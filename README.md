# evidence-engine

Repository for LoopThru's Evidence Engine Service.

## Local Development

```bash
python -m pip install -e ".[dev]"
pytest
```

## Database

The API expects the `review` table to exist in PostgreSQL. Add database settings
to `.env` before running the web service:

```dotenv
HOST=127.0.0.1
PORT=5432
DATABASE=evidence_engine
DB_USER=postgres
DB_PASSWORD=postgres
```

`DATABASE_URL` is also supported when a deployment platform provides a complete
PostgreSQL connection string.

## CLI

```bash
evidence-engine plan tests/fixtures/s3_missing_controls.json
```

## API

```bash
uvicorn evidence_engine.api:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Generate and persist evidence:

```bash
curl -X POST http://127.0.0.1:8000/v1/evidence/terraform-plan \
  -H "Content-Type: application/json" \
  --data '{
    "session_uid": "11111111-1111-1111-1111-111111111111",
    "terraform_plan": {
      "resource_changes": []
    }
  }'
```

Response shape:

```json
{
  "review_id": "22222222-2222-2222-2222-222222222222",
  "session_uid": "11111111-1111-1111-1111-111111111111",
  "status": "evidence_saved",
  "evidence": {
    "schema_version": "2026-06-16.mvp.v1",
    "engine": {
      "name": "loopthru-evidence-engine",
      "version": "0.1.0"
    },
    "summary": {
      "resources_total": 0,
      "resources_evaluated": 0,
      "resources_unsupported": 0,
      "findings_by_severity": {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0
      }
    },
    "resources": []
  }
}
```

## Render

This service is configured for Render with `render.yaml`.

The web process runs:

```bash
uvicorn evidence_engine.api:app --host 0.0.0.0 --port $PORT
```
