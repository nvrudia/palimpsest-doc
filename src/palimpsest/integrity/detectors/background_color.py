"""Detector for text painted in the colour of the page it sits on.

Colour tuples cannot be compared as they stand. ``(1.0, 1.0, 1.0)`` in DeviceRGB
and ``(1.0,)`` in DeviceGray are the same white, and four components in
DeviceCMYK are white as well when they are all zero. Everything is therefore
reduced to one number, the luminance, before any comparison happens.

Unlike the other detectors, this one needs the document itself: the background
is measured by rendering the page, never assumed to be white. Documents are set
on colour, and text matching that colour is exactly as unreadable as white on
white. The path arrives through the constructor, so the `run` method keeps the
signature every other detector has.
"""

from palimpsest.integrity.detectors.base import (
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    format_evidence,
    format_location,
)
from palimpsest.integrity.model import TextRun
from palimpsest.integrity.render import page_background
from palimpsest.report.model import Finding

# Weights converting DeviceRGB to a single intensity, from the conversion PDF
# 32000-1 gives for DeviceRGB to DeviceGray. Taken from the PDF specification
# rather than from a video standard because the question here is what the
# format itself considers equivalent.
RED_WEIGHT = 0.3
GREEN_WEIGHT = 0.59
BLUE_WEIGHT = 0.11

# Number of components each supported colour space carries. A tuple of the wrong
# length is not interpreted: it means the parser and this table disagree about
# the space, and a guess would produce a confident finding from a colour nobody
# established.
COMPONENT_COUNTS = {"DeviceGray": 1, "DeviceRGB": 3, "DeviceCMYK": 4}

# How close the luminance of text may come to the luminance of the page before
# the fragment is reported, for the colour spaces that convert exactly.
#
# Anchored to what the renderer was measured to do: text set 3% away from a
# white background produced no pixels at all, while at 5% roughly half of the
# glyph survived. Below 0.05 a reader is looking at a blank page.
LUMINANCE_THRESHOLD = 0.05

# The same, for DeviceCMYK, where the conversion below is an approximation.
#
# The margin runs the other way from the exact spaces: since the computed
# luminance may be wrong, the computed difference has to be smaller before the
# finding is worth making, not larger. Comparing the approximation against
# PDFium over low ink coverage -- the only region where this detector can fire
# on a white page -- gave errors up to 0.058, which is larger than the 0.05 used
# above. A fragment 0.05 away by this arithmetic may therefore be plainly
# visible, so that band is not claimed at all: for CMYK only a coincidence the
# approximation itself cannot blur is reported.
#
# On a white background such a coincidence is solid. A computed luminance of 1.0
# requires every one of C+K, M+K and Y+K to be zero, which is to say no ink.
CMYK_LUMINANCE_THRESHOLD = 0.01

# Below this difference two luminances are treated as the same value.
#
# Not a perceptual threshold: it is the precision of the comparison itself. The
# background is read back from an 8-bit raster, so a colour the file states
# exactly returns quantised -- a page painted in RGB (0.1, 0.1, 0.35) renders as
# (26, 26, 89), which is (0.102, 0.102, 0.349). Text painted in that same colour
# then differs from its own background by 0.0016 rather than by nothing, and a
# test for exact equality would report the clearest case this detector has as
# the weaker of its two severities.
#
# One quantisation step bounds that: the weights sum to one, so a per-channel
# error of at most half a step carries through to at most half a step of
# luminance. It also covers the rounding of binary floating point, which is
# smaller by many orders of magnitude but real -- the weights do not sum
# associatively, and adding them left to right yields 0.9999999999999999 where
# sum() yields 1.0.
IDENTICAL_LUMINANCE = 1.0 / 255.0

EXPLANATION = (
    "This text is painted in {space} at a luminance of {text:.3f}, on a page "
    "whose background renders at {background:.3f}. The difference of {gap:.3f} "
    "is too small for a reader to make the text out, while text extraction "
    "returns it in full, so a reader and an automated consumer of this file "
    "receive different content."
)


def _luminance(red: float, green: float, blue: float) -> float:
    return RED_WEIGHT * red + GREEN_WEIGHT * green + BLUE_WEIGHT * blue


def _to_grayscale(color: tuple[float, ...], space: str | None) -> float | None:
    """Reduce a colour to a luminance between 0 and 1, or None if it cannot be.

    None means the colour space is not one of the three device spaces, or the
    tuple does not carry the number of components that space requires. Separation
    and ICC-based spaces resolve through data this layer never sees, and a
    pattern has no single colour at all; none of them may be guessed at.

    The DeviceCMYK branch is an approximation. Converting subtractive ink
    coverage to an intensity depends on the output profile, which the file need
    not carry and this tool does not read, so the formula the PDF specification
    supplies for the profile-less case is used instead. Measured against PDFium
    it is exact at zero ink and drifts to roughly 0.06 by 20% coverage, which is
    why CMYK is held to its own threshold above.
    """
    if space is None or len(color) != COMPONENT_COUNTS.get(space, -1):
        return None
    if space == "DeviceGray":
        value = color[0]
    elif space == "DeviceRGB":
        value = _luminance(*color)
    else:
        cyan, magenta, yellow, black = color
        value = _luminance(
            1.0 - min(1.0, cyan + black),
            1.0 - min(1.0, magenta + black),
            1.0 - min(1.0, yellow + black),
        )
    # A component outside 0 to 1 is a malformed file rather than a colour, and a
    # renderer clamps it. Clamping here keeps the comparison meaningful instead
    # of producing a luminance no display can show.
    return min(1.0, max(0.0, value))


def _threshold(space: str) -> float:
    return CMYK_LUMINANCE_THRESHOLD if space == "DeviceCMYK" else LUMINANCE_THRESHOLD


class BackgroundColorDetector:
    """Reports runs whose fill colour is indistinguishable from the page."""

    name = "text_color_matches_background"

    def __init__(self, path: str) -> None:
        self._path = path

    def _background_luminance(self, page: int) -> float:
        red, green, blue = page_background(self._path, page)
        return _luminance(red / 255.0, green / 255.0, blue / 255.0)

    def run(self, runs: list[TextRun]) -> list[Finding]:
        findings = []
        for text_run in runs:
            if text_run.fill_color is None:
                continue
            text_luminance = _to_grayscale(text_run.fill_color, text_run.color_space)
            if text_luminance is None or text_run.color_space is None:
                continue
            # Read only once a run has passed every cheaper test, so a document
            # with nothing to find is never rendered.
            background = self._background_luminance(text_run.page)
            gap = abs(text_luminance - background)
            if gap >= _threshold(text_run.color_space):
                continue
            findings.append(
                Finding(
                    detector=self.name,
                    severity=SEVERITY_HIGH if gap < IDENTICAL_LUMINANCE else SEVERITY_MEDIUM,
                    location=format_location(
                        text_run.page,
                        text_run.x0,
                        text_run.y0,
                        text_run.x1,
                        text_run.y1,
                    ),
                    evidence=format_evidence(text_run.text),
                    explanation=EXPLANATION.format(
                        space=text_run.color_space,
                        text=text_luminance,
                        background=background,
                        gap=gap,
                    ),
                )
            )
        return findings
