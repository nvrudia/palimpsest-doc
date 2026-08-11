"""Extraction layer: PDF characters together with their graphics state.

pdfminer is driven directly rather than through a wrapper because the text
render mode is the one attribute that decides whether text reaches the page at
all, and no wrapper exposes it. The mode lives in PDFTextState, which is handed
to render_string; the character is built one call deeper, in render_char. The
collector below bridges those two.
"""

from numbers import Real
from typing import Any

from pdfminer.converter import PDFLayoutAnalyzer
from pdfminer.layout import LTChar
from pdfminer.pdfcolor import PDFColorSpace
from pdfminer.pdfdevice import PDFTextSeq
from pdfminer.pdffont import PDFFont
from pdfminer.pdfinterp import (
    PDFGraphicState,
    PDFPageInterpreter,
    PDFResourceManager,
    PDFTextState,
)
from pdfminer.pdfpage import PDFPage
from pdfminer.psexceptions import PSException
from pdfminer.utils import Matrix

from palimpsest.integrity.model import Glyph, TextRun

# Two glyph sizes count as equal below this difference. Sizes are floats derived
# from a matrix multiplication, so exact equality would split runs on rounding
# noise alone.
FONT_SIZE_TOLERANCE = 0.01

# A horizontal gap between neighbouring glyphs breaks the run once it reaches
# this multiple of the font size. One em is roughly the width of a wide
# character, so anything larger is deliberate positioning, not letter spacing.
HORIZONTAL_GAP_RATIO = 1.0

# Glyphs belong to the same line while their y0 differ by less than this
# multiple of the font size. Without a vertical test, two glyphs from different
# lines that happen to sit close horizontally would merge, and the run's text
# would read as a string that appears nowhere in the document. In an evidentiary
# tool a fabricated quotation is worse than a missed finding.
BASELINE_TOLERANCE_RATIO = 0.25


class _GlyphCollector(PDFLayoutAnalyzer):
    """Collects every rendered character along with its text render mode.

    render_string receives the PDFTextState and therefore the render mode;
    render_char receives the character but not the state. The chain
    render_string -> render_string_horizontal/vertical -> render_char is
    synchronous and single threaded, so the mode stashed by the former is
    exactly the mode of the character seen by the latter.
    """

    def __init__(self, rsrcmgr: PDFResourceManager) -> None:
        # laparams=None disables layout analysis: no reordering into lines and
        # boxes, characters stay in content stream order as the spec requires.
        super().__init__(rsrcmgr, pageno=1, laparams=None)
        self.glyphs: list[Glyph] = []
        self.page_number = 0
        self._render_mode: int | None = None

    def render_string(
        self,
        textstate: PDFTextState,
        seq: PDFTextSeq,
        ncs: PDFColorSpace,
        graphicstate: PDFGraphicState,
    ) -> None:
        self._render_mode = getattr(textstate, "render", None)
        super().render_string(textstate, seq, ncs, graphicstate)

    def render_char(
        self,
        matrix: Matrix,
        font: PDFFont,
        fontsize: float,
        scaling: float,
        rise: float,
        cid: int,
        ncs: PDFColorSpace,
        graphicstate: PDFGraphicState,
    ) -> float:
        adv = super().render_char(matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate)
        # The parent built an LTChar and appended it to the current container.
        # It returns only the advance width, so the object is taken back off the
        # end of the container's private list: constant time, unlike iterating
        # the container, which would be quadratic over a page.
        #
        # This reaches into pdfminer's internals. If a future version stops
        # appending exactly one LTChar per render_char call, the item retrieved
        # here would be some other object and the character would be paired with
        # a render mode that never applied to it. The isinstance check turns that
        # into a loud failure instead of silently corrupted evidence.
        item = self.cur_item._objs[-1]
        if not isinstance(item, LTChar):
            # TRY004 asks for TypeError; this is not a caller passing a wrong
            # type but our assumption about pdfminer's internals having broken,
            # which RuntimeError describes correctly.
            raise RuntimeError(  # noqa: TRY004
                "pdfminer returned "
                f"{type(item).__name__} where an LTChar was expected; "
                "its internal structure has changed and the render mode can no "
                "longer be attributed to a character reliably"
            )
        self.glyphs.append(_to_glyph(item, self.page_number, self._render_mode))
        return adv


