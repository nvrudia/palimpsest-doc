from palimpsest import __version__
from palimpsest.cli import main
from palimpsest.report.model import Report, SourceDocument


def test_version_is_not_empty() -> None:
    assert __version__


def test_cli_version_returns_zero() -> None:
    assert main(["--version"]) == 0


def test_report_to_dict_has_expected_keys() -> None:
    report = Report(
        source=SourceDocument(
            path="example.pdf",
            sha256="0" * 64,
            size_bytes=0,
            media_type="application/pdf",
        ),
        tool_version=__version__,
        created_at="1970-01-01T00:00:00Z",
    )
    data = report.to_dict()
    assert "source" in data
    assert "findings" in data
    assert "tool_version" in data
