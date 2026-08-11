"""Assembly of the report for one document.

Pure computation: nothing is printed and nothing is written to disk. The caller
decides what to do with the result.
"""

import hashlib
from datetime import UTC, datetime
from importlib.metadata import version

from palimpsest import __version__
from palimpsest.integrity.detectors.base import Detector
from palimpsest.integrity.extract import extract_glyphs, group_runs
from palimpsest.report.model import Finding, Report, SourceDocument

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
PARSER_DISTRIBUTIONS = ("pdfminer.six",)

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

    runs = group_runs(extract_glyphs(path))

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
    )
