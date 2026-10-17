"""Assembly of the report for one document.

Pure computation: nothing is printed and nothing is written to disk. The caller
decides what to do with the result.
"""

import hashlib
from datetime import UTC, datetime
from importlib.metadata import version

from palimpsest import __version__
from palimpsest.integrity.detectors.base import Detector
from palimpsest.integrity.extract import extract_document, group_runs
from palimpsest.integrity.model import DocumentFacts, TextRun
from palimpsest.report.model import Coverage, Finding, Report, SkippedPage, SourceDocument

# A PDF is identified by its header, never by the file extension: the extension
# is metadata a user can set to anything, while the header is the thing every
# reader actually dispatches on.
PDF_MAGIC = b"%PDF-"
PDF_MEDIA_TYPE = "application/pdf"

# Parsers whose versions are recorded in every report. A finding is only
# reproducible if the code that produced it can be identified, so these are read
# from the installed distributions rather than written down here. The field
# answers "what produced this result", so a library that took no part in the
# analysis does not belong in it.
#
# pypdfium2 joined the list when rendering became part of the analysis rather
# than a test aid. Two detectors measure the rendered page, and the visibility
# of a text render mode is now a measurement taken from PDFium; neither can be
# reproduced by someone who does not know which version produced them.
PARSER_DISTRIBUTIONS = ("pdfminer.six", "pypdfium2")

# What this tool does not examine, stated as facts about the tool. Every entry
# was established by measurement: a document carrying the content in question
# was scanned, and the content never reached a detector.
#
# The list is constant. The limits of the check do not depend on the document
# being checked, and a reader comparing two reports must not have to wonder
# whether a limit was omitted because it did not apply.
NOT_CHECKED = (
    "annotations",
    "form field values",
    "embedded files",
    "text layer of scanned pages against the page image",
    "objects obscured by other objects",
    "formats other than PDF",
    "pages with /Rotate containing text (scan is refused)",
)

# Said of a document that opened without a password while still carrying an
# encryption dictionary: the restrictions in it are owner restrictions, which
# this tool neither reads nor enforces.
OWNER_PASSWORD_NOTE = "document is encrypted with an owner password; permissions not evaluated"

# Why a page was not examined. A page reaches a detector only by way of a text
# run, so a page that produced none was walked but never looked at.
NO_TEXT_LAYER = "no text layer"
ROTATED_NO_TEXT_LAYER = "rotated page, no text layer"

_HASH_CHUNK_BYTES = 1 << 16


def _digest_and_size(path: str) -> tuple[str, int, bytes]:
    """Return the SHA-256 hex digest, the byte length and the opening bytes."""
    digest = hashlib.sha256()
    size = 0
    head = b""
    try:
        with open(path, "rb") as handle:
            while chunk := handle.read(_HASH_CHUNK_BYTES):
                if not head:
                    head = chunk[: len(PDF_MAGIC)]
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise ValueError(f"Cannot read {path!r}: {exc}") from exc
    return digest.hexdigest(), size, head


def _media_type(head: bytes, path: str) -> str:
    """Identify the document type from its opening bytes."""
    if head.startswith(PDF_MAGIC):
        return PDF_MEDIA_TYPE
    raise ValueError(f"{path!r} is not a PDF: it does not begin with {PDF_MAGIC.decode('ascii')}")


def _parser_versions() -> dict[str, str]:
    """Installed versions of the libraries that produced the extraction."""
    return {name: version(name) for name in PARSER_DISTRIBUTIONS}


def _created_at() -> str:
    """Current UTC time, ISO 8601 with a Z suffix."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _coverage(detectors: list[Detector], facts: DocumentFacts, runs: list[TextRun]) -> Coverage:
    """State what the scan covered.

    A page is counted as analysed when at least one text run was found on it,
    because a run is the only thing a detector is given. A page that yielded
    none was walked by the interpreter and then seen by nothing, which is not
    the same as a page on which nothing was found.

    The detector names are taken from the detectors that actually ran, not from
    a list written here. A list written here would go on being correct in the
    report long after it had stopped being correct in the tool.
    """
    examined = {run.page for run in runs}
    skipped = [
        SkippedPage(
            page=page.number,
            reason=ROTATED_NO_TEXT_LAYER if page.rotation else NO_TEXT_LAYER,
        )
        for page in facts.pages
        if page.number not in examined
    ]
    return Coverage(
        detectors_run=[detector.name for detector in detectors],
        pages_total=len(facts.pages),
        pages_analysed=len(facts.pages) - len(skipped),
        pages_skipped=skipped,
        not_checked=list(NOT_CHECKED),
        notes=[OWNER_PASSWORD_NOTE] if facts.encrypted else [],
    )


def build_report(path: str, detectors: list[Detector]) -> Report:
    """Run every detector over one document and assemble the report.

    Detectors run in the order given, and their findings are concatenated in
    that same order, with no sorting and no regrouping. Two runs over one
    unchanged file must produce byte-identical findings, in identical order:
    evidence that reorders itself between runs cannot be cited.

    Raises ValueError if the file cannot be read or is not a PDF.
    """
    sha256, size_bytes, head = _digest_and_size(path)
    media_type = _media_type(head, path)

    glyphs, facts = extract_document(path)
    runs = group_runs(glyphs)

    findings: list[Finding] = []
    for detector in detectors:
        findings.extend(detector.run(runs))

    return Report(
        source=SourceDocument(
            path=path,
            sha256=sha256,
            size_bytes=size_bytes,
            media_type=media_type,
        ),
        tool_version=__version__,
        created_at=_created_at(),
        findings=findings,
        parser_versions=_parser_versions(),
        coverage=_coverage(detectors, facts, runs),
    )
