"""Tests for the coverage statement carried by every report.

The point of the block is the report that finds nothing. "No findings" and "not
examined" are indistinguishable to a reader unless the second is written down,
and the legal analysis this came from calls a report without stated limits
insufficient. These tests hold the distinction in place.
"""

from pathlib import Path

import pypdfium2 as pdfium
import pytest
from reportlab.lib import pdfencrypt
from reportlab.pdfgen import canvas

from palimpsest.cli import build_detectors, format_report
from palimpsest.report.build import (
    NO_TEXT_LAYER,
    NOT_CHECKED,
    OWNER_PASSWORD_NOTE,
    ROTATED_NO_TEXT_LAYER,
    build_report,
)
from palimpsest.report.model import Report
from tests.fixtures.generate import (
    BODY_FONT_SIZE,
    FONT_NAME,
    PAGE_SIZE,
    VISIBLE_PARAGRAPH,
    both_pdf,
    clean_pdf,
)


def _scan(path: Path) -> Report:
    return build_report(str(path), build_detectors(str(path)))


def _text(c: canvas.Canvas, y: float = 720.0) -> None:
    text_object = c.beginText(72, y)
    text_object.setFont(FONT_NAME, BODY_FONT_SIZE)
    text_object.textLine(VISIBLE_PARAGRAPH)
    c.drawText(text_object)


def _ink_only(c: canvas.Canvas) -> None:
    """A page that carries marks but no text, so it yields no runs."""
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.rect(100, 100, 400, 500, stroke=0, fill=1)


def test_report_without_findings_still_states_its_coverage(tmp_path: Path) -> None:
    report = _scan(clean_pdf(tmp_path))
    assert report.findings == []
    assert report.coverage.pages_total == 1
    assert report.coverage.pages_analysed == 1
    assert report.coverage.not_checked == list(NOT_CHECKED)
    assert "Coverage" in format_report(report)


def test_detectors_run_names_the_detectors_that_actually_ran(tmp_path: Path) -> None:
    """Taken from the detectors themselves rather than from a list written out
    here, which would go on being right in the report after going wrong in the
    tool."""
    path = both_pdf(tmp_path)
    detectors = build_detectors(str(path))
    report = build_report(str(path), detectors)
    assert report.coverage.detectors_run == [detector.name for detector in detectors]


def test_a_subset_of_detectors_is_reported_as_such(tmp_path: Path) -> None:
    path = both_pdf(tmp_path)
    one = build_detectors(str(path))[:1]
    assert build_report(str(path), one).coverage.detectors_run == [one[0].name]


def test_page_without_a_text_layer_is_reported_as_skipped(tmp_path: Path) -> None:
    path = tmp_path / "second_page_blank.pdf"
    c = canvas.Canvas(str(path), pagesize=PAGE_SIZE)
    _text(c)
    c.showPage()
    _ink_only(c)
    c.showPage()
    c.save()
    coverage = _scan(path).coverage
    assert coverage.pages_total == 2
    assert coverage.pages_analysed == 1
    assert [(s.page, s.reason) for s in coverage.pages_skipped] == [(2, NO_TEXT_LAYER)]


def test_rotated_page_without_text_is_reported_as_skipped(tmp_path: Path) -> None:
    """The gap this block was written for.

    A rotated page is refused outright when it carries text, because only some
    of the checks could examine it. A rotated page carrying none was refused by
    nothing: no run ever pointed at it, so the renderer was never asked about
    it, and the document was reported clean with that page unexamined.
    """
    plain = tmp_path / "plain.pdf"
    c = canvas.Canvas(str(plain), pagesize=PAGE_SIZE)
    _text(c)
    c.showPage()
    _ink_only(c)
    c.showPage()
    c.save()

    path = tmp_path / "rotated_second_page.pdf"
    document = pdfium.PdfDocument(str(plain))
    try:
        document[1].set_rotation(90)
        document.save(str(path))
    finally:
        document.close()

    coverage = _scan(path).coverage
    assert coverage.pages_total == 2
    assert coverage.pages_analysed == 1
    assert [(s.page, s.reason) for s in coverage.pages_skipped] == [(2, ROTATED_NO_TEXT_LAYER)]
    assert f"page skipped:    2 ({ROTATED_NO_TEXT_LAYER})" in format_report(_scan(path))


def test_rotated_page_carrying_text_still_refuses_the_whole_scan(tmp_path: Path) -> None:
    """Coverage reports limits; it does not turn a refusal into a partial scan."""
    plain = tmp_path / "plain.pdf"
    c = canvas.Canvas(str(plain), pagesize=PAGE_SIZE)
    _text(c)
    c.showPage()
    c.save()
    path = tmp_path / "rotated.pdf"
    document = pdfium.PdfDocument(str(plain))
    try:
        document[0].set_rotation(90)
        document.save(str(path))
    finally:
        document.close()
    with pytest.raises(ValueError, match="known limitation"):
        _scan(path)


def test_owner_password_encryption_is_recorded_as_a_note(tmp_path: Path) -> None:
    """The file opens without a password, so the scan proceeds; the restrictions
    it declares are owner restrictions, which this tool neither reads nor acts
    on. Saying so is the difference between a limit stated and a limit hidden."""
    path = tmp_path / "owner_password.pdf"
    encryption = pdfencrypt.StandardEncryption("", ownerPassword="owner", canPrint=0)
    c = canvas.Canvas(str(path), pagesize=PAGE_SIZE, encrypt=encryption)
    _text(c)
    c.showPage()
    c.save()
    report = _scan(path)
    assert report.coverage.notes == [OWNER_PASSWORD_NOTE]
    assert OWNER_PASSWORD_NOTE in format_report(report)


def test_an_unencrypted_document_carries_no_notes(tmp_path: Path) -> None:
    assert _scan(clean_pdf(tmp_path)).coverage.notes == []


def test_coverage_is_serialised_into_the_json_report(tmp_path: Path) -> None:
    data = _scan(clean_pdf(tmp_path)).to_dict()
    # The field is last, so every key that reports already carried keeps its
    # place: a consumer comparing two reports line by line is not disturbed.
    assert list(data)[-1] == "coverage"
    assert set(data["coverage"]) == {
        "detectors_run",
        "pages_total",
        "pages_analysed",
        "pages_skipped",
        "not_checked",
        "notes",
    }
