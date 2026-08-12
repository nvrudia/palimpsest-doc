"""Show that text set in a font without the glyphs for it is substituted, not refused.

A font is chosen together with an encoding, and the encoding decides which characters can be
resolved to a glyph at all. Helvetica is carried by WinAnsi, which covers the Latin range and
nothing beyond it. Reportlab splits each string into runs by what the current font can
resolve, writes the resolvable runs in that font, and writes the rest in another one, glyph
for glyph. The count of characters is preserved, because every character is still written;
what changes is which glyph each one points at.

Nothing in this raises, warns or fails: the file is valid, it opens, and text extraction
returns a string of the length that was written. The divergence falls unevenly, because it
falls on whatever the encoding does not cover, which is every script but one.

Run it with: python reproduction/03_silent_substitution.py
"""

import importlib.util
import os
import shutil
import struct
import sys
import tempfile
import textwrap
import warnings
from importlib.metadata import version
from pathlib import Path
from typing import NamedTuple

# Every third-party import in this file sits inside the function that uses it. The script has
# to be able to report a missing library as a sentence rather than as a traceback, and an
# import at module level would run before check_dependencies could say anything.

LINE_WIDTH = 78

# Module name to the distribution that provides it, which pip needs and which differs for
# pdfminer.six. pdfplumber takes no part here: nothing is read through it.
REQUIRED_MODULES = {"reportlab": "reportlab", "pdfminer": "pdfminer.six"}

PAGE_SIZE = (612.0, 792.0)
LEFT_MARGIN = 72
FIRST_LINE_TOP = 720
LINE_SPACING = 20
FONT_SIZE = 12.0

# One of the standard 14, carried by WinAnsi. This is the font under examination.
LATIN_FONT = "Helvetica"
CONTROL_FONT = "ControlFont"

LATIN_TEXT = "Party shall pay a penalty"
CYRILLIC_TEXT = "Сторона сплачує неустойку"
MIXED_TEXT = "Party / Сторона 500 EUR"
GREEK_TEXT = "Συμβαλλόμενο μέρος"

# Parts 1 and 3: one line of each kind, including one that mixes two scripts. Greek is here
# as well as in part 4 because the two substitutions do not cost the same: one is obviously
# broken on sight, the other reads as an ordinary Latin word, and the table has to show both.
SUBSTITUTION_LINES = (
    ("latin", LATIN_TEXT),
    ("cyrillic", CYRILLIC_TEXT),
    ("mixed", MIXED_TEXT),
    ("greek", GREEK_TEXT),
)

# Part 4: one line per script, to put a number on how unevenly this falls.
SCRIPT_LINES = (
    ("latin", LATIN_TEXT),
    ("cyrillic", CYRILLIC_TEXT),
    ("greek", GREEK_TEXT),
)

SCRIPT_RANGES = {
    "latin": ((0x0041, 0x005A), (0x0061, 0x007A)),
    "cyrillic": ((0x0400, 0x04FF),),
    "greek": ((0x0370, 0x03FF),),
}

# Font files that carry more than the Latin range, by the names they are installed under.
CONTROL_FONT_FILES = (
    "arial.ttf",
    "tahoma.ttf",
    "verdana.ttf",
    "segoeui.ttf",
    "DejaVuSans.ttf",
    "LiberationSans-Regular.ttf",
    "FreeSans.ttf",
    "NotoSans-Regular.ttf",
    "Arial.ttf",
    "Verdana.ttf",
)

# Searched in addition to reportlab's own TTFSearchPath, which it fills in per platform.
CONTROL_FONT_DIRECTORIES = (
    r"C:\Windows\Fonts",
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    "/usr/share/fonts/TTF",
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/freefont",
    "/usr/share/fonts/truetype/noto",
    "/System/Library/Fonts/Supplemental",
    "/Library/Fonts",
)

LABEL_COLUMN = 11
LENGTH_COLUMN = 7
VERDICT_COLUMN = 7
FONTS_COLUMN = 21

EXPECTED_PAGES = 1


class ExtractedLine(NamedTuple):
    """One line read back out of a file, with the fonts its characters were drawn in."""

    text: str
    fonts: tuple[str, ...]


def _heading(title: str) -> str:
    """A section title framed in dashes."""
    rule = "-" * LINE_WIDTH
    return f"\n{rule}\n{title}\n{rule}"


def _script_of(character: str) -> str | None:
    """The script a character belongs to, or None for digits, spaces and punctuation."""
    point = ord(character)
    for script, ranges in SCRIPT_RANGES.items():
        if any(low <= point <= high for low, high in ranges):
            return script
    return None


