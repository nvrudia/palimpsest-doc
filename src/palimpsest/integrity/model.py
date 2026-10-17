"""Data structures of the extraction layer. No logic, no parsing.

A Glyph is one character as the PDF content stream produced it, carrying the
part of the graphics state that decides whether a human ever sees it. A TextRun
is a run of adjacent glyphs that share that state.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Glyph:
    """One character together with the graphics state that produced it."""

    text: str
    page: int  # one-based
    x0: float
    y0: float
    x1: float
    y1: float
    font_name: str
    font_size: float  # effective size, transformation matrix already applied
    render_mode: int | None  # None when the parser cannot supply it
    fill_color: tuple[float, ...] | None
    stroke_color: tuple[float, ...] | None
    # Name of the colour space the components above are expressed in, e.g.
    # "DeviceGray" or "DeviceRGB". Colour tuples are only comparable within one
    # space: (0.0,) in DeviceGray is black, while a one-component tuple in a
    # separation space means something else entirely.
    color_space: str | None


@dataclass(frozen=True)
class TextRun:
    """Adjacent glyphs sharing page, font, size, render mode and colour."""

    text: str
    page: int  # one-based
    x0: float
    y0: float
    x1: float
    y1: float
    font_name: str
    font_size: float
    render_mode: int | None
    fill_color: tuple[float, ...] | None
    color_space: str | None
    glyph_count: int


@dataclass(frozen=True)
class PageFacts:
    """What is known about one page from reading the document structure alone.

    Recorded while the pages are walked, before any detector sees them, so that
    a page nothing was found on can still be told apart from a page nothing was
    looked at on.
    """

    number: int  # one-based
    rotation: int  # degrees, as the /Rotate entry gives it


@dataclass(frozen=True)
class DocumentFacts:
    """Properties of the document as a whole, recorded while it was read."""

    pages: tuple[PageFacts, ...]
    # True when the file carries an encryption dictionary. Reaching this point
    # means the document opened with an empty user password, so whatever
    # restrictions it declares are owner restrictions. This tool does not read
    # them and does not act on them.
    encrypted: bool
