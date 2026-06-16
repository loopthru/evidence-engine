import json
from dataclasses import dataclass, field
from typing import Any

from evidence_engine.models import (
    ChangeAction,
    ControlCategory,
    ControlResult,
    ControlStatus,
    EvidencePointer,
    ResourceEvidence,
    Severity,
)
from evidence_engine.plan_parser import ParsedResourceChange


S3_BUCKET_TYPE = "aws_s3_bucket"
S3_RELATED_TYPES = {
    "aws_s3_bucket_server_side_encryption_configuration",
    "aws_s3_bucket_public_access_block",
    "aws_s3_bucket_versioning",
    "aws_s3_bucket_lifecycle_configuration",
    "aws_s3_bucket_policy",
}
CONTROL_ORDER = [
    "s3.encryption",
    "s3.public_access_block",
    "s3.bucket_policy_exposure",
    "s3.versioning",
    "s3.lifecycle",
    "s3.storage_class_cost",
]
PUBLIC_ACCESS_BLOCK_KEYS = (
    "block_public_acls",
    "block_public_policy",
    "ignore_public_acls",
    "restrict_public_buckets",
)


@dataclass
class S3ResourceGroup:
    key: str
    bucket_change: ParsedResourceChange | None = None
    related: dict[str, ParsedResourceChange] = field(default_factory=dict)


def group_s3_changes(changes: list[ParsedResourceChange]) -> dict[str, S3ResourceGroup]:
    bucket_key_by_name: dict[str, str] = {}
    groups: dict[str, S3ResourceGroup] = {}

    for change in changes:
        if change.type != S3_BUCKET_TYPE:
            continue
        key = change.address
        groups[key] = S3ResourceGroup(key=key, bucket_change=change)
        bucket_name = _bucket_identifier(change.after) or _bucket_identifier(change.before)
        if bucket_name:
            bucket_key_by_name[bucket_name] = key

    for change in changes:
        if change.type not in S3_RELATED_TYPES:
            continue
        bucket_name = _bucket_identifier(change.after) or _bucket_identifier(change.before)
        key = bucket_key_by_name.get(bucket_name or "") or f"unresolved:{change.address}"
        group = groups.setdefault(key, S3ResourceGroup(key=key))
        # Terraform S3 companion resources are expected to be one-per-bucket per type.
        # If a plan contains duplicates, keep the later change deterministically.
        group.related[change.type] = change

    return dict(sorted(groups.items(), key=lambda item: item[0]))


def build_s3_resource_evidence(group: S3ResourceGroup) -> ResourceEvidence:
    primary = _primary_change(group)
    controls_by_id = {
        "s3.encryption": _encryption_control(group, primary),
        "s3.public_access_block": _public_access_block_control(group, primary),
        "s3.bucket_policy_exposure": _bucket_policy_exposure_control(group, primary),
        "s3.versioning": _versioning_control(group, primary),
        "s3.lifecycle": _lifecycle_control(group, primary),
        "s3.storage_class_cost": _storage_class_cost_control(group, primary),
    }

    return ResourceEvidence(
        address=primary.address,
        type=primary.type,
        name=primary.name,
        provider=primary.provider,
        change_actions=_change_actions(primary.actions),
        before=primary.before,
        after=primary.after,
        controls=[controls_by_id[control_id] for control_id in CONTROL_ORDER],
    )