# The characters actually used below, grouped by script. A control font is judged against
# these rather than against a range, so the test is of what the script needs.
SCRIPT_CHARACTERS = {
    script: sorted(
        {
            character
            for _, text in (*SUBSTITUTION_LINES, *SCRIPT_LINES)
            for character in text
            if _script_of(character) == script
        }
    )
    for script in SCRIPT_RANGES
}


def _search_directories() -> list[str]:
    """Where a control font is looked for, reportlab's own paths included."""
    from reportlab import rl_config

    directories: list[str] = []
    seen: set[str] = set()
    for directory in (*CONTROL_FONT_DIRECTORIES, *rl_config.TTFSearchPath):
        # normcase so that a path reportlab spells differently from the list above is
        # recognised as the same directory rather than searched and reported twice.
        key = os.path.normcase(os.path.abspath(directory))
        if key not in seen:
            seen.add(key)
            directories.append(directory)
    return directories


def _coverage(path: str) -> dict[str, bool] | None:
    """Which scripts a font file has glyphs for, or None if it cannot be read.

    The test is against the font's own character map, not against its file name. A font
    picked for a control by name alone could turn out to substitute exactly as the font
    under examination does, and the control would then confirm nothing.
    """
    from reportlab.pdfbase.ttfonts import TTFError, TTFontFile

    try:
        face = TTFontFile(path)
    except (TTFError, OSError, ValueError, struct.error):
        # A font file that cannot be read or parsed is not a candidate, whether because the
        # name matched something that is not a font or because it is one this parser does
        # not handle. The search moves past it.
        return None
    return {
        script: all(ord(character) in face.charToGlyph for character in characters)
        for script, characters in SCRIPT_CHARACTERS.items()
    }


def _font_name(name: str) -> str:
    """A font's name without the subset tag a writer puts in front of it.

    A subset is named like 'ABCDEF+Arial'. The tag identifies the subset, not the face, and
    it changes between runs of some writers, which would make the output differ each time.
    """
    prefix, separator, rest = str(name).partition("+")
    subset_tag_length = 6
    if separator and len(prefix) == subset_tag_length and prefix.isalpha():
        return rest
    return name


def _read_lines(path: str) -> list[ExtractedLine]:
    """Each line of the file, in the order it was written, with the fonts it was drawn in.

    Characters are grouped by the baseline their text matrix places them on. Layout analysis
    is left off: it breaks a line apart wherever glyph widths jump, which is exactly what
    substituted glyphs do, and the line would then be reported in pieces.
    """
    from pdfminer.converter import PDFLayoutAnalyzer
    from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
    from pdfminer.pdfpage import PDFPage

    class LineReader(PDFLayoutAnalyzer):
        def __init__(self, resources: PDFResourceManager) -> None:
            super().__init__(resources, pageno=1, laparams=None)
            self.characters: list[tuple[float, str, str]] = []

        def render_char(
            self, matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate
        ) -> float:
            self.characters.append(
                (round(matrix[5], 1), font.to_unichr(cid), _font_name(font.fontname))
            )
            return super().render_char(
                matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate
            )

    resources = PDFResourceManager()
    reader = LineReader(resources)
    interpreter = PDFPageInterpreter(resources, reader)
    try:
        with open(path, "rb") as handle:
            for page in PDFPage.get_pages(handle):
                interpreter.process_page(page)
    finally:
        reader.close()

    lines: list[ExtractedLine] = []
    current: list[str] = []
    fonts: list[str] = []
    baseline: float | None = None
    for position, character, font in reader.characters:
        if baseline is not None and position != baseline:
            lines.append(ExtractedLine("".join(current), tuple(fonts)))
            current, fonts = [], []
        baseline = position
        current.append(character)
        if font not in fonts:
            fonts.append(font)
    if current:
        lines.append(ExtractedLine("".join(current), tuple(fonts)))
    return lines


