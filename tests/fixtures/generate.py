"""Generators for adversarial sample PDFs.

Files are built into a temporary directory during a test run and never enter the
repository. All text is invented for this purpose; no real document is used.

Setting a non-zero text render mode
-----------------------------------
Any fragment that sets a non-zero render mode must be wrapped in
saveState/restoreState, and the wrapping must enclose the fragment that sets the
mode rather than the fragments after it. Per the PDF specification the render
mode is part of the graphics state: it survives BT/ET and is only undone by Q.
Without the wrapping, mode 3 leaks its invisibility into every following
fragment, and modes 4-7 additionally leak their clipping path, which erases
everything drawn after them.

setTextRenderMode(0) must never be used to undo a mode. Reportlab compares the
requested mode against a counter held by the individual text object, and a fresh
beginText() initialises that counter to 0; asking for 0 therefore matches, and no
Tr operator is emitted at all, while the mode in the file is still whatever the
previous fragment left. The call succeeds and does nothing.

Self-verification
-----------------
Every generator parses the file it has just written and checks that the render
modes and font sizes are the ones it intended, raising immediately if they are
not. During this step reportlab produced a plausible-looking but wrong file
twice: setTextRenderMode(0) silently had no effect, and Helvetica silently
rendered Cyrillic as a row of "n". A fixture that lies makes the test suite
report success while checking something other than what was meant.

Since step 3 the check no longer relies on the text layer alone. Every fragment
is also rasterised and its pixels counted, so a fixture claiming to hide
something must prove it against a renderer that shares no code with the parser.
That closes the circularity the earlier version of this note admitted to: the
claim and its verification no longer come from the same reading of the file.
"""

from pathlib import Path
from typing import NoReturn

from reportlab.pdfgen import canvas
from reportlab.pdfgen.textobject import PDFTextObject

from palimpsest.integrity.detectors.tiny_text import MIN_LEGIBLE_FONT_SIZE
from palimpsest.integrity.extract import extract_glyphs, group_runs
from palimpsest.integrity.model import TextRun
from palimpsest.integrity.render import painted_pixels, visible_area

PAGE_SIZE = (612.0, 792.0)

# Helvetica is one of the standard 14 fonts, always present in a PDF reader, and
# its WinAnsi encoding covers the Latin text used here exactly. It must not be
# given anything outside that range: it does not fail on characters it cannot
# encode, it substitutes them.
FONT_NAME = "Helvetica"
BODY_FONT_SIZE = 12.0
TINY_FONT_SIZE = 0.1

INVISIBLE_RENDER_MODE = 3
VISIBLE_RENDER_MODE = 0

VISIBLE_PARAGRAPH = "This sample document contains one paragraph of ordinary visible text."
SECOND_PARAGRAPH = "It exists so that a detector has something legitimate to leave alone."
HIDDEN_MARKER = "HIDDEN INSTRUCTION MARKER"
TINY_MARKER = "SUB LEGIBLE MARKER"
BACKGROUND_MARKER = "BACKGROUND COLOUR MARKER"
OUTSIDE_MARKER = "OFF PAGE MARKER"

# The page is left unpainted, so its background is the white the renderer fills
# with. Text set to the same white is the anomaly.
BACKGROUND_FILL_GRAY = 1.0

# Far enough to the left that the whole fragment clears the page: a partial
# overlap is deliberately not a finding, so a fixture that only half leaves the
# page would test the opposite of what it claims.
OUTSIDE_X = -300.0


def _visible(text_object: PDFTextObject, text: str, size: float) -> None:
    """Add a fragment drawn in the default render mode."""
    text_object.setFont(FONT_NAME, size)
    text_object.textLine(text)


def _draw_visible(
    c: canvas.Canvas, y: float, text: str, size: float = BODY_FONT_SIZE, x: float = 72.0
) -> None:
    text_object = c.beginText(x, y)
    _visible(text_object, text, size)
    c.drawText(text_object)


def _draw_invisible(c: canvas.Canvas, y: float, text: str) -> None:
    """Add a fragment in render mode 3, confined by q/Q so it cannot leak."""
    c.saveState()
    text_object = c.beginText(72, y)
    text_object.setFont(FONT_NAME, BODY_FONT_SIZE)
    text_object.setTextRenderMode(INVISIBLE_RENDER_MODE)
    text_object.textLine(text)
    c.drawText(text_object)
    c.restoreState()


def _draw_background_coloured(c: canvas.Canvas, y: float, text: str) -> None:
    """Add a fragment painted the colour of the page, in the ordinary mode.

    Wrapped in q/Q for the same reason as the render mode: the fill colour is
    part of the graphics state and survives BT/ET, so without the wrapping every
    following fragment would inherit it and the document would be blank.
    """
    c.saveState()
    text_object = c.beginText(72, y)
    text_object.setFont(FONT_NAME, BODY_FONT_SIZE)
    text_object.setFillGray(BACKGROUND_FILL_GRAY)
    text_object.textLine(text)
    c.drawText(text_object)
    c.restoreState()


