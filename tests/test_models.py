from evidence_engine.models import (
    ChangeAction,
    ControlCategory,
    ControlResult,
    ControlStatus,
    EngineInfo,
    EvidencePointer,
    EvidenceReport,
    ReportSummary,
    ResourceEvidence,
    Severity,
)


def test_evidence_report_serializes_resource_first_shape():
    report = EvidenceReport(
        engine=EngineInfo(name="loopthru-evidence-engine", version="0.1.0"),
        summary=ReportSummary(
            resources_total=1,
            resources_evaluated=1,
            resources_unsupported=0,
            findings_by_severity={
                Severity.CRITICAL: 0,
                Severity.HIGH: 1,
                Severity.MEDIUM: 0,
                Severity.LOW: 0,
                Severity.INFO: 0,
            },
        ),
        resources=[
            ResourceEvidence(
                address="aws_s3_bucket.customer_data",
                type="aws_s3_bucket",
                name="customer_data",
                provider="aws",
                change_actions=[ChangeAction.CREATE],
                before=None,
                after={"bucket": "customer-data-prod"},
                controls=[
                    ControlResult(
                        id="s3.encryption",
                        name="S3 bucket encryption",
                        category=ControlCategory.SECURITY,
                        status=ControlStatus.MISSING,
                        severity=Severity.HIGH,
                        message=(
                            "Default bucket encryption is not configured in the proposed state."
                        ),
                        evidence=EvidencePointer(
                            source="terraform_plan",
                            path="resource_changes[0].change.after.server_side_encryption_configuration",
                            before=None,
                            after=None,
                        ),
                    )
                ],
            )
        ],
    )

    payload = report.model_dump(mode="json")

    assert payload["schema_version"] == "2026-06-16.mvp.v1"
    assert payload["resources"][0]["controls"][0]["status"] == "missing"
    assert payload["resources"][0]["controls"][0]["severity"] == "high"
