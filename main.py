import json
import logging
import sys
import time
import uuid
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Callable, Optional, Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, conint

app = FastAPI(
    title="Ops / Incident Practice API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- Structured JSON logging (Splunk-friendly) ---
logger = logging.getLogger("ops_api")
logger.setLevel(logging.INFO)

class SafeStreamHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except BrokenPipeError:
            # stdout pipe closed (e.g., `uvicorn ... | tee app.log` then Ctrl+C)
            try:
                self.flush()
            except Exception:
                pass
            return

_handler = SafeStreamHandler(sys.stdout)
_handler.setLevel(logging.INFO)

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Attach extra fields if present
        for k in (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "client_ip",
            "error_type",
        ):
            if hasattr(record, k):
                payload[k] = getattr(record, k)
        return json.dumps(payload, ensure_ascii=False)

_handler.setFormatter(JsonFormatter())
logger.handlers.clear()
logger.addHandler(_handler)
logger.propagate = False


# --- SQLite (embedded) for SQL practice ---
DB_PATH = Path(__file__).with_name("app.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  amount_cents INTEGER NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transactions_order_id ON transactions(order_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
"""

SEED_SQL = """
INSERT INTO transactions (order_id, user_id, amount_cents, status, created_at) VALUES
('ORD-1001','U-001',2599,'approved','2025-12-14T10:10:00Z'),
('ORD-1002','U-002',4999,'declined','2025-12-14T10:12:00Z'),
('ORD-1003','U-001',1299,'pending','2025-12-14T10:13:30Z'),
('ORD-1004','U-003',9999,'approved','2025-12-14T10:15:00Z');
"""


def get_conn() -> sqlite3.Connection:
    # `check_same_thread=False` allows usage across different threads (common with FastAPI/Uvicorn)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.executescript(SCHEMA_SQL)

        # Seed only if empty
        cur.execute("SELECT COUNT(*) AS c FROM transactions")
        count = cur.fetchone()["c"]
        if count == 0:
            cur.executescript(SEED_SQL)
        conn.commit()
    finally:
        conn.close()


@app.on_event("startup")
def on_startup():
    init_db()


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next: Callable):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    start = time.time()

    try:
        response = await call_next(request)
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        logger.error(
            "unhandled_exception",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "duration_ms": duration_ms,
                "client_ip": getattr(request.client, "host", "unknown"),
                "error_type": type(e).__name__,
            },
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error", "request_id": request_id},
        )

    duration_ms = int((time.time() - start) * 1000)
    logger.info(
        "request_completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "client_ip": getattr(request.client, "host", "unknown"),
        },
    )

    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/fail")
def fail():
    # Simulate a real bug/unhandled exception (will be caught by middleware -> 500)
    raise RuntimeError("Simulated failure for incident practice")


@app.get("/timeout")
async def timeout(seconds: int = 10):
    # Simulate a slow upstream dependency / timeout-like behavior
    # (This will still return 200, but with high latency.)
    import asyncio

    await asyncio.sleep(seconds)
    return {"status": "ok", "slept_seconds": seconds}


# --- SQL Query Endpoints ---

@app.get("/transactions/by-order/{order_id}")
def tx_by_order(order_id: str):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM transactions WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        return dict(row)
    finally:
        conn.close()


@app.get("/transactions/recent")
def tx_recent(limit: int = 10):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# --- Additional Transaction Endpoints and Models ---
class TransactionCreate(BaseModel):
    order_id: str = Field(min_length=3, max_length=50)
    user_id: str = Field(min_length=2, max_length=50)
    amount_cents: conint(ge=1, le=1_000_000)  # $0.01 - $10,000
    status: Literal["approved", "declined", "pending"] = "pending"


class TransactionUpdateStatus(BaseModel):
    status: Literal["approved", "declined", "pending"]


@app.get("/transactions/by-user/{user_id}")
def tx_by_user(user_id: str, limit: int = 25):
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT * FROM transactions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/transactions/search")
def tx_search(
    status: Optional[str] = None,
    min_amount_cents: Optional[int] = None,
    max_amount_cents: Optional[int] = None,
    user_id: Optional[str] = None,
    limit: int = 50,
):
    # Simple dynamic filtering (safe parameterization)
    where = []
    params = []

    if status:
        where.append("status = ?")
        params.append(status)
    if user_id:
        where.append("user_id = ?")
        params.append(user_id)
    if min_amount_cents is not None:
        where.append("amount_cents >= ?")
        params.append(min_amount_cents)
    if max_amount_cents is not None:
        where.append("amount_cents <= ?")
        params.append(max_amount_cents)

    sql = "SELECT * FROM transactions"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    conn = get_conn()
    try:
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.post("/transactions", status_code=201)
def tx_create(payload: TransactionCreate):
    conn = get_conn()
    try:
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        conn.execute(
            """
            INSERT INTO transactions (order_id, user_id, amount_cents, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (payload.order_id, payload.user_id, payload.amount_cents, payload.status, created_at),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM transactions WHERE order_id = ?",
            (payload.order_id,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


@app.put("/transactions/{order_id}/status")
def tx_update_status(order_id: str, payload: TransactionUpdateStatus):
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE transactions SET status = ? WHERE order_id = ?",
            (payload.status, order_id),
        )
        conn.commit()

        if cur.rowcount == 0:
            return JSONResponse(status_code=404, content={"detail": "Not found"})

        row = conn.execute(
            "SELECT * FROM transactions WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


@app.get("/transactions/bad-query")
def tx_bad_query():
    # Intentionally broken SQL to simulate an incident (500 + JSON logs)
    conn = get_conn()
    try:
        conn.execute("SELECT * FROM transactionz")  # typo table name
        return {"status": "should_not_happen"}
    finally:
        conn.close()
