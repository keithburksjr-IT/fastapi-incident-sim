

# FastAPI Incident Troubleshooting Lab

This project is a small FastAPI application built to practice real-world IT and application support workflows, with an emphasis on troubleshooting and incident response rather than feature development.

## What This Demonstrates
- Reproducing application errors and slow responses on demand
- Structured JSON application logging (request ID, endpoint, latency)
- Investigating issues using logs and SQL queries
- Using Splunk saved searches to identify errors and performance issues
- Writing simple runbooks for repeatable incident response

## How to Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001 --no-access-log | tee app.log
```

API documentation:
```
http://127.0.0.1:8001/docs
```

## Key Endpoints
| Endpoint | Purpose |
|--------|--------|
| `/health` | Service health check |
| `/fail` | Simulated 500 error |
| `/timeout?seconds=2` | Simulated slow response |
| `/transactions/recent` | Retrieve recent transaction data |
| `/transactions/bad-query` | Simulated SQL error |

## Logging & Monitoring
- The application emits structured JSON logs including request_id, path, status_code, and duration_ms
- Logs are written to `app.log`
- Logs are ingested into Splunk via file monitoring
- Saved searches are used to identify failing endpoints and slow requests

## SQL Validation
The `Query.sql` file contains example SQL queries used to validate application behavior, confirm fixes, and investigate transaction data during incidents.

## Purpose
This project is intentionally small and practical, designed to mirror how issues are investigated in IT support, MSP, and application support roles.
# FastAPI Incident Troubleshooting Lab

A small FastAPI application built to practice **IT / application support** troubleshooting workflows: reproduce incidents, inspect logs, validate with SQL, and triage using Splunk.

## What This Demonstrates
- Reproducing incidents on demand (500s, slow responses, SQL errors)
- Structured JSON application logging (request ID, endpoint, latency)
- Validating behavior with API calls (Postman / curl) and SQL queries
- Log ingestion into Splunk and saved searches for fast triage
- Simple runbook-driven incident response

## How to Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001 --no-access-log | tee app.log
```

API documentation:
```
http://127.0.0.1:8001/docs
```

> Tip: If you see `Address already in use`, another Uvicorn instance is already running on port 8001.

## Key Endpoints
| Endpoint | Purpose |
|--------|--------|
| `/health` | Service health check |
| `/fail` | Simulated 500 error (exception) |
| `/timeout?seconds=2` | Simulated slow response |
| `/transactions/recent` | Retrieve recent transaction data |
| `/transactions/bad-query` | Simulated SQL error |
| `/transactions/by-user/{user_id}` | Retrieve transactions for a user |
| `/transactions/search?status=pending&min_amount_cents=500` | Filter transactions |
| `/transactions` (POST) | Create a transaction |
| `/transactions/{order_id}/status` (PUT) | Update transaction status |

## API Validation (Postman)
The endpoints were exercised using Postman to:
- Reproduce error conditions (HTTP 500)
- Generate slow requests for performance triage
- Validate normal responses after changes



## Logging & Monitoring (Splunk)
- The application emits structured JSON logs including `request_id`, `path`, `status_code`, and `duration_ms`.
- Logs are written to `app.log` and can be ingested into Splunk via file monitoring.

Saved searches used for triage:
- **Errors by Endpoint** (counts error events grouped by path)
- **Slow Requests (>1s)** (requests where `duration_ms > 1000`)

(Recommended proof: add screenshots of each saved search results to `/screenshots`.)

## SQL Validation
`Query.sql` contains SQL used to validate application behavior during investigations (incident triage vs validation vs reporting).

## Repo Hygiene
This repo intentionally excludes local artifacts:
- `.venv/`, `__pycache__/`, `app.log`, `app.db`, `.idea/`

## Purpose
This project is intentionally small and practical, designed to mirror how issues are investigated in **IT support, MSP, and application support** roles.