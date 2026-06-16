from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "2026-06-16.mvp.v1"


class ChangeAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    NO_OP = "no-op"
    READ = "read"


class ControlCategory(StrEnum):
    SECURITY = "security"
    RELIABILITY = "reliability"
    COST = "cost"
    COMPLIANCE = "compliance"
    PLATFORM = "platform"


class ControlStatus(StrEnum):
    PASSED = "passed"
    MISSING = "missing"
    CHANGED = "changed"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class EvidencePointer(BaseModel):
    source: str = "terraform_plan"
    path: str
    before: Any = None
    after: Any = None


class ControlResult(BaseModel):
    id: str
    name: str
    category: ControlCategory
    status: ControlStatus
    severity: Severity
    message: str
    evidence: EvidencePointer


class ResourceEvidence(BaseModel):
    address: str
    type: str
    name: str
    provider: str | None = None
    change_actions: list[ChangeAction]
    before: Any = None
    after: Any = None
    controls: list[ControlResult]


class EngineInfo(BaseModel):
    name: str = "loopthru-evidence-engine"
    version: str


class ReportSummary(BaseModel):
    resources_total: int
    resources_evaluated: int
    resources_unsupported: int
    findings_by_severity: dict[Severity, int] = Field(
        default_factory=lambda: {
            Severity.CRITICAL: 0,
            Severity.HIGH: 0,
            Severity.MEDIUM: 0,
            Severity.LOW: 0,
            Severity.INFO: 0,
        }
    )


class EvidenceReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: str = SCHEMA_VERSION
    engine: EngineInfo
    summary: ReportSummary
    resources: list[ResourceEvidence]
