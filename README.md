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
