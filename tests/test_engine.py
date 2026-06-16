from evidence_engine.engine import generate_evidence


def test_empty_plan_generates_empty_report():
    report = generate_evidence({"resource_changes": []})

    assert report.summary.resources_total == 0
    assert report.summary.resources_evaluated == 0
    assert report.summary.resources_unsupported == 0
    assert report.resources == []


def test_unsupported_resource_is_reported_not_ignored():
    report = generate_evidence(
        {
            "resource_changes": [
                {
                    "address": "aws_instance.web",
                    "type": "aws_instance",
                    "name": "web",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {"instance_type": "t3.micro"},
                    },
                }
            ]
        }
    )

    resource = report.resources[0]
    control = resource.controls[0]

    assert report.summary.resources_total == 1
    assert report.summary.resources_evaluated == 0
    assert report.summary.resources_unsupported == 1
    assert resource.address == "aws_instance.web"
    assert control.id == "resource.unsupported"
    assert control.status == "unsupported"
    assert control.severity == "info"


def test_s3_resource_is_evaluated():
    report = generate_evidence(
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

    assert report.summary.resources_total == 1
    assert report.summary.resources_evaluated == 1
    assert report.summary.resources_unsupported == 0
    assert report.resources[0].address == "aws_s3_bucket.customer_data"
    assert [control.id for control in report.resources[0].controls] == [
        "s3.encryption",
        "s3.public_access_block",
        "s3.bucket_policy_exposure",
        "s3.versioning",
        "s3.lifecycle",
        "s3.storage_class_cost",
    ]


def test_unknown_change_action_is_reported_as_unknown():
    report = generate_evidence(
        {
            "resource_changes": [
                {
                    "address": "custom_resource.example",
                    "type": "custom_resource",
                    "name": "example",
                    "change": {
                        "actions": ["migrate"],
                        "before": None,
                        "after": {"name": "example"},
                    },
                }
            ]
        }
    )

    assert report.resources[0].change_actions == ["unknown"]


def test_engine_evaluates_s3_bucket_and_unsupported_resource_together():
    report = generate_evidence(
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
                    "address": "aws_instance.web",
                    "type": "aws_instance",
                    "name": "web",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {"instance_type": "t3.micro"},
                    },
                },
            ]
        }
    )

    assert report.summary.resources_total == 2
    assert report.summary.resources_evaluated == 1
    assert report.summary.resources_unsupported == 1
    assert [resource.address for resource in report.resources] == [
        "aws_instance.web",
        "aws_s3_bucket.customer_data",
    ]
