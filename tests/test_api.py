from fastapi.testclient import TestClient

from evidence_engine import __version__
from evidence_engine.api import app


client = TestClient(app)


def test_health_endpoint_returns_engine_version():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "engine": "loopthru-evidence-engine",
        "version": __version__,
    }


def test_terraform_plan_endpoint_returns_evidence_report():
    response = client.post(
        "/v1/evidence/terraform-plan",
        json={"resource_changes": []},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "2026-06-16.mvp.v1"
    assert payload["summary"]["resources_total"] == 0


def test_terraform_plan_endpoint_rejects_unrecognized_plan_json():
    response = client.post("/v1/evidence/terraform-plan", json={"hello": "world"})

    assert response.status_code == 422
    assert response.json()["detail"] == "Terraform plan JSON must include a resource_changes array."
