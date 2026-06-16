from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from evidence_engine import __version__
from evidence_engine.engine import generate_evidence
from evidence_engine.exceptions import InvalidTerraformPlanError


app = FastAPI(title="LoopThru Evidence Engine", version=__version__)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        raise exc
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "engine": "loopthru-evidence-engine",
        "version": __version__,
    }


@app.post("/v1/evidence/terraform-plan")
def terraform_plan_evidence(plan: dict[str, Any]) -> dict[str, Any]:
    try:
        report = generate_evidence(plan)
    except InvalidTerraformPlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return report.model_dump(mode="json")
