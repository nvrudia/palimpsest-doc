"""Detector for text that is present in the file but never painted.

Modes 3 and 7 were checked against a real renderer rather than taken from the
specification alone: a page carrying both was rasterised, and neither fragment
produced a single non-white pixel, while modes 0-2 and 4-6 did.
"""

from palimpsest.integrity.detectors.base import (
    SEVERITY_HIGH,
    format_evidence,
    format_location,
)
from palimpsest.integrity.model import TextRun
from palimpsest.report.model import Finding

# Text render modes that put nothing on the page. Mode 3 paints neither fill nor
# stroke; mode 7 only adds the glyphs to the clipping path. Modes 4, 5 and 6 also
# touch the clipping path but still fill or stroke, so the text stays visible and
# is not a finding.
INVISIBLE_RENDER_MODES = frozenset({3, 7})

EXPLANATION = (
    "This text is present in the file and is returned by text extraction, but "
    "text render mode {mode} paints nothing on the page, so it does not appear "
    "in the rendered document. A reader and an automated consumer of this file "
    "therefore receive different content."
)


class InvisibleTextDetector:
    """Reports runs drawn in a render mode that produces no visible marks."""

    name = "invisible_render_mode"

    def run(self, runs: list[TextRun]) -> list[Finding]:
        findings = []
        for text_run in runs:
            # render_mode is None when the parser could not supply it, and may
            # hold any integer the file contained, including values outside the
            # 0-7 range the specification defines. Membership covers all three
            # cases: absent data and undefined values are not findings.
            if text_run.render_mode not in INVISIBLE_RENDER_MODES:
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
                    explanation=EXPLANATION.format(mode=text_run.render_mode),
                )
            )
        return findings
