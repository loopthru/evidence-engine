import json
from pathlib import Path
from typing import Annotated

import typer

from evidence_engine.engine import generate_evidence
from evidence_engine.exceptions import InvalidTerraformPlanError


app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    pass


@app.command()
def plan(path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)]) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise InvalidTerraformPlanError("Terraform plan JSON must be an object.")
        report = generate_evidence(payload)
    except json.JSONDecodeError as exc:
        typer.echo(f"Invalid JSON: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except InvalidTerraformPlanError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
