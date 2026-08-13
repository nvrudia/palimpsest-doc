"""Rendering layer: a second, independent reading of the page.

Everything else in this package reads the document through pdfminer. A defect
there would be invisible to a test that also reads through pdfminer, so the
extraction layer's self-verification proves only that it agrees with itself.
This module rasterises the page with PDFium, which shares no code with
pdfminer: a claim about what a reader sees can then be checked against what a
different implementation actually paints.

Pillow is deliberately not used. pypdfium2 declares no dependencies of its own,
and Pillow reaches this environment only through reportlab, which is a
development dependency. Calling ``to_pil()`` would therefore work in the test
environment and fail once the tool is installed. The raster is read out of the
bitmap's raw buffer instead.
"""

from collections import Counter
from functools import lru_cache
from math import ceil, floor

import pypdfium2 as pdfium

# Rendering scale. At 1.0 a small glyph covers a handful of pixels and a thin
# stroke can fall between sample points entirely, turning a painted fragment
# into a count of zero. Doubling costs four times the memory and removes that
# class of false negative.
DEFAULT_SCALE = 2.0

# How many rasters are held at once. One page at the default scale is about
# 6 MB, which bounds this module at roughly 50 MB.
#
# The cache exists for determinism, not for speed: every question asked about
# one page must be answered from one raster, otherwise two findings about the
# same page could rest on two different renderings and disagree. Keyed on the
# path alone, so a file rewritten during a single run would still be served
# from the cache; scanning a file while it changes is out of scope.
RENDER_CACHE_SIZE = 8

# Page geometry is cheap to read but must also stay fixed for a run, and it is
# asked for once per fragment. A page count well above the render cache costs
# almost nothing.
GEOMETRY_CACHE_SIZE = 64

# Thickness of the frame along the page edge sampled for the background colour,
# in PDF units.
#
# The background is taken from the perimeter rather than from the whole page.
# The most frequent colour of an entire page is the colour of whatever covers
# most of it, and on a scan carrying one large dark image that is the image.
# Ordinary documents keep their margins clear -- the usual text margin is 72
# units -- so a frame this thin stays outside the text block.
#
# The assumption fails on a document whose content runs to the very edge of the
# page: such a page reports its content as its background, and a fragment
# painted in that colour is then counted as blank.
BACKGROUND_BORDER_UNITS = 12.0

# How far a channel must depart from the background before a pixel counts as
# painted, on the 0-255 scale.
#
# Not zero, or text that no reader can make out would be reported as painted:
# a line set one step off white, at 254, was measured to fill its box as
# densely as black text does. Not large either, because a faint mark is still a
# mark. The value was chosen against a scale of greys on white, counting the
# pixels of one 12 pt line:
#
#     fill  254  252  250  247  242  230  128    0
#     t=0  2426 2426 2426 2426 2426 2426  2426 2426
#     t=8     0    0    0    0 1283 1631  2180 2259
#     t=32    0    0    0    0    0    0  1816 1974
#
# At 8 the two ends behave: text within 3% of the background disappears, while
# a light grey at 230 keeps two thirds of its pixels. At 32 that grey is erased
# as well, which would be a claim that a reader cannot see it.
#
# Antialiasing is the reason the count never reaches the whole box: roughly 7%
# of a black glyph's pixels sit within the threshold of the background, at the
# outer edge of each stroke.
PAINT_THRESHOLD = 8

# Channels per pixel in the packed raster returned by render_page.
CHANNELS = 3


def _open(path: str) -> pdfium.PdfDocument:
    """Open a document, reporting failures the way extract.py does."""
    try:
        return pdfium.PdfDocument(path)
    except OSError as exc:
        raise ValueError(f"Cannot read {path!r}: {exc}") from exc
    except pdfium.PdfiumError as exc:
        raise ValueError(f"Cannot parse {path!r} as a PDF: {exc}") from exc


