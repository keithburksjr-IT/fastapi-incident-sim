

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