"""Detector for text too small to be read from the page."""

from palimpsest.integrity.detectors.base import (
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    format_evidence,
    format_location,
)
from palimpsest.integrity.model import TextRun
from palimpsest.report.model import Finding

# Effective font size, in points, below which text is not legible to a human
# under any viewing condition. Typography below one point cannot be resolved by
# the eye at normal viewing distance, and zooming a scanned or printed copy does
# not recover it.
MIN_LEGIBLE_FONT_SIZE = 1.0

ZERO_EXPLANATION = (
    "This text is drawn at an effective font size of zero, so it covers no area "
    "of the page and cannot be seen, while remaining present in the file and "
    "returned by text extraction."
)

SMALL_EXPLANATION = (
    "This text is drawn at an effective font size of {size:g} points, below the "
    "{threshold:g} point limit of human legibility, while remaining present in "
    "the file and returned by text extraction. A reader and an automated "
    "consumer of this file therefore receive different content."
)

# Appended when the size is negative, so that the number quoted in the finding
# and the number a reader will see on opening the file are both present.
NEGATIVE_SIZE_NOTE = (
    " The file records this size as {actual:g} points; the sign comes from a "
    "transformation matrix that flips the text, and legibility follows the "
    "magnitude."
)


class TinyTextDetector:
    """Reports runs whose effective font size is below the legibility limit."""

    name = "sub_legible_font_size"

    def run(self, runs: list[TextRun]) -> list[Finding]:
        findings = []
        for text_run in runs:
            # Blank runs hide nothing, and reporting them would train the reader
            # to ignore this detector's output.
            if not text_run.text.strip():
                continue
            # Compared by absolute value. A negative size comes from a
            # transformation matrix with a negative scale, which flips the text
            # rather than shrinking it: -12 points is ordinary text upside down,
            # perfectly readable, and reporting it would be a false positive.
            size = abs(text_run.font_size)
            if size >= MIN_LEGIBLE_FONT_SIZE:
                continue
            zero = size == 0
            explanation = (
                ZERO_EXPLANATION
                if zero
                else SMALL_EXPLANATION.format(size=size, threshold=MIN_LEGIBLE_FONT_SIZE)
            )
            if text_run.font_size < 0:
                explanation += NEGATIVE_SIZE_NOTE.format(actual=text_run.font_size)
            findings.append(
                Finding(
                    detector=self.name,
                    severity=SEVERITY_HIGH if zero else SEVERITY_MEDIUM,
                    location=format_location(
                        text_run.page,
                        text_run.x0,
                        text_run.y0,
                        text_run.x1,
                        text_run.y1,
                    ),
                    evidence=format_evidence(text_run.text),
                    explanation=explanation,
                )
            )
        return findings
