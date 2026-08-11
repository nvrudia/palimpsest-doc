"""The detector contract and the severity vocabulary.

A detector receives text runs that were already extracted and grouped, and
returns findings. It never opens the file itself. That is deliberate: a
detector can then be tested against hand-built runs, with no PDF involved and
no dependency on the parser behaving in any particular way.
"""

from typing import Protocol

from palimpsest.integrity.model import TextRun
from palimpsest.report.model import Finding

# Severity is a plain string on Finding; an enumeration would buy nothing while
# there are three values and no logic branches on them.
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

# Longest quotation carried in a finding before it is cut.
EVIDENCE_MAX_CHARS = 200


def format_evidence(text: str) -> str:
    """Quote a run's text for a finding.

    Evidence is what a person will cite as proof, so the text is reproduced
    exactly: whitespace is not normalised, quotation marks are not substituted,
    edges are not stripped. Truncation is the only permitted alteration, and it
    announces itself inside the returned string, because a silent cut produces
    a quotation the document does not contain even when the meaning survives.
    """
    if len(text) <= EVIDENCE_MAX_CHARS:
        return text
    return f"{text[:EVIDENCE_MAX_CHARS]}... [truncated, {len(text)} characters in total]"


def format_location(page: int, x0: float, y0: float, x1: float, y1: float) -> str:
    """Render a run's position for a finding, in PDF user space units."""
    return f"page {page}, bbox ({x0:.2f}, {y0:.2f}, {x1:.2f}, {y1:.2f})"


class Detector(Protocol):
    """What every detector must provide.

    A Protocol rather than an abstract base class: detectors are matched
    structurally, so nothing has to inherit from a shared parent to qualify.
    """

    name: str

    def run(self, runs: list[TextRun]) -> list[Finding]: ...