def _bucket_identifier(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    bucket = value.get("bucket")
    if isinstance(bucket, str) and bucket:
        return bucket
    bucket_id = value.get("id")
    if isinstance(bucket_id, str) and bucket_id:
        return bucket_id
    return None


def _primary_change(group: S3ResourceGroup) -> ParsedResourceChange:
    if group.bucket_change is not None:
        return group.bucket_change
    return sorted(group.related.values(), key=lambda change: change.index)[0]


def _change_actions(actions: list[str]) -> list[ChangeAction]:
    result: list[ChangeAction] = []
    for action in actions:
        try:
            result.append(ChangeAction(action))
        except ValueError:
            result.append(ChangeAction.UNKNOWN)
    return result


def _encryption_control(group: S3ResourceGroup, primary: ParsedResourceChange) -> ControlResult:
    related = group.related.get("aws_s3_bucket_server_side_encryption_configuration")
    if related is not None:
        rule = _dict_value(related.after, "rule")
        if _has_value(rule):
            return _control(
                "s3.encryption",
                "S3 encryption",
                ControlCategory.SECURITY,
                ControlStatus.PASSED,
                Severity.HIGH,
                "S3 bucket has server-side encryption configured.",
                related,
                "change.after.rule",
                _dict_value(related.before, "rule"),
                rule,
            )

    inline = _dict_value(primary.after, "server_side_encryption_configuration")
    if _has_value(inline):
        return _control(
            "s3.encryption",
            "S3 encryption",
            ControlCategory.SECURITY,
            ControlStatus.PASSED,
            Severity.HIGH,
            "S3 bucket has inline server-side encryption configured.",
            primary,
            "change.after.server_side_encryption_configuration",
            _dict_value(primary.before, "server_side_encryption_configuration"),
            inline,
        )

    return _control(
        "s3.encryption",
        "S3 encryption",
        ControlCategory.SECURITY,
        ControlStatus.MISSING,
        Severity.HIGH,
        "S3 bucket server-side encryption is not configured in this plan.",
        related or primary,
        (
            "change.after.rule"
            if related is not None
            else "change.after.server_side_encryption_configuration"
        ),
        _dict_value(
            (related or primary).before,
            "rule" if related is not None else "server_side_encryption_configuration",
        ),
        _dict_value(
            (related or primary).after,
            "rule" if related is not None else "server_side_encryption_configuration",
        ),
    )


def _public_access_block_control(
    group: S3ResourceGroup, primary: ParsedResourceChange
) -> ControlResult:
    related = group.related.get("aws_s3_bucket_public_access_block")
    if related is None:
        return _control(
            "s3.public_access_block",
            "S3 public access block",
            ControlCategory.SECURITY,
            ControlStatus.MISSING,
            Severity.HIGH,
            "S3 bucket public access block is not configured in this plan.",
            primary,
            "change.after",
            primary.before,
            primary.after,
        )

    after = related.after if isinstance(related.after, dict) else {}
    before = related.before if isinstance(related.before, dict) else {}
    if all(after.get(key) is True for key in PUBLIC_ACCESS_BLOCK_KEYS):
        status = ControlStatus.PASSED
        message = "S3 bucket public access block enables all required protections."
    elif any(
        before.get(key) is True for key in PUBLIC_ACCESS_BLOCK_KEYS if after.get(key) is not True
    ):
        status = ControlStatus.CHANGED
        message = "S3 bucket public access block is being weakened in this plan."
    else:
        status = ControlStatus.MISSING
        message = "S3 bucket public access block does not enable all required protections."

    return _control(
        "s3.public_access_block",
        "S3 public access block",
        ControlCategory.SECURITY,
        status,
        Severity.HIGH,
        message,
        related,
        "change.after",
        related.before,
        related.after,
    )


def _bucket_policy_exposure_control(
    group: S3ResourceGroup, primary: ParsedResourceChange
) -> ControlResult:
    related = group.related.get("aws_s3_bucket_policy")
    if related is None:
        return _control(
            "s3.bucket_policy_exposure",
            "S3 bucket policy exposure",
            ControlCategory.SECURITY,
            ControlStatus.UNKNOWN,
            Severity.HIGH,
            "S3 bucket policy is not present in this plan.",
            primary,
            "change.after.policy",
            None,
            None,
        )

    before_policy = _dict_value(related.before, "policy")
    after_policy = _dict_value(related.after, "policy")
    status = ControlStatus.UNKNOWN
    message = "S3 bucket policy could not be evaluated from this plan."

    if isinstance(after_policy, str):
        try:
            parsed_policy = json.loads(after_policy)
        except json.JSONDecodeError:
            parsed_policy = None
        if isinstance(parsed_policy, dict):
            if _policy_allows_public_principal(parsed_policy):
                status = ControlStatus.MISSING
                message = "S3 bucket policy allows public principal access."
            else:
                status = ControlStatus.PASSED
                message = "S3 bucket policy does not allow public principal access."

    return _control(
        "s3.bucket_policy_exposure",
        "S3 bucket policy exposure",
        ControlCategory.SECURITY,
        status,
        Severity.HIGH,
        message,
        related,
        "change.after.policy",
        before_policy,
        after_policy,
    )


def _versioning_control(group: S3ResourceGroup, primary: ParsedResourceChange) -> ControlResult:
    related = group.related.get("aws_s3_bucket_versioning")
    if related is None:
        return _control(
            "s3.versioning",
            "S3 versioning",
            ControlCategory.RELIABILITY,
            ControlStatus.MISSING,
            Severity.MEDIUM,
            "S3 bucket versioning is not configured in this plan.",
            primary,
            "change.after.versioning_configuration",
            None,
            None,
        )

    before_config = _dict_value(related.before, "versioning_configuration")
    after_config = _dict_value(related.after, "versioning_configuration")
    if _versioning_enabled(after_config):
        status = ControlStatus.PASSED
        message = "S3 bucket versioning is enabled."
    elif _versioning_enabled(before_config):
        status = ControlStatus.CHANGED
        message = "S3 bucket versioning is being disabled or suspended."
    else:
        status = ControlStatus.MISSING
        message = "S3 bucket versioning is not enabled."

    return _control(
        "s3.versioning",
        "S3 versioning",
        ControlCategory.RELIABILITY,
        status,
        Severity.MEDIUM,
        message,
        related,
        "change.after.versioning_configuration",
        before_config,
        after_config,
    )


def _lifecycle_control(group: S3ResourceGroup, primary: ParsedResourceChange) -> ControlResult:
    related = group.related.get("aws_s3_bucket_lifecycle_configuration")
    rule = _dict_value(related.after, "rule") if related is not None else None
    status = ControlStatus.PASSED if _has_value(rule) else ControlStatus.MISSING
    return _control(
        "s3.lifecycle",
        "S3 lifecycle",
        ControlCategory.RELIABILITY,
        status,
        Severity.LOW,
        "S3 bucket lifecycle rules are configured."
        if status == ControlStatus.PASSED
        else "S3 bucket lifecycle rules are not configured in this plan.",
        related or primary,
        "change.after.rule",
        _dict_value((related or primary).before, "rule"),
        rule,
    )


def _storage_class_cost_control(
    group: S3ResourceGroup, primary: ParsedResourceChange
) -> ControlResult:
    related = group.related.get("aws_s3_bucket_lifecycle_configuration")
    rule = _dict_value(related.after, "rule") if related is not None else None
    status = ControlStatus.PASSED if _has_transition(rule) else ControlStatus.NOT_APPLICABLE
    return _control(
        "s3.storage_class_cost",
        "S3 storage class cost",
        ControlCategory.COST,
        status,
        Severity.INFO,
        "S3 lifecycle rules include storage class transitions."
        if status == ControlStatus.PASSED
        else "S3 lifecycle storage class transitions are not applicable from this plan.",
        related or primary,
        "change.after.rule",
        _dict_value((related or primary).before, "rule"),
        rule,
    )


def _control(
    control_id: str,
    name: str,
    category: ControlCategory,
    status: ControlStatus,
    severity: Severity,
    message: str,
    change: ParsedResourceChange,
    relative_path: str,
    before: Any,
    after: Any,
) -> ControlResult:
    return ControlResult(
        id=control_id,
        name=name,
        category=category,
        status=status,
        severity=severity,
        message=message,
        evidence=EvidencePointer(
            path=f"resource_changes[{change.index}].{relative_path}",
            before=before,
            after=after,
        ),
    )


def _dict_value(value: Any, key: str) -> Any:
    if not isinstance(value, dict):
        return None
    return value.get(key)


def _has_value(value: Any) -> bool:
    return bool(value)


def _versioning_enabled(configuration: Any) -> bool:
    if isinstance(configuration, dict):
        return configuration.get("status") == "Enabled"
    if isinstance(configuration, list):
        return any(
            isinstance(item, dict) and item.get("status") == "Enabled" for item in configuration
        )
    return False


def _has_transition(rules: Any) -> bool:
    if isinstance(rules, dict):
        return _has_value(rules.get("transition"))
    if isinstance(rules, list):
        return any(isinstance(rule, dict) and _has_value(rule.get("transition")) for rule in rules)
    return False


def _policy_allows_public_principal(policy: dict[str, Any]) -> bool:
    statements = policy.get("Statement", [])
    if isinstance(statements, dict):
        statements = [statements]
    if not isinstance(statements, list):
        return False

    for statement in statements:
        if not isinstance(statement, dict):
            continue
        if statement.get("Effect") == "Allow" and _principal_is_public(statement.get("Principal")):
            return True
    return False


def _principal_is_public(principal: Any) -> bool:
    if principal == "*":
        return True
    if isinstance(principal, dict):
        return any(
            value == "*" or (isinstance(value, list) and "*" in value)
            for value in principal.values()
        )
    return False
