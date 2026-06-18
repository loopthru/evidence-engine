import inspect
from uuid import UUID

import anyio
import httpx
from fastapi.testclient import TestClient

from evidence_engine import __version__
from evidence_engine.api import app, terraform_plan_evidence
from evidence_engine.db import AgentStatusRecord, ReviewRecord, ReviewStatusRecord

client = TestClient(app)


class FakeReviewRepository:
    def __init__(self):
        self.insert_calls = []
        self.status_by_session_uid = {}

    def insert_review(self, *, session_uid, evidence):
        self.insert_calls.append(
            {
                "session_uid": session_uid,
                "evidence": evidence,
            }
        )
        return ReviewRecord(
            id=UUID("22222222-2222-2222-2222-222222222222"),
            session_uid=session_uid,
            status="evidence_saved",
        )

    def get_status_by_session_uid(self, session_uid):
        return self.status_by_session_uid.get(session_uid)


def test_health_endpoint_returns_engine_version():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "engine": "loopthru-evidence-engine",
        "version": __version__,
    }


def test_terraform_plan_endpoint_handler_is_async():
    assert inspect.iscoroutinefunction(terraform_plan_evidence)


def test_terraform_plan_endpoint_returns_evidence_report(monkeypatch):
    repository = FakeReviewRepository()
    monkeypatch.setattr("evidence_engine.api.review_repository", repository)

    response = client.post(
        "/v1/evidence/terraform-plan",
        json={
            "session_uid": "11111111-1111-1111-1111-111111111111",
            "terraform_plan": {"resource_changes": []},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["review_id"] == "22222222-2222-2222-2222-222222222222"
    assert payload["session_uid"] == "11111111-1111-1111-1111-111111111111"
    assert payload["status"] == "evidence_saved"
    assert payload["evidence"]["schema_version"] == "2026-06-16.mvp.v1"
    assert payload["evidence"]["summary"]["resources_total"] == 0


def test_terraform_plan_endpoint_persists_evidence_report(monkeypatch):
    repository = FakeReviewRepository()
    monkeypatch.setattr("evidence_engine.api.review_repository", repository)

    response = client.post(
        "/v1/evidence/terraform-plan",
        json={
            "session_uid": "11111111-1111-1111-1111-111111111111",
            "terraform_plan": {"resource_changes": []},
        },
    )

    payload = response.json()
    assert repository.insert_calls == [
        {
            "session_uid": UUID("11111111-1111-1111-1111-111111111111"),
            "evidence": payload["evidence"],
        }
    ]


def test_terraform_plan_endpoint_triggers_orchestrator(monkeypatch):
    repository = FakeReviewRepository()
    trigger_calls = []
    monkeypatch.setattr("evidence_engine.api.review_repository", repository)
    monkeypatch.setattr(
        "evidence_engine.api.trigger_band_review",
        lambda session_uid: trigger_calls.append(session_uid),
    )

    response = client.post(
        "/v1/evidence/terraform-plan",
        json={
            "session_uid": "11111111-1111-1111-1111-111111111111",
            "terraform_plan": {"resource_changes": []},
        },
    )

    assert response.status_code == 200
    assert trigger_calls == ["11111111-1111-1111-1111-111111111111"]


def test_terraform_plan_endpoint_rejects_band_chat_id(monkeypatch):
    repository = FakeReviewRepository()
    monkeypatch.setattr("evidence_engine.api.review_repository", repository)

    response = client.post(
        "/v1/evidence/terraform-plan",
        json={
            "session_uid": "11111111-1111-1111-1111-111111111111",
            "band_chat_id": "chat-abc",
            "terraform_plan": {"resource_changes": []},
        },
    )

    assert response.status_code == 422
    assert repository.insert_calls == []


def test_terraform_plan_endpoint_rejects_unrecognized_plan_json(monkeypatch):
    repository = FakeReviewRepository()
    monkeypatch.setattr("evidence_engine.api.review_repository", repository)

    response = client.post(
        "/v1/evidence/terraform-plan",
        json={
            "session_uid": "11111111-1111-1111-1111-111111111111",
            "terraform_plan": {"hello": "world"},
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Terraform plan JSON must include a resource_changes array."
    assert repository.insert_calls == []


def test_terraform_plan_endpoint_does_not_trigger_orchestrator_for_invalid_plan(monkeypatch):
    repository = FakeReviewRepository()
    trigger_calls = []
    monkeypatch.setattr("evidence_engine.api.review_repository", repository)
    monkeypatch.setattr(
        "evidence_engine.api.trigger_band_review",
        lambda session_uid: trigger_calls.append(session_uid),
    )

    response = client.post(
        "/v1/evidence/terraform-plan",
        json={
            "session_uid": "11111111-1111-1111-1111-111111111111",
            "terraform_plan": {"hello": "world"},
        },
    )

    assert response.status_code == 422
    assert trigger_calls == []


def test_trigger_band_review_posts_session_uid(monkeypatch):
    post_calls = []

    class FakeAsyncClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def post(self, url, *, json):
            post_calls.append(
                {
                    "url": url,
                    "json": json,
                    "timeout": self.timeout,
                }
            )
            return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr("evidence_engine.api.httpx.AsyncClient", FakeAsyncClient)

    from evidence_engine.api import trigger_band_review

    anyio.run(trigger_band_review, "11111111-1111-1111-1111-111111111111")

    assert post_calls == [
        {
            "url": "https://band-of-agents.onrender.com/review",
            "json": {"session_uid": "11111111-1111-1111-1111-111111111111"},
            "timeout": 5.0,
        }
    ]


def test_terraform_plan_endpoint_rejects_missing_session_uid():
    response = client.post(
        "/v1/evidence/terraform-plan",
        json={"terraform_plan": {"resource_changes": []}},
    )

    assert response.status_code == 422


def test_evidence_status_endpoint_returns_evidence_saved(monkeypatch):
    session_uid = UUID("11111111-1111-1111-1111-111111111111")
    repository = FakeReviewRepository()
    repository.status_by_session_uid[session_uid] = ReviewStatusRecord(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        session_uid=session_uid,
        status="evidence_saved",
        summarizer_output=None,
        agents=[],
    )
    monkeypatch.setattr("evidence_engine.api.review_repository", repository)

    response = client.get(f"/v1/evidence/status/{session_uid}")

    assert response.status_code == 200
    assert response.json() == {
        "session_uid": str(session_uid),
        "status": "evidence_saved",
    }


def test_evidence_status_endpoint_returns_agents_running(monkeypatch):
    session_uid = UUID("11111111-1111-1111-1111-111111111111")
    repository = FakeReviewRepository()
    repository.status_by_session_uid[session_uid] = ReviewStatusRecord(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        session_uid=session_uid,
        status="agents_running",
        summarizer_output=None,
        agents=[
            AgentStatusRecord(agent="Policy", status="running"),
            AgentStatusRecord(agent="Security", status="queued"),
        ],
    )
    monkeypatch.setattr("evidence_engine.api.review_repository", repository)

    response = client.get(f"/v1/evidence/status/{session_uid}")

    assert response.status_code == 200
    assert response.json() == {
        "session_uid": str(session_uid),
        "status": "agents_running",
        "agents": [
            {"agent": "Policy", "status": "running"},
            {"agent": "Security", "status": "queued"},
        ],
    }


def test_evidence_status_endpoint_returns_summarized(monkeypatch):
    session_uid = UUID("11111111-1111-1111-1111-111111111111")
    repository = FakeReviewRepository()
    repository.status_by_session_uid[session_uid] = ReviewStatusRecord(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        session_uid=session_uid,
        status="summarized",
        summarizer_output={"risk": "low"},
        agents=[],
    )
    monkeypatch.setattr("evidence_engine.api.review_repository", repository)

    response = client.get(f"/v1/evidence/status/{session_uid}")

    assert response.status_code == 200
    assert response.json() == {
        "session_uid": str(session_uid),
        "status": "summarized",
        "summary": {"risk": "low"},
    }


def test_evidence_status_endpoint_returns_unexpected_status_without_extra_fields(monkeypatch):
    session_uid = UUID("11111111-1111-1111-1111-111111111111")
    repository = FakeReviewRepository()
    repository.status_by_session_uid[session_uid] = ReviewStatusRecord(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        session_uid=session_uid,
        status="custom_status",
        summarizer_output={"ignored": True},
        agents=[AgentStatusRecord(agent="Security", status="running")],
    )
    monkeypatch.setattr("evidence_engine.api.review_repository", repository)

    response = client.get(f"/v1/evidence/status/{session_uid}")

    assert response.status_code == 200
    assert response.json() == {
        "session_uid": str(session_uid),
        "status": "custom_status",
    }


def test_evidence_status_endpoint_returns_404_for_unknown_session_uid(monkeypatch):
    session_uid = UUID("11111111-1111-1111-1111-111111111111")
    repository = FakeReviewRepository()
    monkeypatch.setattr("evidence_engine.api.review_repository", repository)

    response = client.get(f"/v1/evidence/status/{session_uid}")

    assert response.status_code == 404
