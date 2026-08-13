"""Pixel evidence: what the extraction layer claims, checked against a renderer.

Every other test in this suite reads the document through pdfminer and compares
the result with an expectation also derived from pdfminer. That is a closed
loop. These tests break it: the documents are rasterised by PDFium, which shares
no code with pdfminer, and the question asked of the raster -- how many pixels
did this fragment paint -- is answered without consulting the text layer at all.

The counts here are measurements. If a render mode ever behaves differently, the
right response is to report the divergence between the specification and the
renderer, not to adjust the expectation until the suite passes again.
"""

from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from palimpsest.integrity.detectors.base import format_location
from palimpsest.integrity.detectors.invisible_text import InvisibleTextDetector
from palimpsest.integrity.extract import extract_glyphs, group_runs
from palimpsest.integrity.model import TextRun
from palimpsest.integrity.render import painted_pixels
from tests.fixtures.generate import BODY_FONT_SIZE, FONT_NAME, PAGE_SIZE, invisible_text_pdf

MODE_MARKER = "RENDER MODE SAMPLE"
BASELINE = 700.0

# What the PDF specification says each text render mode puts on the page. Modes
# 4 to 6 add the glyphs to the clipping path in addition to filling or stroking
# them, which leaves them visible; mode 7 only clips, and mode 3 does nothing at
# all.
PAINTS = {0: True, 1: True, 2: True, 3: False, 4: True, 5: True, 6: True, 7: False}


def _render_mode_pdf(directory: Path, mode: int) -> Path:
    """A page carrying one fragment, drawn in one render mode.

    One fragment per document rather than eight bands on one page: a mode that
    misbehaves then cannot be blamed on the fragment above it.

    The fragment is wrapped in saveState/restoreState even at mode 0. The
    wrapping is mandatory for modes 4 to 7, which leave the glyphs in the
    clipping path after the text object ends, so anything drawn afterwards is
    erased; applying it uniformly means no fragment is a special case.
    """
    path = Path(directory) / f"render_mode_{mode}.pdf"
    c = canvas.Canvas(str(path), pagesize=PAGE_SIZE)
    c.saveState()
    text_object = c.beginText(72, BASELINE)
    text_object.setFont(FONT_NAME, BODY_FONT_SIZE)
    text_object.setTextRenderMode(mode)
    text_object.textLine(MODE_MARKER)
    c.drawText(text_object)
    c.restoreState()
    c.showPage()
    c.save()
    return path


def _single_run(path: Path) -> TextRun:
    runs = group_runs(extract_glyphs(str(path)))
    assert len(runs) == 1, f"expected one run in {path.name}, parsed {len(runs)}"
    return runs[0]


def _box(run: TextRun) -> tuple[float, float, float, float]:
    return (run.x0, run.y0, run.x1, run.y1)


@pytest.mark.parametrize("mode", sorted(PAINTS), ids=lambda mode: f"mode{mode}")
def test_render_mode_paints_what_the_specification_says(mode: int, tmp_path: Path) -> None:
    """Each of the eight render modes, measured against a real renderer.

    The parsed mode is asserted first. reportlab has been caught emitting no Tr
    operator at all for a requested mode, and a fixture that quietly carries the
    wrong mode would make the pixel count below a measurement of something else.
    """
    path = _render_mode_pdf(tmp_path, mode)
    run = _single_run(path)
    assert run.render_mode == mode

    painted = painted_pixels(str(path), 1, _box(run))
    if PAINTS[mode]:
        assert painted > 0, f"mode {mode} should paint, but its box is empty"
    else:
        assert painted == 0, f"mode {mode} should paint nothing, but its box holds {painted} pixels"


def test_invisible_detector_agrees_with_the_renderer(tmp_path: Path) -> None:
    """The detector's verdict, checked against pixels rather than against itself.

    This is the test the fixtures' own self-verification cannot be: that check
    reads the file through the same extraction layer it is meant to guard, so a
    misreading shared by both would satisfy it. Here the two readings are
    independent, and they have to agree in both directions -- a flagged fragment
    paints nothing, and an unflagged one paints something.
    """
    path = invisible_text_pdf(tmp_path)
    runs = group_runs(extract_glyphs(str(path)))
    flagged = {finding.location for finding in InvisibleTextDetector().run(runs)}
    assert flagged, "the fixture is supposed to contain hidden text"

    for run in runs:
        if not run.text.strip():
            # A run of spaces paints nothing whatever its render mode, so it
            # says nothing about whether the detector was right.
            continue
        location = format_location(run.page, run.x0, run.y0, run.x1, run.y1)
        painted = painted_pixels(str(path), 1, _box(run))
        if location in flagged:
            assert painted == 0, f"{run.text!r} was reported invisible but painted {painted} pixels"
        else:
            assert painted > 0, f"{run.text!r} was left alone but painted nothing"
