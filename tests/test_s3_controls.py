import json

from evidence_engine.controls.s3 import build_s3_resource_evidence, group_s3_changes
from evidence_engine.plan_parser import parse_plan


def test_group_s3_changes_combines_bucket_related_resources_by_bucket_name():
    changes = parse_plan(
        {
            "resource_changes": [
                {
                    "address": "aws_s3_bucket.customer_data",
                    "type": "aws_s3_bucket",
                    "name": "customer_data",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {"bucket": "customer-data-prod"},
                    },
                },
                {
                    "address": "aws_s3_bucket_versioning.customer_data",
                    "type": "aws_s3_bucket_versioning",
                    "name": "customer_data",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {
                            "bucket": "customer-data-prod",
                            "versioning_configuration": [{"status": "Enabled"}],
                        },
                    },
                },
            ]
        }
    )

    groups = group_s3_changes(changes)

    assert list(groups) == ["aws_s3_bucket.customer_data"]
    group = groups["aws_s3_bucket.customer_data"]
    assert group.bucket_change.address == "aws_s3_bucket.customer_data"
    assert (
        group.related["aws_s3_bucket_versioning"].address
        == "aws_s3_bucket_versioning.customer_data"
    )


def test_group_s3_changes_creates_unresolved_group_for_unmatched_related_resource():
    changes = parse_plan(
        {
            "resource_changes": [
                {
                    "address": "aws_s3_bucket_policy.orphan",
                    "type": "aws_s3_bucket_policy",
                    "name": "orphan",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {"bucket": "missing-bucket", "policy": "{}"},
                    },
                }
            ]
        }
    )

    groups = group_s3_changes(changes)

    assert list(groups) == ["unresolved:aws_s3_bucket_policy.orphan"]
    group = groups["unresolved:aws_s3_bucket_policy.orphan"]
    assert group.bucket_change is None
    assert group.related["aws_s3_bucket_policy"].address == "aws_s3_bucket_policy.orphan"


def test_group_s3_changes_matches_related_resource_by_before_bucket():
    changes = parse_plan(
        {
            "resource_changes": [
                {
                    "address": "aws_s3_bucket.customer_data",
                    "type": "aws_s3_bucket",
                    "name": "customer_data",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["update"],
                        "before": {"bucket": "customer-data-prod"},
                        "after": {"bucket": "customer-data-prod"},
                    },
                },
                {
                    "address": "aws_s3_bucket_public_access_block.customer_data",
                    "type": "aws_s3_bucket_public_access_block",
                    "name": "customer_data",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["delete"],
                        "before": {"bucket": "customer-data-prod", "block_public_acls": True},
                        "after": None,
                    },
                },
            ]
        }
    )

    group = group_s3_changes(changes)["aws_s3_bucket.customer_data"]

    assert (
        group.related["aws_s3_bucket_public_access_block"].address
        == "aws_s3_bucket_public_access_block.customer_data"
    )


def test_group_s3_changes_matches_bucket_and_related_resource_by_id_fallback():
    changes = parse_plan(
        {
            "resource_changes": [
                {
                    "address": "aws_s3_bucket.logs",
                    "type": "aws_s3_bucket",
                    "name": "logs",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {"id": "logs-prod"},
                    },
                },
                {
                    "address": "aws_s3_bucket_lifecycle_configuration.logs",
                    "type": "aws_s3_bucket_lifecycle_configuration",
                    "name": "logs",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {"id": "logs-prod", "rule": []},
                    },
                },
            ]
        }
    )

    group = group_s3_changes(changes)["aws_s3_bucket.logs"]

    assert (
        group.related["aws_s3_bucket_lifecycle_configuration"].address
        == "aws_s3_bucket_lifecycle_configuration.logs"
    )


def test_group_s3_changes_returns_groups_in_deterministic_key_order():
    changes = parse_plan(
        {
            "resource_changes": [
                {
                    "address": "aws_s3_bucket.zeta",
                    "type": "aws_s3_bucket",
                    "name": "zeta",
                    "change": {"actions": ["create"], "before": None, "after": {"bucket": "zeta"}},
                },
                {
                    "address": "aws_s3_bucket.alpha",
                    "type": "aws_s3_bucket",
                    "name": "alpha",
                    "change": {"actions": ["create"], "before": None, "after": {"bucket": "alpha"}},
                },
            ]
        }
    )

    assert list(group_s3_changes(changes)) == ["aws_s3_bucket.alpha", "aws_s3_bucket.zeta"]


def test_group_s3_changes_keeps_last_same_type_related_resource_for_bucket():
    changes = parse_plan(
        {
            "resource_changes": [
                {
                    "address": "aws_s3_bucket.customer_data",
                    "type": "aws_s3_bucket",
                    "name": "customer_data",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {"bucket": "customer-data-prod"},
                    },
                },
                {
                    "address": "aws_s3_bucket_policy.first",
                    "type": "aws_s3_bucket_policy",
                    "name": "first",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {"bucket": "customer-data-prod", "policy": "{}"},
                    },
                },
                {
                    "address": "aws_s3_bucket_policy.second",
                    "type": "aws_s3_bucket_policy",
                    "name": "second",
                    "change": {
                        "actions": ["update"],
                        "before": {"bucket": "customer-data-prod", "policy": "{}"},
                        "after": {"bucket": "customer-data-prod", "policy": "{}"},
                    },
                },
            ]
        }
    )

    group = group_s3_changes(changes)["aws_s3_bucket.customer_data"]

    assert group.related["aws_s3_bucket_policy"].address == "aws_s3_bucket_policy.second"


