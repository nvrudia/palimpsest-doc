"""Command line interface for Palimpsest-doc."""

import argparse
import sys
from typing import TextIO

from palimpsest import __version__
from palimpsest.integrity.detectors.base import Detector
from palimpsest.integrity.detectors.invisible_text import InvisibleTextDetector
from palimpsest.integrity.detectors.tiny_text import TinyTextDetector
from palimpsest.report.build import build_report
from palimpsest.report.model import Report

# Exit codes follow the convention of code analysers, so the tool can sit in a
# pipeline without anyone parsing its output. The three are kept strictly
# separate: 1 states that the file was read, the analysis finished and findings
# exist. Nothing else may produce it.
EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2

# The order detectors run in is the order their findings appear in the report,
# and that order has to hold between runs on the same file.
DETECTORS: list[Detector] = [InvisibleTextDetector(), TinyTextDetector()]


def _force_utf8(stream: TextIO) -> None:
    """Write UTF-8 regardless of the locale of the machine.

    Reports quote documents verbatim, and JSON is defined as UTF-8. On a
    Windows console a redirected stream defaults to the ANSI code page, which
    silently produces mis-encoded output and raises on any character the page
    cannot represent.

    errors="replace" is deliberate: a damaged character in the report is a
    better outcome than a traceback in place of the report. Streams that cannot
    be reconfigured at all, such as the substitutes a test harness installs, are
    left as they are.
    """
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError):
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="palimpsest",
        description="Detect divergence between what a human reads and what a pipeline ingests.",
    )
    # Handled manually rather than with argparse's "version" action, which exits
    # the process instead of returning control to main().
    parser.add_argument(
        "--version",
        action="store_true",
        help="print the version and exit",
    )
    subparsers = parser.add_subparsers(dest="command")
    scan = subparsers.add_parser(
        "scan",
        help="scan a document for structural anomalies",
        description="Scan a document and report structural anomalies.",
    )
    scan.add_argument("file", help="path to the document to scan")
    scan.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print the report as JSON and nothing else",
    )
    return parser


def format_report(report: Report) -> str:
    """Render a report for reading, in a form that can be quoted as evidence.

    The header carries the digest and the timestamp, without which a conclusion
    is not tied to any particular file and proves nothing.
    """
    lines = [
        f"file:     {report.source.path}",
        f"sha256:   {report.source.sha256}",
        f"size:     {report.source.size_bytes} bytes",
        f"type:     {report.source.media_type}",
        f"scanned:  {report.created_at}",
        f"tool:     palimpsest {report.tool_version}",
        f"findings: {len(report.findings)}",
    ]
    for number, finding in enumerate(report.findings, start=1):
        lines.append("")
        lines.append(f"[{number}] {finding.detector} ({finding.severity})")
        lines.append(f"    location:    {finding.location}")
        # Evidence is quoted exactly as it stands in the document, so it is not
        # indented, wrapped or escaped. A run containing a line break therefore
        # continues at the left margin: the layout gives way to the quotation,
        # not the other way round.
        lines.append(f"    evidence:    {finding.evidence}")
        lines.append(f"    explanation: {finding.explanation}")
    return "\n".join(lines)


def scan(path: str, as_json: bool) -> int:
    """Scan one document and print the report.

    Every failure returns EXIT_ERROR. A document that parses but contains no
    text at all is not a failure: an empty report with no findings is the
    correct answer, and returns EXIT_CLEAN.
    """
    try:
        report = build_report(path, DETECTORS)
        print(report.to_json() if as_json else format_report(report))
    except Exception as exc:  # noqa: BLE001 - see EXIT_ERROR above
        # Anything at all: an unreadable file, a malformed document, a parser
        # defect. All of it is reported as an error rather than as a clean
        # result or as a finding, so that the exit codes stay unambiguous.
        print(f"palimpsest: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_FINDINGS if report.findings else EXIT_CLEAN


def main(argv: list[str] | None = None) -> int:
    _force_utf8(sys.stdout)
    _force_utf8(sys.stderr)

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(__version__)
        return 0

    if args.command == "scan":
        return scan(args.file, args.as_json)

    parser.print_help()
    return 0
