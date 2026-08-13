"""Tests for the rendering layer itself.

Two things are checked here that nothing else can check. The first is the
mapping from page coordinates to pixels: it has to undo the vertical flip and
start from the displayed area rather than from the MediaBox, and an error in it
produces counts that look entirely plausible. The second is determinism. A count
is evidence, and evidence that changes between two readings of one unchanged
file is not evidence at all.
"""

from collections.abc import Callable
from math import ceil
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from reportlab.pdfgen import canvas

from palimpsest.integrity.extract import extract_glyphs, group_runs
from palimpsest.integrity.render import (
    page_background,
    painted_pixels,
    render_page,
    visible_area,
)

PAGE_SIZE = (612.0, 792.0)
TEXT = "RENDER LAYER SAMPLE"

# A CropBox well inside the MediaBox, and one that runs past it. The PDF
# specification says the second is intersected with the MediaBox; PDFium's
# get_cropbox reports the oversized entry unchanged, which is why the rendering
# layer does not use it.
INNER_CROP = (100.0, 100.0, 512.0, 692.0)
OVERSIZED_CROP = (-50.0, -50.0, 700.0, 900.0)

PAGE_COLOUR = (0.1, 0.1, 0.35)
PAGE_COLOUR_RENDERED = (26, 26, 89)


def _page(
    directory: Path,
    name: str = "page.pdf",
    *,
    x: float = 72.0,
    y: float = 720.0,
    background: tuple[float, float, float] | None = None,
) -> Path:
    """One line of ordinary text, optionally on a coloured page."""
    path = Path(directory) / name
    c = canvas.Canvas(str(path), pagesize=PAGE_SIZE)
    if background is not None:
        c.setFillColorRGB(*background)
        c.rect(0, 0, *PAGE_SIZE, stroke=0, fill=1)
        c.setFillColorRGB(0, 0, 0)
    text_object = c.beginText(x, y)
    text_object.setFont("Helvetica", 12)
    text_object.textLine(TEXT)
    c.drawText(text_object)
    c.showPage()
    c.save()
    return path


def _edited(
    source: Path,
    destination: Path,
    *,
    media: tuple[float, float, float, float] | None = None,
    crop: tuple[float, float, float, float] | None = None,
    rotation: int | None = None,
) -> Path:
    """Rewrite a page's boxes or rotation.

    reportlab writes neither a CropBox nor a /Rotate entry, so the documents
    these tests need are made by editing a file it produced.
    """
    document = pdfium.PdfDocument(str(source))
    try:
        page = document[0]
        if media is not None:
            page.set_mediabox(*media)
        if crop is not None:
            page.set_cropbox(*crop)
        if rotation is not None:
            page.set_rotation(rotation)
        document.save(str(destination))
    finally:
        document.close()
    return destination


def _text_box(path: Path) -> tuple[float, float, float, float]:
    """The bounding box of the line of text, as the extraction layer sees it."""
    runs = [run for run in group_runs(extract_glyphs(str(path))) if run.text.strip()]
    assert len(runs) == 1, f"expected one run in {path.name}, parsed {len(runs)}"
    run = runs[0]
    return (run.x0, run.y0, run.x1, run.y1)


def _whole_page(path: Path) -> tuple[float, float, float, float]:
    offset_x, offset_y, width, height = visible_area(str(path), 1)
    return (offset_x, offset_y, offset_x + width, offset_y + height)


@pytest.fixture
def plain(tmp_path: Path) -> Path:
    return _page(tmp_path)


def test_visible_area_of_a_plain_page(plain: Path) -> None:
    assert visible_area(str(plain), 1) == (0.0, 0.0, 612.0, 792.0)


def test_visible_area_is_relative_to_the_mediabox_origin(plain: Path, tmp_path: Path) -> None:
    """A MediaBox that does not start at the origin shifts nothing.

    pdfminer already reports glyph coordinates relative to the lower left corner
    of the MediaBox, so subtracting that corner a second time would move every
    fragment off its own ink.
    """
    shifted = _edited(plain, tmp_path / "shifted.pdf", media=(30.0, 50.0, 642.0, 842.0))
    assert visible_area(str(shifted), 1) == (0.0, 0.0, 612.0, 792.0)
    assert painted_pixels(str(shifted), 1, _text_box(shifted)) > 0


def test_visible_area_follows_the_cropbox(plain: Path, tmp_path: Path) -> None:
    cropped = _edited(plain, tmp_path / "cropped.pdf", crop=INNER_CROP)
    assert visible_area(str(cropped), 1) == (100.0, 100.0, 412.0, 592.0)


