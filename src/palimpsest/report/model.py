"""Data structures of the Palimpsest-doc report. No logic, no serialisation yet."""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Finding:
    """A single detection."""

    detector: str
    severity: str
    location: str
    evidence: str
    explanation: str


@dataclass
class SourceDocument:
    """The file the report is about."""

    path: str
    sha256: str
    size_bytes: int
    media_type: str


@dataclass
class Report:
    """The protocol produced for one document."""

    source: SourceDocument
    tool_version: str
    created_at: str  # ISO 8601, UTC
    findings: list[Finding] = field(default_factory=list)
    parser_versions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
