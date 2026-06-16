class EvidenceEngineError(Exception):
    """Base exception for evidence engine domain errors."""


class InvalidTerraformPlanError(EvidenceEngineError):
    """Raised when input JSON is not recognizable Terraform plan JSON."""
