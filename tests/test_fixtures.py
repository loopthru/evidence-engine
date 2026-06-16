import json
from pathlib import Path

from evidence_engine.engine import generate_evidence


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    with (FIXTURES_DIR / name).open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def summarize_controls(report: object) -> list[dict[str, str]]:
    return [
        {
            "id": control.id,
            "status": control.status,
            "severity": control.severity,
            "message": control.message,
            "evidence_path": control.evidence.path,
        }
        for control in report.resources[0].controls
    ]


def test_empty_plan_fixture_generates_empty_report():
    report = generate_evidence(load_fixture("empty_plan.json"))

    assert report.model_dump(mode="json") == {
        "schema_version": "2026-06-16.mvp.v1",
        "engine": {"name": "loopthru-evidence-engine", "version": "0.1.0"},
        "summary": {
            "resources_total": 0,
            "resources_evaluated": 0,
            "resources_unsupported": 0,
            "findings_by_severity": {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "info": 0,
            },
        },
        "resources": [],
    }


def test_unsupported_only_fixture_reports_unsupported_resource():
    report = generate_evidence(load_fixture("unsupported_only.json"))
    resource = report.resources[0]

    assert report.summary.resources_total == 1
    assert report.summary.resources_evaluated == 0
    assert report.summary.resources_unsupported == 1
    assert resource.address == "aws_instance.web"
    assert resource.type == "aws_instance"
    assert summarize_controls(report) == [
        {
            "id": "resource.unsupported",
            "status": "unsupported",
            "severity": "info",
            "message": (
                "Resource type aws_instance is observed but not evaluated by "
                "this engine version."
            ),
            "evidence_path": "resource_changes[0]",
        }
    ]


def test_s3_missing_controls_fixture_is_stable_full_report_regression():
    plan = load_fixture("s3_missing_controls.json")

    first_report = generate_evidence(plan)
    second_report = generate_evidence(plan)

    assert first_report.model_dump(mode="json") == second_report.model_dump(mode="json")
    assert first_report.model_dump(mode="json")["summary"] == {
        "resources_total": 1,
        "resources_evaluated": 1,
        "resources_unsupported": 0,
        "findings_by_severity": {
            "critical": 0,
            "high": 3,
            "medium": 1,
            "low": 1,
            "info": 1,
        },
    }
    assert first_report.model_dump(mode="json")["resources"][0] | {"controls": []} == {
        "address": "aws_s3_bucket.customer_data",
        "type": "aws_s3_bucket",
        "name": "customer_data",
        "provider": "aws",
        "change_actions": ["create"],
        "before": None,
        "after": {"bucket": "customer-data-prod"},
        "controls": [],
    }
    assert summarize_controls(first_report) == [
        {
            "id": "s3.encryption",
            "status": "missing",
            "severity": "high",
            "message": (
                "S3 bucket server-side encryption is not configured in this plan."
            ),
            "evidence_path": (
                "resource_changes[0].change.after."
                "server_side_encryption_configuration"
            ),
        },
        {
            "id": "s3.public_access_block",
            "status": "missing",
            "severity": "high",
            "message": "S3 bucket public access block is not configured in this plan.",
            "evidence_path": "resource_changes[0].change.after",
        },
        {
            "id": "s3.bucket_policy_exposure",
            "status": "unknown",
            "severity": "high",
            "message": "S3 bucket policy is not present in this plan.",
            "evidence_path": "resource_changes[0].change.after.policy",
        },
        {
            "id": "s3.versioning",
            "status": "missing",
            "severity": "medium",
            "message": "S3 bucket versioning is not configured in this plan.",
            "evidence_path": (
                "resource_changes[0].change.after.versioning_configuration"
            ),
        },
        {
            "id": "s3.lifecycle",
            "status": "missing",
            "severity": "low",
            "message": "S3 bucket lifecycle rules are not configured in this plan.",
            "evidence_path": "resource_changes[0].change.after.rule",
        },
        {
            "id": "s3.storage_class_cost",
            "status": "not_applicable",
            "severity": "info",
            "message": (
                "S3 lifecycle storage class transitions are not applicable "
                "from this plan."
            ),
            "evidence_path": "resource_changes[0].change.after.rule",
        },
    ]


def test_s3_safe_controls_fixture_passes_all_controls():
    report = generate_evidence(load_fixture("s3_safe_controls.json"))

    assert report.summary.resources_total == 1
    assert report.summary.resources_evaluated == 1
    assert report.summary.resources_unsupported == 0

    controls = {control.id: control.status for control in report.resources[0].controls}
    assert controls == {
        "s3.encryption": "passed",
        "s3.public_access_block": "passed",
        "s3.bucket_policy_exposure": "passed",
        "s3.versioning": "passed",
        "s3.lifecycle": "passed",
        "s3.storage_class_cost": "passed",
    }


def test_s3_public_policy_fixture_flags_public_exposure():
    report = generate_evidence(load_fixture("s3_public_policy.json"))

    controls = {control.id: control for control in report.resources[0].controls}
    public_policy = controls["s3.bucket_policy_exposure"]

    assert public_policy.status == "missing"
    assert public_policy.severity == "high"
    assert public_policy.message == "S3 bucket policy allows public principal access."
    assert public_policy.evidence.path == "resource_changes[1].change.after.policy"