def _load_page(document: pdfium.PdfDocument, path: str, page: int) -> pdfium.PdfPage:
    """Fetch one page by its one-based number, as the rest of the project counts.

    The lower bound is checked before indexing rather than left to the library.
    pypdfium2 indexes a document like a list, so page 0 would quietly return the
    last page instead of failing, and every measurement taken from it would be
    about a page nobody asked for.
    """
    if page < 1:
        raise ValueError(f"Page numbers start at 1; page {page} was requested for {path!r}")
    count = len(document)
    if page > count:
        raise ValueError(f"{path!r} has {count} page(s); page {page} was requested")
    try:
        return document[page - 1]
    except pdfium.PdfiumError as exc:
        raise ValueError(f"Cannot load page {page} of {path!r}: {exc}") from exc


@lru_cache(maxsize=GEOMETRY_CACHE_SIZE)
def _visible_area(path: str, page: int) -> tuple[float, float, float, float]:
    document = _open(path)
    try:
        page_object = _load_page(document, path, page)
        rotation = page_object.get_rotation()
        if rotation:
            # Both readings do handle rotation, and they agree: measured at 0,
            # 90, 180 and 270 degrees, pdfminer reports glyph coordinates in the
            # rotated display space and the formula below lands on the ink every
            # time. What does not survive is the page size used here -- get_bbox
            # ignores /Rotate while PDFium rasterises the rotated page, so the
            # two disagree about which dimension is which.
            #
            # That alone would be a small fix. The reason the restriction stays
            # is a layer down: grouping glyphs into runs assumes horizontal text,
            # comparing baselines and horizontal gaps, so a rotated line arrives
            # as one run per character. Findings would then quote single letters,
            # which is worse than declining to answer.
            raise ValueError(
                f"Page {page} of {path!r} is rotated by {rotation} degrees, which this tool "
                "cannot render. This is a known limitation. The scan stops here rather than "
                "report a document that only some of the checks were able to examine."
            )
        # get_bbox is the intersection of MediaBox and CropBox, which is exactly
        # the area PDFium rasterises. get_cropbox returns the raw entry instead:
        # measured against a file whose CropBox exceeds its MediaBox, it reports
        # the oversized box while the page still renders at MediaBox size.
        bbox = page_object.get_bbox()
        # Needed only for its origin: pdfminer reports glyph coordinates
        # relative to the lower left corner of the MediaBox, so the visible area
        # has to be expressed in the same terms.
        #
        # PDFium does not resolve boxes inherited from a parent node in the page
        # tree, whereas pdfminer does. A page inheriting a MediaBox whose origin
        # is not (0, 0) would therefore be measured against the wrong origin.
        # Such files are rare, and inventing a second box reader to cover them
        # would defeat the purpose of reading the page through one library.
        media = page_object.get_mediabox()
    finally:
        # Windows keeps the file locked until the document is closed, which
        # breaks the cleanup of the temporary directories the fixtures use.
        document.close()

    x0, y0, x1, y1 = bbox
    return (x0 - media[0], y0 - media[1], x1 - x0, y1 - y0)


def visible_area(path: str, page: int) -> tuple[float, float, float, float]:
    """Offset and size of the area of a page that is actually displayed.

    Returns ``(offset_x, offset_y, width, height)`` in PDF units, in the same
    coordinate space as a Glyph: relative to the lower left corner of the
    MediaBox, y increasing upwards.

    The displayed area is the CropBox where one is present, intersected with the
    MediaBox, and the MediaBox alone otherwise. It is the single place this
    geometry is derived; a detector deciding whether a fragment lies off the
    page and this module deciding which pixels a fragment covers must not each
    carry their own copy of the formula, or they will eventually disagree.

    Raises ValueError if the page cannot be read, if the number is out of range,
    or if the page is rotated.
    """
    return _visible_area(path, page)


