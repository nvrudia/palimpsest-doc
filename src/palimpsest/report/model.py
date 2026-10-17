"""Data structures of the Palimpsest-doc report, and its JSON serialisation."""

import json
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
class SkippedPage:
    """A page no detector examined, and why."""

    page: int
    reason: str


@dataclass
class Coverage:
    """What the scan covered, and what it did not.

    A report that lists only findings cannot be relied on: "nothing was found"
    and "nothing was looked for" read identically. This block separates them, so
    that a reader can see which pages were examined, which detectors ran, and
    which kinds of content the tool does not inspect at all.

    The entries in not_checked are facts about this tool, not about the document
    in hand. They are the same in every report, because the limits of the check
    do not depend on what is being checked.
    """

    detectors_run: list[str] = field(default_factory=list)
    pages_total: int = 0
    pages_analysed: int = 0
    pages_skipped: list[SkippedPage] = field(default_factory=list)
    not_checked: list[str] = field(default_factory=list)
    # Observations about this particular document that limit the check without
    # stopping it. Empty when there are none.
    notes: list[str] = field(default_factory=list)


@dataclass
class Report:
    """The protocol produced for one document."""

    source: SourceDocument
    tool_version: str
    created_at: str  # ISO 8601, UTC
    findings: list[Finding] = field(default_factory=list)
    parser_versions: dict[str, str] = field(default_factory=dict)
    # Last, and with a default, so that the keys already present in reports
    # written before this field existed keep their place and their order.
    coverage: Coverage = field(default_factory=Coverage)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialise the report as JSON.

        Keys keep the order the fields are declared in, which asdict preserves
        and json.dumps does not disturb, so two reports on one document are
        comparable line by line.

        ensure_ascii is off deliberately: evidence is quoted verbatim from the
        document, and a Ukrainian contract escaped into \\uXXXX sequences would
        be unreadable to the person meant to check the quotation against the
        original.
        """
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
