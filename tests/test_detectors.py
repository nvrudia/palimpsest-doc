"""Tests for the detectors, over generated adversarial documents."""

from collections.abc import Callable
from pathlib import Path

import pytest

from palimpsest.cli import build_detectors
from palimpsest.integrity.detectors.base import EVIDENCE_MAX_CHARS, Detector
from palimpsest.integrity.extract import extract_glyphs, group_runs
from palimpsest.report.model import Finding
from tests.fixtures.generate import (
    BACKGROUND_MARKER,
    HIDDEN_MARKER,
    OUTSIDE_MARKER,
    TINY_MARKER,
    background_color_pdf,
    both_pdf,
    clean_pdf,
    invisible_text_pdf,
    outside_page_pdf,
    tiny_text_pdf,
)

INVISIBLE = "invisible_render_mode"
SUB_LEGIBLE = "sub_legible_font_size"
BACKGROUND = "text_color_matches_background"
OUTSIDE = "text_outside_page_area"

ALL_FIXTURES = [
    clean_pdf,
    invisible_text_pdf,
    tiny_text_pdf,
    background_color_pdf,
    outside_page_pdf,
    both_pdf,
]

# The list the command line builds, not a copy of it. A detector added to the
# tool but forgotten here would otherwise leave the clean-document test passing
# while covering one fewer detector than it claims to.
DETECTOR_COUNT = 4


def _detectors(path: Path) -> list[Detector]:
    return build_detectors(str(path))


def _scan(path: Path) -> tuple[list[Finding], str]:
    """Return every finding for a document, and the document's own text."""
    runs = group_runs(extract_glyphs(str(path)))
    findings = [finding for detector in _detectors(path) for finding in detector.run(runs)]
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
    fires: the first teaches the reader to ignore the output.

    Every detector the tool ships has to stay silent here, not merely the ones
    this file happens to name, so the list comes from the command line itself.
    """
    path = clean_pdf(tmp_path)
    assert len(_detectors(path)) == DETECTOR_COUNT
    findings, _ = _scan(path)
    assert findings == []


def test_background_color_pdf_yields_exactly_one_finding(tmp_path: Path) -> None:
    findings, _ = _scan(background_color_pdf(tmp_path))
    background = [f for f in findings if f.detector == BACKGROUND]
    assert len(background) == 1
    assert BACKGROUND_MARKER in background[0].evidence
    assert _names(findings) == [BACKGROUND]


def test_outside_page_pdf_yields_exactly_one_finding(tmp_path: Path) -> None:
    findings, _ = _scan(outside_page_pdf(tmp_path))
    outside = [f for f in findings if f.detector == OUTSIDE]
    assert len(outside) == 1
    assert OUTSIDE_MARKER in outside[0].evidence
    assert _names(findings) == [OUTSIDE]


def test_both_pdf_yields_one_finding_of_each_kind(tmp_path: Path) -> None:
    findings, _ = _scan(both_pdf(tmp_path))
    assert _names(findings).count(INVISIBLE) == 1
    assert _names(findings).count(SUB_LEGIBLE) == 1


@pytest.mark.parametrize("detector", build_detectors("no such file.pdf"), ids=lambda d: str(d.name))
def test_detector_on_empty_runs_returns_empty_list(detector: Detector) -> None:
    """A document with no text is not an error, and reads no file to find out.

    The path given here does not exist. Two of these detectors open the document
    when they have a run to measure; with nothing to measure they must not touch
    it at all, and this test fails loudly if that ever changes.
    """
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
