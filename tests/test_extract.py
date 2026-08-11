"""Tests for the extraction layer: characters and runs, not detectors."""

from pathlib import Path

import pytest

from palimpsest.integrity.extract import extract_glyphs, group_runs
from tests.fixtures.generate import VISIBLE_PARAGRAPH, clean_pdf


def test_clean_pdf_yields_glyphs(tmp_path: Path) -> None:
    assert extract_glyphs(str(clean_pdf(tmp_path)))


def test_every_glyph_carries_page_font_and_size(tmp_path: Path) -> None:
    for glyph in extract_glyphs(str(clean_pdf(tmp_path))):
        assert glyph.page >= 1
        assert glyph.font_name
        assert glyph.font_size > 0


def test_grouping_yields_fewer_runs_than_glyphs(tmp_path: Path) -> None:
    glyphs = extract_glyphs(str(clean_pdf(tmp_path)))
    runs = group_runs(glyphs)
    assert 0 < len(runs) < len(glyphs)


def test_run_text_contains_the_document_text(tmp_path: Path) -> None:
    runs = group_runs(extract_glyphs(str(clean_pdf(tmp_path))))
    assert VISIBLE_PARAGRAPH in "".join(run.text for run in runs)


def test_glyph_count_is_preserved_by_grouping(tmp_path: Path) -> None:
    """Grouping regroups characters; it must not drop or invent any."""
    glyphs = extract_glyphs(str(clean_pdf(tmp_path)))
    runs = group_runs(glyphs)
    assert sum(run.glyph_count for run in runs) == len(glyphs)
    assert "".join(run.text for run in runs) == "".join(glyph.text for glyph in glyphs)


def test_missing_file_raises_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        extract_glyphs(str(tmp_path / "no_such_file.pdf"))


def test_file_that_is_not_a_pdf_raises_value_error(tmp_path: Path) -> None:
    not_a_pdf = tmp_path / "plain.txt"
    not_a_pdf.write_text("This is not a PDF.", encoding="utf-8")
    with pytest.raises(ValueError):
        extract_glyphs(str(not_a_pdf))
