import pytest

from evidence_engine.exceptions import InvalidTerraformPlanError
from evidence_engine.plan_parser import ParsedResourceChange, parse_plan


def test_parse_plan_extracts_resource_changes():
    plan = {
        "format_version": "1.2",
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
                    "after_unknown": {"arn": True},
                },
            }
        ],
    }

    parsed = parse_plan(plan)

    assert parsed == [
        ParsedResourceChange(
            index=0,
            address="aws_s3_bucket.customer_data",
            type="aws_s3_bucket",
            name="customer_data",
            provider="aws",
            actions=["create"],
            before=None,
            after={"bucket": "customer-data-prod"},
            after_unknown={"arn": True},
            raw=plan["resource_changes"][0],
        )
    ]


def test_parse_plan_rejects_missing_resource_changes():
    with pytest.raises(InvalidTerraformPlanError, match="resource_changes"):
        parse_plan({"format_version": "1.2"})


def test_parse_plan_rejects_resource_change_missing_change_block():
    with pytest.raises(InvalidTerraformPlanError, match="change"):
        parse_plan({"resource_changes": [{"address": "aws_s3_bucket.bad"}]})


def test_parse_plan_rejects_missing_identity_fields():
    with pytest.raises(InvalidTerraformPlanError, match="type"):
        parse_plan(
            {
                "resource_changes": [
                    {
                        "address": "aws_s3_bucket.bad",
                        "name": "bad",
                        "change": {"actions": ["create"]},
                    }
                ]
            }
        )


def test_parse_plan_rejects_non_string_actions():
    with pytest.raises(InvalidTerraformPlanError, match="actions"):
        parse_plan(
            {
                "resource_changes": [
                    {
                        "address": "aws_s3_bucket.bad",
                        "type": "aws_s3_bucket",
                        "name": "bad",
                        "change": {"actions": ["create", None]},
                    }
                ]
            }
        )


def test_parse_plan_preserves_present_falsy_after_unknown_value():
    plan = {
        "resource_changes": [
            {
                "address": "aws_s3_bucket.customer_data",
                "type": "aws_s3_bucket",
                "name": "customer_data",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {"bucket": "customer-data-prod"},
                    "after_unknown": None,
                },
            }
        ],
    }

    parsed = parse_plan(plan)

    assert parsed[0].after_unknown is None
