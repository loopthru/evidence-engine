from uuid import UUID

from fastapi.testclient import TestClient

from evidence_engine import __version__
from evidence_engine.api import app
from evidence_engine.db import ReviewRecord

client = TestClient(app)


class FakeReviewRepository:
    def __init__(self):
        self.insert_calls = []

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


def test_health_endpoint_returns_engine_version():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "engine": "loopthru-evidence-engine",
        "version": __version__,
    }


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


def test_terraform_plan_endpoint_rejects_missing_session_uid():
    response = client.post(
        "/v1/evidence/terraform-plan",
        json={"terraform_plan": {"resource_changes": []}},
    )

    assert response.status_code == 422

