"""Tests for the detectors, over generated adversarial documents."""

from collections.abc import Callable
from pathlib import Path

import pytest

from palimpsest.integrity.detectors.base import EVIDENCE_MAX_CHARS, Detector
from palimpsest.integrity.detectors.invisible_text import InvisibleTextDetector
from palimpsest.integrity.detectors.tiny_text import TinyTextDetector
from palimpsest.integrity.extract import extract_glyphs, group_runs
from palimpsest.report.model import Finding
from tests.fixtures.generate import (
    HIDDEN_MARKER,
    TINY_MARKER,
    both_pdf,
    clean_pdf,
    invisible_text_pdf,
    tiny_text_pdf,
)

INVISIBLE = "invisible_render_mode"
SUB_LEGIBLE = "sub_legible_font_size"

ALL_FIXTURES = [clean_pdf, invisible_text_pdf, tiny_text_pdf, both_pdf]


def _detectors() -> list[Detector]:
    return [InvisibleTextDetector(), TinyTextDetector()]


def _scan(path: Path) -> tuple[list[Finding], str]:
    """Return every finding for a document, and the document's own text."""
    runs = group_runs(extract_glyphs(str(path)))
    findings = [finding for detector in _detectors() for finding in detector.run(runs)]
    return findings, "".join(run.text for run in runs)


def _names(findings: list[Finding]) -> list[str]:
    return [finding.detector for finding in findings]


def test_invisible_text_pdf_yields_exactly_one_invisible_finding(tmp_path: Path) -> None:
    findings, _ = _scan(invisible_text_pdf(tmp_path))
    assert _names(findings).count(INVISIBLE) == 1


def test_invisible_finding_quotes_the_marker(tmp_path: Path) -> None:
    findings, _ = _scan(invisible_text_pdf(tmp_path))
    invisible = [f for f in findings if f.detector == INVISIBLE]
    assert HIDDEN_MARKER in invisible[0].evidence


def test_tiny_text_pdf_yields_a_sub_legible_finding(tmp_path: Path) -> None:
    findings, _ = _scan(tiny_text_pdf(tmp_path))
    sub_legible = [f for f in findings if f.detector == SUB_LEGIBLE]
    assert len(sub_legible) == 1
    assert TINY_MARKER in sub_legible[0].evidence


def test_clean_pdf_yields_no_findings_at_all(tmp_path: Path) -> None:
    """A detector that fires on a clean document is worse than one that never
    fires: the first teaches the reader to ignore the output."""
    findings, _ = _scan(clean_pdf(tmp_path))
    assert findings == []


def test_both_pdf_yields_one_finding_of_each_kind(tmp_path: Path) -> None:
    findings, _ = _scan(both_pdf(tmp_path))
    assert _names(findings).count(INVISIBLE) == 1
    assert _names(findings).count(SUB_LEGIBLE) == 1


@pytest.mark.parametrize("detector", _detectors(), ids=lambda d: str(d.name))
def test_detector_on_empty_runs_returns_empty_list(detector: Detector) -> None:
    assert detector.run([]) == []


@pytest.mark.parametrize("make_pdf", ALL_FIXTURES, ids=lambda f: str(f.__name__))
def test_evidence_appears_verbatim_in_the_document(
    make_pdf: Callable[[Path], Path], tmp_path: Path
) -> None:
    """Everything else here checks that a finding was found. This checks that
    what it quotes is really in the file, which is what the tool rests on.

    Evidence longer than the limit carries its truncation marker and is not a
    complete quotation, so only untruncated evidence is compared.
    """
    findings, document_text = _scan(make_pdf(tmp_path))
    for finding in findings:
        if len(finding.evidence) <= EVIDENCE_MAX_CHARS:
            assert finding.evidence in document_text
