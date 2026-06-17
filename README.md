# evidence-engine

Repository for LoopThru's Evidence Engine Service.

## Local Development

```bash
python -m pip install -e ".[dev]"
pytest
```

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

Generate evidence:

```bash
curl -X POST http://127.0.0.1:8000/v1/evidence/terraform-plan \
  -H "Content-Type: application/json" \
  --data @tests/fixtures/s3_missing_controls.json
```

## Render

This service is configured for Render with `render.yaml`.

The web process runs:

```bash
uvicorn evidence_engine.api:app --host 0.0.0.0 --port $PORT
```
