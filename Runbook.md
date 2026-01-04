

# Incident Runbook

This runbook documents how to investigate common application issues using logs, SQL, and API behavior.

## Incident 1: API Returning 500 Errors

**Symptom**
- Endpoint returns HTTP 500

**Reproduction**
```bash
curl http://127.0.0.1:8001/fail
```

**Investigation**
1. Review the Splunk saved search **Errors by Endpoint**
2. Identify the failing path and error type
3. Correlate events using request metadata if needed

**Likely Causes**
- Unhandled application exception
- SQL error
- Invalid code path

**Validation**
- Endpoint returns expected response
- No new error events appear in Splunk

## Incident 2: Slow API Responses

**Symptom**
- Users report slow responses

**Reproduction**
```bash
curl "http://127.0.0.1:8001/timeout?seconds=2"
```

**Investigation**
1. Review the Splunk saved search **Slow Requests Over 1s**
2. Identify affected endpoints
3. Confirm response times exceed threshold

**Likely Causes**
- Blocking operation
- External dependency delay
- Inefficient query

**Validation**
- Endpoint responds within expected time
- Slow request count decreases in Splunk

## Incident 3: Database / SQL Error

**Symptom**
- API returns HTTP 500 when accessing transaction data

**Reproduction**
```bash
curl http://127.0.0.1:8001/transactions/bad-query
```

**Investigation**
1. Review error events in Splunk
2. Identify SQL-related error messages
3. Run validation queries from `Query.sql`

**Likely Causes**
- Invalid SQL
- Schema mismatch
- Missing table or column

**Validation**
- SQL query executes successfully
- Endpoint returns expected data

## Notes
- Logs are the primary source of truth
- SQL is used to confirm application state
- Saved searches enable fast triage during incidents