def _describe(runs: list[TextRun]) -> str:
    """Render the parsed runs for an error message."""
    return "\n".join(
        f"    mode={run.render_mode!r} size={run.font_size:g} text={run.text!r}" for run in runs
    )


def _bbox(run: TextRun) -> tuple[float, float, float, float]:
    return (run.x0, run.y0, run.x1, run.y1)


def _locate(runs: list[TextRun], marker: str) -> TextRun | None:
    return next((run for run in runs if marker in run.text), None)


def _verify(
    path: Path,
    *,
    invisible_texts: list[str],
    tiny_texts: list[str],
    background_texts: list[str],
    outside_texts: list[str],
    visible_texts: list[str],
) -> None:
    """Check that the written file contains exactly the anomalies intended.

    Raises RuntimeError rather than returning a result: a wrong fixture must
    stop the run where it was created, not surface later as a puzzling failure
    in a test that looks unrelated.

    The structural half of this check reads the file through the same extraction
    layer the tests exercise, and a misreading shared by both would satisfy it.
    The pixel half does not: it rasterises the page with an unrelated library and
    counts what was actually painted. Every fragment is measured, so a fixture
    cannot claim to hide a marker that a renderer would in fact display, nor
    quietly blank a fragment it promised to show.
    """
    runs = group_runs(extract_glyphs(str(path)))

    def fail(reason: str) -> NoReturn:
        raise RuntimeError(
            f"fixture {path.name} is not what it claims: {reason}\n{_describe(runs)}"
        )

    invisible = [run for run in runs if run.render_mode == INVISIBLE_RENDER_MODE]
    if len(invisible) != len(invisible_texts):
        fail(f"expected {len(invisible_texts)} invisible run(s), found {len(invisible)}")
    for run, expected in zip(invisible, invisible_texts, strict=True):
        if expected not in run.text:
            fail(f"invisible run reads {run.text!r}, expected to contain {expected!r}")

    tiny = [run for run in runs if abs(run.font_size) < MIN_LEGIBLE_FONT_SIZE and run.text.strip()]
    if len(tiny) != len(tiny_texts):
        fail(f"expected {len(tiny_texts)} sub-legible run(s), found {len(tiny)}")
    for run, expected in zip(tiny, tiny_texts, strict=True):
        if expected not in run.text:
            fail(f"sub-legible run reads {run.text!r}, expected to contain {expected!r}")

    for run in runs:
        if run.render_mode not in (VISIBLE_RENDER_MODE, INVISIBLE_RENDER_MODE):
            fail(f"unexpected render mode {run.render_mode!r} in run {run.text!r}")
        if run not in invisible and run not in tiny and abs(run.font_size) < MIN_LEGIBLE_FONT_SIZE:
            fail(f"run {run.text!r} is unintentionally sub-legible")

    for expected in background_texts:
        located = _locate(runs, expected)
        if located is None:
            fail(f"background-coloured run {expected!r} is absent from the parsed document")
        # Its invisibility has to come from the colour and from nothing else, or
        # the fixture would still hide its marker while testing another detector.
        if located.render_mode != VISIBLE_RENDER_MODE:
            fail(
                f"background-coloured run {expected!r} carries render mode {located.render_mode!r}"
            )
        if abs(located.font_size) < MIN_LEGIBLE_FONT_SIZE:
            fail(f"background-coloured run {expected!r} is also sub-legible")

    for expected in outside_texts:
        located = _locate(runs, expected)
        if located is None:
            fail(f"off-page run {expected!r} is absent from the parsed document")
        offset_x, offset_y, width, height = visible_area(str(path), located.page)
        # Wholly outside, not merely overlapping the edge: a partial overlap is
        # deliberately not a finding, so a fixture that only half leaves the page
        # would prove the opposite of what it was written to prove.
        if not (
            located.x1 <= offset_x
            or located.x0 >= offset_x + width
            or located.y1 <= offset_y
            or located.y0 >= offset_y + height
        ):
            fail(
                f"off-page run {expected!r} at {_bbox(located)} still meets the visible area "
                f"({offset_x}, {offset_y}) to ({offset_x + width}, {offset_y + height})"
            )

    # Guards against a font silently substituting characters it cannot encode.
    for expected in visible_texts:
        if not any(expected in run.text for run in runs):
            fail(f"visible text {expected!r} is absent from the parsed document")

    # The independent half. Every fragment the document was meant to hide has to
    # paint nothing, and every fragment it was meant to show has to paint
    # something, measured by a library that never saw the text layer.
    hidden = invisible_texts + tiny_texts + background_texts + outside_texts
    for run in runs:
        if not run.text.strip():
            continue
        painted = painted_pixels(str(path), run.page, _bbox(run))
        if any(marker in run.text for marker in hidden):
            if painted:
                fail(f"run {run.text!r} was meant to be hidden but paints {painted} pixel(s)")
        elif not painted:
            fail(f"run {run.text!r} was meant to be visible but paints nothing")