def _normalise_color(value: Any) -> tuple[float, ...] | None:
    """Bring a pdfminer colour value to a uniform tuple shape.

    pdfminer reports a single component as a bare number (DeviceGray black is
    ``0``) and several components as a tuple. Anything else - a pattern name,
    for instance - carries no numeric components and becomes None rather than a
    guess.
    """
    if value is None:
        return None
    if isinstance(value, Real):
        return (float(value),)
    if isinstance(value, (tuple, list)) and all(isinstance(component, Real) for component in value):
        return tuple(float(component) for component in value)
    return None


def _to_glyph(char: LTChar, page_number: int, render_mode: int | None) -> Glyph:
    """Convert one LTChar plus its render mode into a Glyph."""
    graphicstate = char.graphicstate
    color_space = getattr(getattr(graphicstate, "ncs", None), "name", None)
    x0, y0, x1, y1 = char.bbox
    return Glyph(
        text=char.get_text(),
        page=page_number,
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        font_name=char.fontname,
        font_size=char.size,
        render_mode=render_mode,
        fill_color=_normalise_color(graphicstate.ncolor),
        stroke_color=_normalise_color(graphicstate.scolor),
        color_space=color_space,
    )


def extract_glyphs(path: str) -> list[Glyph]:
    """Return every character of the PDF, in the order the parser emits them.

    Raises ValueError if the file cannot be read or is not a PDF.
    """
    rsrcmgr = PDFResourceManager()
    device = _GlyphCollector(rsrcmgr)
    interpreter = PDFPageInterpreter(rsrcmgr, device)
    try:
        with open(path, "rb") as handle:
            for page_number, page in enumerate(PDFPage.get_pages(handle), start=1):
                device.page_number = page_number
                interpreter.process_page(page)
    except OSError as exc:
        raise ValueError(f"Cannot read {path!r}: {exc}") from exc
    except PSException as exc:
        # Base class of every pdfminer parsing error, including PDFSyntaxError
        # raised for files that are not PDFs at all.
        raise ValueError(f"Cannot parse {path!r} as a PDF: {exc}") from exc
    finally:
        device.close()
    return device.glyphs


def _same_state(current: Glyph, previous: Glyph) -> bool:
    """Everything except geometry: page, font, size, render mode, colour."""
    return (
        current.page == previous.page
        and current.font_name == previous.font_name
        and abs(current.font_size - previous.font_size) < FONT_SIZE_TOLERANCE
        and current.render_mode == previous.render_mode
        # Colour components are only meaningful inside one colour space, so the
        # space must match before the tuples are worth comparing at all.
        and current.color_space == previous.color_space
        and current.fill_color == previous.fill_color
    )


def _continues_run(current: Glyph, previous: Glyph) -> bool:
    """Whether current belongs to the same run as its predecessor."""
    if not _same_state(current, previous):
        return False
    # Whitespace carries no visible shape, so its position says nothing about
    # whether the text was interrupted. It joins on state alone.
    if not current.text.strip():
        return True
    size = previous.font_size
    if abs(current.y0 - previous.y0) >= size * BASELINE_TOLERANCE_RATIO:
        return False
    return current.x0 - previous.x1 < size * HORIZONTAL_GAP_RATIO


def _make_run(glyphs: list[Glyph]) -> TextRun:
    """Merge a list of glyphs sharing one state into a single run."""
    first = glyphs[0]
    return TextRun(
        text="".join(glyph.text for glyph in glyphs),
        page=first.page,
        x0=min(glyph.x0 for glyph in glyphs),
        y0=min(glyph.y0 for glyph in glyphs),
        x1=max(glyph.x1 for glyph in glyphs),
        y1=max(glyph.y1 for glyph in glyphs),
        font_name=first.font_name,
        font_size=first.font_size,
        render_mode=first.render_mode,
        fill_color=first.fill_color,
        color_space=first.color_space,
        glyph_count=len(glyphs),
    )


def group_runs(glyphs: list[Glyph]) -> list[TextRun]:
    """Group consecutive glyphs sharing state and position into text runs."""
    runs: list[TextRun] = []
    current: list[Glyph] = []
    for glyph in glyphs:
        if current and not _continues_run(glyph, current[-1]):
            runs.append(_make_run(current))
            current = []
        current.append(glyph)
    if current:
        runs.append(_make_run(current))
    return runs