def _print_comparison(samples: tuple[tuple[str, str], ...], lines: list[ExtractedLine]) -> bool:
    """Print what was written against what came back; return whether lengths all matched.

    The substitution column is what separates the two kinds of loss. Characters sent to
    ZapfDingbats come back as a run of one letter and are broken on sight; characters sent
    to Symbol come back as ordinary Latin words that read as though they were meant. The
    extracted text sits directly under the written text so the two can be compared as they
    are, without either being described.
    """
    # The first sample is Latin throughout, so it is drawn wholly in the font the document
    # was set in, and every other face on the page is therefore a substitute.
    if len(lines[0].fonts) != 1:
        raise RuntimeError(
            f"the Latin sample was drawn in {lines[0].fonts}, so the font the document was "
            "set in cannot be told apart from the fonts substituted for it"
        )
    primary = lines[0].fonts[0]

    header = (
        f"{'sample':<{LABEL_COLUMN}}{'length':<{LENGTH_COLUMN}}"
        f"{'same':<{VERDICT_COLUMN}}{'substituted into':<{FONTS_COLUMN}}"
    )
    print(f"{header}written, then extracted")
    print("-" * LINE_WIDTH)
    matched = True
    indent = LABEL_COLUMN + LENGTH_COLUMN + VERDICT_COLUMN + FONTS_COLUMN
    for (label, written), line in zip(samples, lines, strict=True):
        matched = matched and len(written) == len(line.text)
        lengths = f"{len(written)}/{len(line.text)}"
        verdict = str(written == line.text)
        substitutes = "+".join(font for font in line.fonts if font != primary) or "-"
        row = (
            f"{label:<{LABEL_COLUMN}}{lengths:<{LENGTH_COLUMN}}"
            f"{verdict:<{VERDICT_COLUMN}}{substitutes:<{FONTS_COLUMN}}"
        )
        print(f"{row}{written!r}")
        print(f"{'':<{indent}}{line.text!r}")
    return matched


def check_dependencies() -> None:
    """Confirm the demonstration libraries are importable, or say which one is not."""
    missing = [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]
    if not missing:
        return
    print("This script needs libraries that the palimpsest-doc package does not depend on.")
    print(f"Not importable: {', '.join(missing)}")
    print()
    print("Install with:")
    print(f"    pip install {' '.join(REQUIRED_MODULES[name] for name in missing)}")
    sys.exit(1)


def find_control_font() -> tuple[str, dict[str, bool]] | None:
    """The first installed font carrying Cyrillic, preferring one that carries every script."""
    partial: tuple[str, dict[str, bool]] | None = None
    for directory in _search_directories():
        for name in CONTROL_FONT_FILES:
            path = os.path.join(directory, name)
            if not os.path.isfile(path):
                continue
            coverage = _coverage(path)
            if coverage is None or not coverage["cyrillic"]:
                continue
            if all(coverage.values()):
                return path, coverage
            # Usable, but something is missing. Kept in case nothing better turns up, so
            # that what it does cover is still shown rather than dropped.
            partial = partial or (path, coverage)
    return partial


def build_document(path: str, font: str, lines: tuple[tuple[str, str], ...]) -> None:
    """Write one line per sample, all in the given font."""
    from reportlab.pdfgen import canvas

    page = canvas.Canvas(path, pagesize=PAGE_SIZE)
    top = FIRST_LINE_TOP
    for _, text in lines:
        item = page.beginText(LEFT_MARGIN, top)
        item.setFont(font, FONT_SIZE)
        item.textLine(text)
        page.drawText(item)
        top -= LINE_SPACING
    page.showPage()
    page.save()


def show_substitution(path: str) -> None:
    """Part 1: what was written, what comes back, and what that costs each script."""
    print(_heading("PART 1 - WHAT IS WRITTEN AND WHAT COMES BACK"))
    print(f"\nEvery line below was set in {LATIN_FONT}, which WinAnsi carries.\n")

    extracted = _read_lines(path)
    matched = _print_comparison(SUBSTITUTION_LINES, extracted)
    print(f"\nThe extracted length equals the written length in every sample: {matched}")

    # The mixed sample is the one that matters most: a line half of which survives reads as
    # an ordinary line, and nothing about it invites a second look.
    written = MIXED_TEXT
    got = extracted[[label for label, _ in SUBSTITUTION_LINES].index("mixed")].text
    print(f"\nWithin the mixed sample, {written!r}, by script:")
    for script in SCRIPT_RANGES:
        total = [_script_of(character) for character in written].count(script)
        if not total:
            continue
        kept = sum(
            1
            for before, after in zip(written, got, strict=True)
            if _script_of(before) == script and before == after
        )
        print(f"    {script:<11} {kept} of {total} characters kept")


def show_absence_of_signal(path: str, raised: list[warnings.WarningMessage]) -> None:
    """Part 2: nothing was raised, and the file that came out is valid."""
    from pdfminer.pdfpage import PDFPage

    print(_heading("PART 2 - WHAT THE GENERATION REPORTED"))

    print(f"\nWarnings recorded while the file was written: {len(raised)}")
    for caught in raised:
        print(f"    {caught.category.__name__}: {caught.message}")
    print("Exceptions raised: none, or this line would not be reached")

    with open(path, "rb") as handle:
        pages = len(list(PDFPage.get_pages(handle)))
    lines = _read_lines(path)
    print("\nThe file opens: True")
    print(f"Pages found: {pages}, expected {EXPECTED_PAGES}")
    print(f"Lines of text extracted: {len(lines)}, expected {len(SUBSTITUTION_LINES)}")


