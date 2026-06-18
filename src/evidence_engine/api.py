from typing import Any
from uuid import UUID

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
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
BAND_REVIEW_URL = "https://band-of-agents.onrender.com/review"


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
async def terraform_plan_evidence(
    request: TerraformPlanEvidenceRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
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

    background_tasks.add_task(trigger_band_review, str(review.session_uid))

    return {
        "review_id": str(review.id),
        "session_uid": str(review.session_uid),
        "status": review.status,
        "evidence": evidence,
    }


@app.get("/v1/evidence/status/{session_uid}")
def evidence_status(session_uid: UUID) -> dict[str, Any]:
    try:
        review = review_repository.get_status_by_session_uid(session_uid)
    except DatabaseConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if review is None:
        raise HTTPException(status_code=404, detail="Review not found.")

    response: dict[str, Any] = {
        "session_uid": str(review.session_uid),
        "status": review.status,
    }
    if review.status == "agents_running":
        response["agents"] = [
            {"agent": agent.agent, "status": agent.status}
            for agent in review.agents
        ]
    elif review.status == "summarized":
        response["summary"] = review.summarizer_output

    return response


async def trigger_band_review(session_uid: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                BAND_REVIEW_URL,
                json={"session_uid": session_uid},
            )
        response.raise_for_status()
    except httpx.HTTPError:
        return
