import json
from pathlib import Path

from typer.testing import CliRunner

from evidence_engine.cli import app

runner = CliRunner()


def test_cli_plan_outputs_evidence_json_for_fixture():
    fixture = Path("tests/fixtures/s3_missing_controls.json")

    result = runner.invoke(app, ["plan", str(fixture)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "2026-06-16.mvp.v1"
    assert payload["summary"]["resources_total"] == 1


def test_cli_plan_returns_error_for_unrecognized_plan(tmp_path):
    bad_plan = tmp_path / "bad.json"
    bad_plan.write_text('{"hello": "world"}', encoding="utf-8")

    result = runner.invoke(app, ["plan", str(bad_plan)])

    assert result.exit_code == 1
    assert "resource_changes" in result.stderr


def test_cli_plan_returns_error_for_non_object_json(tmp_path):
    bad_plan = tmp_path / "bad.json"
    bad_plan.write_text("[]", encoding="utf-8")

    result = runner.invoke(app, ["plan", str(bad_plan)])

    assert result.exit_code == 1
    assert "Terraform plan JSON must be an object." in result.stderr
