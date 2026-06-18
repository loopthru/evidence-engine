from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from evidence_engine import __version__
from evidence_engine.db import (
    DatabaseConfigurationError,
    ReviewRepository,
)
from evidence_engine.engine import generate_evidence
from evidence_engine.exceptions import InvalidTerraformPlanError

app = FastAPI(title="LoopThru Evidence Engine", version=__version__)
review_repository = ReviewRepository()


class TerraformPlanEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_uid: UUID
    terraform_plan: dict[str, Any] = Field(min_length=1)


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
def terraform_plan_evidence(request: TerraformPlanEvidenceRequest) -> dict[str, Any]:
    try:
        report = generate_evidence(request.terraform_plan)
    except InvalidTerraformPlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    evidence = report.model_dump(mode="json")

    try:
        review = review_repository.insert_review(
            session_uid=request.session_uid,
            evidence=evidence,
        )
    except DatabaseConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "review_id": str(review.id),
        "session_uid": str(review.session_uid),
        "status": review.status,
        "evidence": evidence,
    }