def test_visible_area_intersects_a_cropbox_larger_than_the_page(
    plain: Path, tmp_path: Path
) -> None:
    oversized = _edited(plain, tmp_path / "oversized.pdf", crop=OVERSIZED_CROP)
    assert visible_area(str(oversized), 1) == (0.0, 0.0, 612.0, 792.0)


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0, 3.0])
def test_raster_measures_the_visible_area_at_the_requested_scale(plain: Path, scale: float) -> None:
    _, _, area_width, area_height = visible_area(str(plain), 1)
    width, height, pixels = render_page(str(plain), 1, scale)
    assert (width, height) == (ceil(area_width * scale), ceil(area_height * scale))
    # Three bytes per pixel, tightly packed, no padding between rows.
    assert len(pixels) == width * height * 3


def test_painted_pixels_returns_the_same_count_twice(plain: Path) -> None:
    """Determinism is a requirement here, not a happy accident.

    Two questions about one page are answered from one raster. Were the page
    rendered twice, two findings about the same fragment could carry different
    counts, and a reader would have no way to tell which of them to believe.
    """
    box = _text_box(plain)
    first = painted_pixels(str(plain), 1, box)
    second = painted_pixels(str(plain), 1, box)
    assert first == second
    # An integer scale must reach the same raster as the float default rather
    # than becoming a second entry that renders the page again.
    assert painted_pixels(str(plain), 1, box, 2) == first


def test_the_text_box_holds_every_painted_pixel_of_the_page(plain: Path) -> None:
    """The mapping is checked against the only fragment on the page.

    A vertical flip left undone, or an origin taken from the wrong corner, moves
    the box onto blank paper and this count collapses to zero while the page
    count stays where it was.
    """
    painted = painted_pixels(str(plain), 1, _text_box(plain))
    assert painted > 0
    assert painted == painted_pixels(str(plain), 1, _whole_page(plain))


def test_painted_pixels_is_zero_outside_the_visible_area(plain: Path, tmp_path: Path) -> None:
    cropped = _edited(plain, tmp_path / "cropped.pdf", crop=INNER_CROP)
    assert painted_pixels(str(cropped), 1, _text_box(cropped)) == 0


def test_painted_pixels_of_blank_paper_is_zero(plain: Path) -> None:
    assert painted_pixels(str(plain), 1, (72.0, 300.0, 540.0, 340.0)) == 0


def test_page_background_is_measured_rather_than_assumed_white(tmp_path: Path) -> None:
    coloured = _page(tmp_path, "coloured.pdf", background=PAGE_COLOUR)
    assert page_background(str(coloured), 1) == PAGE_COLOUR_RENDERED
    # Black text on a coloured page still counts as painted, which it would not
    # if the background were taken to be white.
    assert painted_pixels(str(coloured), 1, _text_box(coloured)) > 0


def test_white_page_reports_a_white_background(plain: Path) -> None:
    assert page_background(str(plain), 1) == (255, 255, 255)


@pytest.fixture
def rotated(plain: Path, tmp_path: Path) -> Path:
    return _edited(plain, tmp_path / "rotated.pdf", rotation=90)


def test_missing_file_raises_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Cannot read"):
        render_page(str(tmp_path / "absent.pdf"), 1)


def test_file_that_is_not_a_pdf_raises_value_error(tmp_path: Path) -> None:
    path = tmp_path / "not.pdf"
    path.write_bytes(b"this is not a PDF at all")
    with pytest.raises(ValueError, match="Cannot parse"):
        render_page(str(path), 1)


def test_page_zero_raises_rather_than_returning_the_last_page(plain: Path) -> None:
    """pypdfium2 indexes a document like a list, so page 0 would be page -1."""
    with pytest.raises(ValueError, match="Page numbers start at 1"):
        render_page(str(plain), 0)


def test_page_beyond_the_end_raises_value_error(plain: Path) -> None:
    with pytest.raises(ValueError, match="has 1 page"):
        render_page(str(plain), 2)


def test_rotated_page_is_refused_by_name(rotated: Path) -> None:
    """The refusal has to say what is wrong, not merely that something is.

    A rotated page is a known limitation rather than a broken file, and the
    message is what tells a user which of the two they are looking at.
    """
    with pytest.raises(ValueError, match="rotated by 90 degrees"):
        render_page(str(rotated), 1)


@pytest.mark.parametrize(
    "call",
    [visible_area, page_background, lambda path, page: painted_pixels(path, page, (0, 0, 10, 10))],
    ids=["visible_area", "page_background", "painted_pixels"],
)
def test_every_entry_point_refuses_a_rotated_page(
    call: Callable[[str, int], object], rotated: Path
) -> None:
    with pytest.raises(ValueError, match="known limitation"):
        call(str(rotated), 1)