def show_control(path: str | None, control: tuple[str, dict[str, bool]] | None) -> None:
    """Part 3: the same text in a font that has the glyphs, where one can be found."""
    print(_heading("PART 3 - THE SAME TEXT IN A FONT THAT HAS THE GLYPHS"))

    if control is None or path is None:
        print("\nSkipped: no installed font carrying Cyrillic glyphs was found.")
        print("Only this part needs one, so the rest of the script stands.")
        print("\nDirectories searched:")
        for directory in _search_directories():
            print(f"    {directory}")
        print("\nFile names looked for:")
        for name in CONTROL_FONT_FILES:
            print(f"    {name}")
        return

    font_path, coverage = control
    covered = [script for script, present in coverage.items() if present]
    missing = [script for script, present in coverage.items() if not present]

    print(f"\nControl font: {os.path.basename(font_path)}, from {os.path.dirname(font_path)}")
    print(f"Glyphs present for: {', '.join(covered)}")
    if missing:
        print(f"No glyphs for: {', '.join(missing)}")
        print("That is a property of this font, not of the text; part 4 reads the same")
        print("scripts through the Latin-set font and is unaffected.")
    print()

    _print_comparison(SUBSTITUTION_LINES, _read_lines(path))


def show_distribution(path: str, control: tuple[str, dict[str, bool]] | None) -> None:
    """Part 4: the share of each script that survives the Latin-set font."""
    print(_heading("PART 4 - HOW UNEVENLY THIS FALLS"))
    print(f"\nOne line per script, all set in {LATIN_FONT}. Only characters of the script")
    print("itself are counted; spaces, digits and punctuation are left out.\n")

    extracted = _read_lines(path)
    print(f"{'script':<{LABEL_COLUMN}}{'characters':<13}{'kept':<8}share")
    print("-" * LINE_WIDTH)
    for (script, written), line in zip(SCRIPT_LINES, extracted, strict=True):
        total = sum(1 for character in written if _script_of(character) == script)
        kept = sum(
            1
            for before, after in zip(written, line.text, strict=True)
            if _script_of(before) == script and before == after
        )
        share = f"{kept / total:.0%}" if total else "-"
        print(f"{script:<{LABEL_COLUMN}}{total:<13}{kept:<8}{share}")

    if control is None:
        print("\nNo control font was found, so these figures stand on their own: they say")
        print("what this font resolves, not what the characters are capable of.")
        return
    _, coverage = control
    carried = ", ".join(script for script, present in coverage.items() if present)
    print()
    # Wrapped rather than split by hand: the list of scripts varies with the font found.
    for line in textwrap.wrap(
        f"The control font in part 3 carries: {carried}. The zeros above are therefore a "
        "property of the encoding the text was set in, not of the characters.",
        LINE_WIDTH,
    ):
        print(line)


def main() -> None:
    """Build the samples, print the four parts, and leave nothing behind."""
    check_dependencies()
    directory = tempfile.mkdtemp()
    try:
        latin_path = str(Path(directory) / "latin.pdf")
        scripts_path = str(Path(directory) / "scripts.pdf")

        # Recorded around the generation itself, which is the moment a substitution would be
        # the thing to report. simplefilter keeps a warning from being suppressed as a repeat.
        with warnings.catch_warnings(record=True) as raised:
            warnings.simplefilter("always")
            build_document(latin_path, LATIN_FONT, SUBSTITUTION_LINES)

        build_document(scripts_path, LATIN_FONT, SCRIPT_LINES)

        control = find_control_font()
        control_path = None
        if control is not None:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont

            pdfmetrics.registerFont(TTFont(CONTROL_FONT, control[0]))
            control_path = str(Path(directory) / "control.pdf")
            build_document(control_path, CONTROL_FONT, SUBSTITUTION_LINES)

        show_substitution(latin_path)
        show_absence_of_signal(latin_path, list(raised))
        show_control(control_path, control)
        show_distribution(scripts_path, control)

        print(_heading("ENVIRONMENT"))
        print()
        print(f"    {'python':<16} {'.'.join(str(part) for part in sys.version_info[:3])}")
        for distribution in ("reportlab", "pdfminer.six"):
            print(f"    {distribution:<16} {version(distribution)}")
    finally:
        shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    main()