def _pack_rgb(bitmap: pdfium.PdfBitmap) -> bytes:
    """Copy a rendered bitmap into tightly packed 8-bit RGB.

    The layout is read back from the bitmap rather than assumed. ``format``
    alone does not describe it: rendering the same page with and without
    ``rev_byteorder`` was measured to report format 2 in both cases while the
    bytes came out in opposite orders, so a check on the format constant would
    pass while red and blue were being swapped. Nor is the stride guaranteed to
    equal ``width * n_channels``; a padded row would shift every line of the
    image by a constant and still produce plausible counts.

    Anything this function cannot read is an error, not a best effort: a wrong
    but confident pixel count is worse than no count at all.
    """
    channels = bitmap.n_channels
    if not bitmap.rev_byteorder or channels not in (3, 4):
        raise RuntimeError(
            "cannot read the rendered bitmap: expected reverse byte order and 3 "
            f"or 4 channels, got format={bitmap.format} n_channels={channels} "
            f"rev_byteorder={bitmap.rev_byteorder} stride={bitmap.stride}"
        )

    raw = memoryview(bitmap.buffer)
    stride = bitmap.stride
    row_length = bitmap.width * channels
    packed = bytearray()
    for y in range(bitmap.height):
        row = bytearray(raw[y * stride : y * stride + row_length])
        if channels == 4:
            # RGBx or RGBA: the fourth byte carries no colour here, as the page
            # is rendered onto an opaque background.
            del row[3::4]
        packed += row
    return bytes(packed)


@lru_cache(maxsize=RENDER_CACHE_SIZE)
def _render_page(path: str, page: int, scale: float) -> tuple[int, int, bytes]:
    width, height = _visible_area(path, page)[2:]
    document = _open(path)
    try:
        page_object = _load_page(document, path, page)
        try:
            bitmap = page_object.render(scale=scale, rev_byteorder=True)
        except pdfium.PdfiumError as exc:
            raise ValueError(f"Cannot render page {page} of {path!r}: {exc}") from exc
        raster_width, raster_height = bitmap.width, bitmap.height
        pixels = _pack_rgb(bitmap)
    finally:
        document.close()

    # PDFium sizes the raster by rounding each dimension up. If the result is
    # not the size the page geometry predicts, then the two disagree about what
    # was drawn, and every coordinate mapped from the page onto this raster
    # would be off by an unknown amount.
    expected = (ceil(width * scale), ceil(height * scale))
    if (raster_width, raster_height) != expected:
        raise RuntimeError(
            f"rendered page {page} of {path!r} measures {raster_width}x{raster_height} "
            f"pixels, but its visible area of {width}x{height} units at scale "
            f"{scale} predicts {expected[0]}x{expected[1]}"
        )
    return raster_width, raster_height, pixels


def render_page(path: str, page: int, scale: float = DEFAULT_SCALE) -> tuple[int, int, bytes]:
    """Rasterise one page and return ``(width, height, pixels)``.

    Page numbers start at 1, as everywhere else in the project; the library
    counts from 0 and the conversion is made here so no caller has to remember
    which convention it is holding.

    ``pixels`` is tightly packed 8-bit RGB, three bytes per pixel, rows running
    from the top of the page downwards. The byte at ``(y * width + x) * 3`` is
    the red channel of the pixel at column x, row y.

    Raises ValueError if the page cannot be read or rendered.
    """
    # scale is normalised before it reaches the cache: render_page(p, 1) and
    # render_page(p, 1, 2) must not become two entries producing two rasters,
    # which is the very thing the cache is here to prevent.
    return _render_page(path, page, float(scale))


def _pixel(pixels: bytes, offset: int) -> tuple[int, int, int]:
    return (pixels[offset], pixels[offset + 1], pixels[offset + 2])


