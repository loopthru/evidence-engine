from collections import Counter
from typing import Any

from evidence_engine import __version__
from evidence_engine.controls.s3 import build_s3_resource_evidence, group_s3_changes
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
from evidence_engine.plan_parser import ParsedResourceChange, parse_plan


S3_RESOURCE_TYPES = {
    "aws_s3_bucket",
    "aws_s3_bucket_server_side_encryption_configuration",
    "aws_s3_bucket_public_access_block",
    "aws_s3_bucket_versioning",
    "aws_s3_bucket_lifecycle_configuration",
    "aws_s3_bucket_policy",
}


def generate_evidence(plan: dict[str, Any]) -> EvidenceReport:
    changes = parse_plan(plan)
    s3_changes = [change for change in changes if change.type in S3_RESOURCE_TYPES]
    resources = [
        build_s3_resource_evidence(group) for group in group_s3_changes(s3_changes).values()
    ]
    resources.extend(
        _unsupported_resource(change) for change in changes if change.type not in S3_RESOURCE_TYPES
    )
    resources.sort(key=lambda resource: resource.address)

    return EvidenceReport(
        engine=EngineInfo(version=__version__),
        summary=_build_summary(resources),
        resources=resources,
    )


def _unsupported_resource(change: ParsedResourceChange) -> ResourceEvidence:
    return ResourceEvidence(
        address=change.address,
        type=change.type,
        name=change.name,
        provider=change.provider,
        change_actions=_change_actions(change.actions),
        before=change.before,
        after=change.after,
        controls=[
            ControlResult(
                id="resource.unsupported",
                name="Unsupported resource",
                category=ControlCategory.PLATFORM,
                status=ControlStatus.UNSUPPORTED,
                severity=Severity.INFO,
                message=(
                    f"Resource type {change.type} is observed but not evaluated "
                    "by this engine version."
                ),
                evidence=EvidencePointer(
                    path=f"resource_changes[{change.index}]",
                    before=change.before,
                    after=change.after,
                ),
            )
        ],
    )


def _build_summary(resources: list[ResourceEvidence]) -> ReportSummary:
    severities = Counter()
    unsupported = 0
    evaluated = 0

    for resource in resources:
        if _is_unsupported_resource(resource):
            unsupported += 1
        else:
            evaluated += 1
        for control in resource.controls:
            severities[Severity(control.severity)] += 1

    return ReportSummary(
        resources_total=len(resources),
        resources_evaluated=evaluated,
        resources_unsupported=unsupported,
        findings_by_severity={
            Severity.CRITICAL: severities[Severity.CRITICAL],
            Severity.HIGH: severities[Severity.HIGH],
            Severity.MEDIUM: severities[Severity.MEDIUM],
            Severity.LOW: severities[Severity.LOW],
            Severity.INFO: severities[Severity.INFO],
        },
    )


def _change_actions(actions: list[str]) -> list[ChangeAction]:
    result: list[ChangeAction] = []
    for action in actions:
        try:
            result.append(ChangeAction(action))
        except ValueError:
            result.append(ChangeAction.UNKNOWN)
    return result


def _is_unsupported_resource(resource: ResourceEvidence) -> bool:
    return bool(resource.controls) and all(
        control.id == "resource.unsupported" and control.status == ControlStatus.UNSUPPORTED
        for control in resource.controls
    )
