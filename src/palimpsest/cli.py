"""Command line interface for Palimpsest-doc."""

import argparse

from palimpsest import __version__


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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(__version__)
        return 0

    parser.print_help()
    return 0