@lru_cache(maxsize=GEOMETRY_CACHE_SIZE)
def _page_background(path: str, page: int, scale: float) -> tuple[int, int, int]:
    width, height, pixels = _render_page(path, page, scale)

    # At least one pixel, and never so thick that the frame swallows the page:
    # on a very small page the two side bands would otherwise overlap and the
    # centre would be counted twice.
    border = max(1, int(BACKGROUND_BORDER_UNITS * scale))
    border = min(border, (width + 1) // 2, (height + 1) // 2)

    counts: Counter[tuple[int, int, int]] = Counter()
    for y in range(height):
        row_start = y * width * CHANNELS
        if y < border or y >= height - border:
            spans = [(0, width)]  # a full row, top and bottom bands
        else:
            spans = [(0, border), (width - border, width)]  # left and right
        for x0, x1 in spans:
            row = pixels[row_start + x0 * CHANNELS : row_start + x1 * CHANNELS]
            counts.update(zip(row[0::CHANNELS], row[1::CHANNELS], row[2::CHANNELS]))
    # A raster always has at least one pixel, so the counter is never empty.
    return counts.most_common(1)[0][0]


def page_background(path: str, page: int, scale: float = DEFAULT_SCALE) -> tuple[int, int, int]:
    """The background colour of a page as rendered, as 8-bit RGB.

    Measured as the most frequent colour in a frame along the edge of the page;
    see BACKGROUND_BORDER_UNITS for why the sample is the frame rather than the
    whole page. White is never assumed: a document may be set on any colour, and
    text matching that colour is as invisible as white text on white.

    Cached alongside the raster, for the same reason: a page has one background,
    and two callers asking must not receive two answers.

    Raises ValueError if the page cannot be read or rendered.
    """
    return _page_background(path, page, float(scale))


def painted_pixels(
    path: str,
    page: int,
    box: tuple[float, float, float, float],
    scale: float = DEFAULT_SCALE,
) -> int:
    """Count the painted pixels inside a rectangle of a page.

    ``box`` is ``(x0, y0, x1, y1)`` in PDF units, in the coordinate space of a
    Glyph: origin at the lower left of the MediaBox, y increasing upwards. The
    raster runs the other way, from the top down, and starts at the corner of
    the displayed area rather than of the MediaBox, so both are undone here.

    A pixel counts as painted when any channel differs from the background of
    the page by more than PAINT_THRESHOLD. The background is measured, not
    assumed to be white.

    Raises ValueError if the page cannot be read or rendered.
    """
    width, height, pixels = render_page(path, page, scale)
    offset_x, offset_y, _, area_height = visible_area(path, page)
    background = page_background(path, page, scale)

    # Callers pass a bounding box, which is ordered by construction; sorting the
    # edges anyway costs nothing and keeps an inverted rectangle from silently
    # counting nothing rather than counting what it names.
    x0, x1 = sorted((box[0], box[2]))
    y0, y1 = sorted((box[1], box[3]))

    # Outward rounding on every edge. Truncating instead drops the outermost row
    # and column of the fragment, which is where antialiasing puts the faintest
    # part of a glyph -- exactly the part a check for "did this paint anything"
    # depends on.
    top = offset_y + area_height
    left_px = max(0, floor((x0 - offset_x) * scale))
    right_px = min(width, ceil((x1 - offset_x) * scale))
    top_px = max(0, floor((top - y1) * scale))
    bottom_px = min(height, ceil((top - y0) * scale))
    if left_px >= right_px or top_px >= bottom_px:
        # The rectangle lies wholly outside the displayed area, or has no area.
        return 0

    painted = 0
    for y in range(top_px, bottom_px):
        row_start = (y * width + left_px) * CHANNELS
        for offset in range(row_start, row_start + (right_px - left_px) * CHANNELS, CHANNELS):
            pixel = _pixel(pixels, offset)
            if any(
                abs(channel - reference) > PAINT_THRESHOLD
                for channel, reference in zip(pixel, background)
            ):
                painted += 1
    return painted
