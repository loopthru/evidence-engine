from dataclasses import dataclass
from typing import Any

from evidence_engine.exceptions import InvalidTerraformPlanError


@dataclass(frozen=True)
class ParsedResourceChange:
    index: int
    address: str
    type: str
    name: str
    provider: str | None
    actions: list[str]
    before: Any
    after: Any
    after_unknown: Any
    raw: dict[str, Any]


def parse_plan(plan: dict[str, Any]) -> list[ParsedResourceChange]:
    resource_changes = plan.get("resource_changes")
    if not isinstance(resource_changes, list):
        raise InvalidTerraformPlanError("Terraform plan JSON must include a resource_changes array.")

    parsed: list[ParsedResourceChange] = []
    for index, resource_change in enumerate(resource_changes):
        if not isinstance(resource_change, dict):
            raise InvalidTerraformPlanError(f"resource_changes[{index}] must be an object.")

        change = resource_change.get("change")
        if not isinstance(change, dict):
            raise InvalidTerraformPlanError(f"resource_changes[{index}] must include a change object.")

        address = _required_string(resource_change, "address", index)
        resource_type = _required_string(resource_change, "type", index)
        name = _required_string(resource_change, "name", index)

        actions = change.get("actions", [])
        if not isinstance(actions, list):
            raise InvalidTerraformPlanError(
                f"resource_changes[{index}].change.actions must be an array."
            )
        if not all(isinstance(action, str) for action in actions):
            raise InvalidTerraformPlanError(
                f"resource_changes[{index}].change.actions must contain only strings."
            )

        parsed.append(
            ParsedResourceChange(
                index=index,
                address=address,
                type=resource_type,
                name=name,
                provider=_provider_short_name(resource_change.get("provider_name")),
                actions=[str(action) for action in actions],
                before=change.get("before"),
                after=change.get("after"),
                after_unknown=change["after_unknown"] if "after_unknown" in change else {},
                raw=resource_change,
            )
        )

    return parsed


def _provider_short_name(provider_name: Any) -> str | None:
    if not isinstance(provider_name, str) or not provider_name:
        return None
    return provider_name.rsplit("/", maxsplit=1)[-1]


def _required_string(resource_change: dict[str, Any], field: str, index: int) -> str:
    value = resource_change.get(field)
    if not isinstance(value, str) or not value:
        raise InvalidTerraformPlanError(f"resource_changes[{index}].{field} must be a non-empty string.")
    return value
