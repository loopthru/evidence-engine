from dataclasses import dataclass, field
from typing import Any

from evidence_engine.plan_parser import ParsedResourceChange


S3_BUCKET_TYPE = "aws_s3_bucket"
S3_RELATED_TYPES = {
    "aws_s3_bucket_server_side_encryption_configuration",
    "aws_s3_bucket_public_access_block",
    "aws_s3_bucket_versioning",
    "aws_s3_bucket_lifecycle_configuration",
    "aws_s3_bucket_policy",
}


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
