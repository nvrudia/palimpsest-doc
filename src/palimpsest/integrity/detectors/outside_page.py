"""Detector for text placed where the page is never displayed.

A PDF page has a canvas and a window onto it. Content may be written anywhere on
the canvas, but a reader is shown only the CropBox, or the MediaBox where no
CropBox is given. Text written outside that window is in the file, is returned
by extraction in full, and is never seen.

Like the background colour detector, this one needs the document rather than the
runs alone, because the window is a property of the page. It takes the geometry
from render.visible_area: that function already reconciles the two boxes and the
coordinate space pdfminer reports in, and a second copy of the formula here
would eventually disagree with the first.
"""

from palimpsest.integrity.detectors.base import (
    SEVERITY_HIGH,
    format_evidence,
    format_location,
)
from palimpsest.integrity.model import TextRun
from palimpsest.integrity.render import visible_area
from palimpsest.report.model import Finding

EXPLANATION = (
    "This text lies entirely outside the displayed area of the page. The page "
    "shows ({vx0:.2f}, {vy0:.2f}) to ({vx1:.2f}, {vy1:.2f}) in PDF units, while "
    "the text occupies ({x0:.2f}, {y0:.2f}) to ({x1:.2f}, {y1:.2f}). It is "
    "returned by text extraction in full and appears nowhere in the rendered "
    "document, so a reader and an automated consumer of this file receive "
    "different content."
)


class OutsidePageDetector:
    """Reports runs whose bounding box falls wholly beyond the visible area."""

    name = "text_outside_page_area"

    def __init__(self, path: str) -> None:
        self._path = path

    def run(self, runs: list[TextRun]) -> list[Finding]:
        findings = []
        for text_run in runs:
            offset_x, offset_y, width, height = visible_area(self._path, text_run.page)
            visible_x1 = offset_x + width
            visible_y1 = offset_y + height
            # Wholly outside means the two rectangles do not overlap at all.
            # Anything less than that is not reported: text crossing the edge of
            # the page is ordinary -- a rule bled to the trim, a header running
            # into the margin -- and a detector firing on it would bury the case
            # it exists for. Touching edges count as outside, since an overlap of
            # zero width shows nothing.
            outside = (
                text_run.x1 <= offset_x
                or text_run.x0 >= visible_x1
                or text_run.y1 <= offset_y
                or text_run.y0 >= visible_y1
            )
            if not outside:
                continue
            findings.append(
                Finding(
                    detector=self.name,
                    severity=SEVERITY_HIGH,
                    location=format_location(
                        text_run.page,
                        text_run.x0,
                        text_run.y0,
                        text_run.x1,
                        text_run.y1,
                    ),
                    evidence=format_evidence(text_run.text),
                    explanation=EXPLANATION.format(
                        vx0=offset_x,
                        vy0=offset_y,
                        vx1=visible_x1,
                        vy1=visible_y1,
                        x0=text_run.x0,
                        y0=text_run.y0,
                        x1=text_run.x1,
                        y1=text_run.y1,
                    ),
                )
            )
        return findings