def clean_pdf(directory: Path) -> Path:
    """A document with nothing to find. No detector may report anything."""
    path = Path(directory) / "clean.pdf"
    c = canvas.Canvas(str(path), pagesize=PAGE_SIZE)
    _draw_visible(c, 720, VISIBLE_PARAGRAPH)
    _draw_visible(c, 700, SECOND_PARAGRAPH)
    c.showPage()
    c.save()
    _verify(
        path,
        invisible_texts=[],
        tiny_texts=[],
        background_texts=[],
        outside_texts=[],
        visible_texts=[VISIBLE_PARAGRAPH, SECOND_PARAGRAPH],
    )
    return path


def invisible_text_pdf(directory: Path) -> Path:
    """A visible paragraph plus one fragment in render mode 3."""
    path = Path(directory) / "invisible_text.pdf"
    c = canvas.Canvas(str(path), pagesize=PAGE_SIZE)
    _draw_visible(c, 720, VISIBLE_PARAGRAPH)
    _draw_invisible(c, 700, HIDDEN_MARKER)
    _draw_visible(c, 680, SECOND_PARAGRAPH)
    c.showPage()
    c.save()
    _verify(
        path,
        invisible_texts=[HIDDEN_MARKER],
        tiny_texts=[],
        background_texts=[],
        outside_texts=[],
        visible_texts=[VISIBLE_PARAGRAPH, SECOND_PARAGRAPH],
    )
    return path


def tiny_text_pdf(directory: Path) -> Path:
    """A visible paragraph plus one fragment below the legibility threshold."""
    path = Path(directory) / "tiny_text.pdf"
    c = canvas.Canvas(str(path), pagesize=PAGE_SIZE)
    _draw_visible(c, 720, VISIBLE_PARAGRAPH)
    _draw_visible(c, 700, TINY_MARKER, TINY_FONT_SIZE)
    _draw_visible(c, 680, SECOND_PARAGRAPH)
    c.showPage()
    c.save()
    _verify(
        path,
        invisible_texts=[],
        tiny_texts=[TINY_MARKER],
        background_texts=[],
        outside_texts=[],
        visible_texts=[VISIBLE_PARAGRAPH, SECOND_PARAGRAPH],
    )
    return path


def both_pdf(directory: Path) -> Path:
    """Both anomalies in one document, each present exactly once."""
    path = Path(directory) / "both.pdf"
    c = canvas.Canvas(str(path), pagesize=PAGE_SIZE)
    _draw_visible(c, 720, VISIBLE_PARAGRAPH)
    _draw_invisible(c, 700, HIDDEN_MARKER)
    _draw_visible(c, 680, TINY_MARKER, TINY_FONT_SIZE)
    _draw_visible(c, 660, SECOND_PARAGRAPH)
    c.showPage()
    c.save()
    _verify(
        path,
        invisible_texts=[HIDDEN_MARKER],
        tiny_texts=[TINY_MARKER],
        background_texts=[],
        outside_texts=[],
        visible_texts=[VISIBLE_PARAGRAPH, SECOND_PARAGRAPH],
    )
    return path


def background_color_pdf(directory: Path) -> Path:
    """A visible paragraph plus one fragment painted the colour of the page."""
    path = Path(directory) / "background_color.pdf"
    c = canvas.Canvas(str(path), pagesize=PAGE_SIZE)
    _draw_visible(c, 720, VISIBLE_PARAGRAPH)
    _draw_background_coloured(c, 700, BACKGROUND_MARKER)
    _draw_visible(c, 680, SECOND_PARAGRAPH)
    c.showPage()
    c.save()
    _verify(
        path,
        invisible_texts=[],
        tiny_texts=[],
        background_texts=[BACKGROUND_MARKER],
        outside_texts=[],
        visible_texts=[VISIBLE_PARAGRAPH, SECOND_PARAGRAPH],
    )
    return path


def outside_page_pdf(directory: Path) -> Path:
    """A visible paragraph plus one fragment written off the edge of the page."""
    path = Path(directory) / "outside_page.pdf"
    c = canvas.Canvas(str(path), pagesize=PAGE_SIZE)
    _draw_visible(c, 720, VISIBLE_PARAGRAPH)
    _draw_visible(c, 700, OUTSIDE_MARKER, BODY_FONT_SIZE, OUTSIDE_X)
    _draw_visible(c, 680, SECOND_PARAGRAPH)
    c.showPage()
    c.save()
    _verify(
        path,
        invisible_texts=[],
        tiny_texts=[],
        background_texts=[],
        outside_texts=[OUTSIDE_MARKER],
        visible_texts=[VISIBLE_PARAGRAPH, SECOND_PARAGRAPH],
    )
    return path
