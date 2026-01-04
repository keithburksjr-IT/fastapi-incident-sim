import json
import logging
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, conint


# -----------------------------
# Logging
# -----------------------------
logging.raiseExceptions = False


class SafeStreamHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except BrokenPipeError:
            # stdout pipe closed (e.g., piping to `tee` then stopping)
            try:
                self.flush()
            except Exception:
                pass
            return


logger = logging.getLogger("ops_api")
logger.setLevel(logging.INFO)
logger.propagate = False

_handler = SafeStreamHandler(sys.stdout)
_handler.setLevel(logging.INFO)
_handler.setFormatter(logging.Formatter("%(message)s"))

# Avoid duplicate handlers in reload
if not any(isinstance(h, SafeStreamHandler) for h in logger.handlers):
    logger.addHandler(_handler)


def log_event(level: str, msg: str, **fields) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "level": level,
        "logger": "ops_api",
        "msg": msg,
        **fields,
    }
    line = json.dumps(payload)
    if level == "ERROR":
        logger.error(line)
    else:
        logger.info(line)


# -----------------------------
# DB
# -----------------------------
DB_PATH = "app.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
"""

SEED_SQL = """
INSERT INTO transactions (order_id, user_id, amount_cents, status, created_at) VALUES
    ('ORD-1001', 'U-001', 2599, 'approved', '2025-12-14T10:10:00Z'),
    ('ORD-1002', 'U-002', 1099, 'pending',  '2025-12-14T10:12:00Z'),
    ('ORD-1003', 'U-001', 499,  'declined', '2025-12-14T10:13:00Z'),
    ('ORD-1004', 'U-003', 9999, 'approved', '2025-12-14T10:15:00Z');
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.executescript(SCHEMA_SQL)
        row = cur.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()
        if row and int(row["c"]) == 0:
            cur.executescript(SEED_SQL)
        conn.commit()
    finally:
        conn.close()


# -----------------------------
# App
# -----------------------------
app = FastAPI(title="FastAPI Incident Troubleshooting Lab")


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.time()
    try:
        response = await call_next(request)
        duration_ms = int((time.time() - start) * 1000)
        log_event(
            "INFO",
            "request_completed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            client_ip=(request.client.host if request.client else None),
        )
        response.headers["X-Request-Id"] = request_id
        return response
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log_event(
            "ERROR",
            "unhandled_exception",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=500,
            duration_ms=duration_ms,
            client_ip=(request.client.host if request.client else None),
            error_type=type(e).__name__,
        )
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error", "request_id": request_id})


# -----------------------------
# Core endpoints
# -----------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/fail")
def fail():
    raise RuntimeError("simulated failure")


@app.get("/timeout")
def timeout(seconds: int = 2):
    time.sleep(seconds)
    return {"slept": seconds}


# -----------------------------
# Transactions endpoints
# -----------------------------
@app.get("/transactions/recent")
def tx_recent(limit: int = 25):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/transactions/bad-query")
def tx_bad_query():
    conn = get_conn()
    try:
        conn.execute("SELECT * FROM not_a_real_table").fetchall()
        return {"ok": True}
    finally:
        conn.close()


class TransactionCreate(BaseModel):
    order_id: str = Field(min_length=3, max_length=50)
    user_id: str = Field(min_length=2, max_length=50)
    amount_cents: conint(ge=1, le=1_000_000)
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