def test_build_s3_resource_evidence_reports_missing_controls_for_plain_bucket_create():
    changes = parse_plan(
        {
            "resource_changes": [
                {
                    "address": "aws_s3_bucket.customer_data",
                    "type": "aws_s3_bucket",
                    "name": "customer_data",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {"bucket": "customer-data-prod"},
                    },
                }
            ]
        }
    )
    group = group_s3_changes(changes)["aws_s3_bucket.customer_data"]

    evidence = build_s3_resource_evidence(group)

    assert [control.id for control in evidence.controls] == [
        "s3.encryption",
        "s3.public_access_block",
        "s3.bucket_policy_exposure",
        "s3.versioning",
        "s3.lifecycle",
        "s3.storage_class_cost",
    ]
    controls = {control.id: control for control in evidence.controls}
    assert controls["s3.encryption"].status == "missing"
    assert controls["s3.public_access_block"].severity == "high"
    assert controls["s3.bucket_policy_exposure"].status == "unknown"
    assert controls["s3.versioning"].severity == "medium"
    assert controls["s3.lifecycle"].severity == "low"
    assert controls["s3.storage_class_cost"].severity == "info"


def test_build_s3_resource_evidence_passes_safe_related_controls():
    changes = parse_plan(
        {
            "resource_changes": [
                {
                    "address": "aws_s3_bucket.customer_data",
                    "type": "aws_s3_bucket",
                    "name": "customer_data",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {"bucket": "customer-data-prod"},
                    },
                },
                {
                    "address": "aws_s3_bucket_server_side_encryption_configuration.customer_data",
                    "type": "aws_s3_bucket_server_side_encryption_configuration",
                    "name": "customer_data",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {"bucket": "customer-data-prod", "rule": [{}]},
                    },
                },
                {
                    "address": "aws_s3_bucket_public_access_block.customer_data",
                    "type": "aws_s3_bucket_public_access_block",
                    "name": "customer_data",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {
                            "bucket": "customer-data-prod",
                            "block_public_acls": True,
                            "block_public_policy": True,
                            "ignore_public_acls": True,
                            "restrict_public_buckets": True,
                        },
                    },
                },
                {
                    "address": "aws_s3_bucket_versioning.customer_data",
                    "type": "aws_s3_bucket_versioning",
                    "name": "customer_data",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {
                            "bucket": "customer-data-prod",
                            "versioning_configuration": [{"status": "Enabled"}],
                        },
                    },
                },
                {
                    "address": "aws_s3_bucket_lifecycle_configuration.customer_data",
                    "type": "aws_s3_bucket_lifecycle_configuration",
                    "name": "customer_data",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {
                            "bucket": "customer-data-prod",
                            "rule": [{"transition": [{"storage_class": "STANDARD_IA"}]}],
                        },
                    },
                },
                {
                    "address": "aws_s3_bucket_policy.customer_data",
                    "type": "aws_s3_bucket_policy",
                    "name": "customer_data",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {
                            "bucket": "customer-data-prod",
                            "policy": json.dumps(
                                {
                                    "Statement": [
                                        {
                                            "Effect": "Allow",
                                            "Principal": {
                                                "AWS": "arn:aws:iam::123456789012:role/App"
                                            },
                                            "Action": "s3:GetObject",
                                            "Resource": "*",
                                        }
                                    ]
                                }
                            ),
                        },
                    },
                },
            ]
        }
    )
    group = group_s3_changes(changes)["aws_s3_bucket.customer_data"]

    evidence = build_s3_resource_evidence(group)

    assert {control.id: control.status for control in evidence.controls} == {
        "s3.encryption": "passed",
        "s3.public_access_block": "passed",
        "s3.bucket_policy_exposure": "passed",
        "s3.versioning": "passed",
        "s3.lifecycle": "passed",
        "s3.storage_class_cost": "passed",
    }


def test_build_s3_resource_evidence_reports_public_bucket_policy_exposure():
    changes = parse_plan(
        {
            "resource_changes": [
                {
                    "address": "aws_s3_bucket.customer_data",
                    "type": "aws_s3_bucket",
                    "name": "customer_data",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {"bucket": "customer-data-prod"},
                    },
                },
                {
                    "address": "aws_s3_bucket_policy.customer_data",
                    "type": "aws_s3_bucket_policy",
                    "name": "customer_data",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {
                            "bucket": "customer-data-prod",
                            "policy": json.dumps(
                                {
                                    "Statement": {
                                        "Effect": "Allow",
                                        "Principal": "*",
                                        "Action": "s3:*",
                                        "Resource": "*",
                                    }
                                }
                            ),
                        },
                    },
                },
            ]
        }
    )
    group = group_s3_changes(changes)["aws_s3_bucket.customer_data"]

    controls = {control.id: control for control in build_s3_resource_evidence(group).controls}

    assert controls["s3.bucket_policy_exposure"].status == "missing"
    assert controls["s3.bucket_policy_exposure"].severity == "high"
