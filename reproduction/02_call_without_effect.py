"""Show that setTextRenderMode(0) writes no operator, and what the page then carries.

The decision is taken against reportlab's own record of the state. setTextRenderMode writes an
operator only when the mode it is asked for differs from self._textRenderMode, and that
counter belongs to the individual text object: beginText hands back an object whose counter is
zero, whatever mode the page is actually in. A reset to 0 on a fresh text object therefore
matches the counter, the guard holds, and nothing is written.

The render mode is part of the graphics state, so it outlives BT/ET and is ended by Q alone.
Between the library's record and the state of the document there is thus a gap, and every
fragment written after an unpainted one falls into it: the code asks for a visible fragment,
the call reports success, and the file carries mode 3.

Run it with: python reproduction/02_call_without_effect.py
"""

import importlib.util
import inspect
import io
import re
import shutil
import sys
import tempfile
import textwrap
from importlib.metadata import version
from pathlib import Path

# Every third-party import in this file sits inside the function that uses it. The script has
# to be able to report a missing library as a sentence rather than as a traceback, and an
# import at module level would run before check_dependencies could say anything.

LINE_WIDTH = 78

# Module name to the distribution that provides it, which pip needs and which differs for
# pdfminer.six. pdfplumber takes no part here: neither variant is read through it.
REQUIRED_MODULES = {"reportlab": "reportlab", "pdfminer": "pdfminer.six"}

PAGE_SIZE = (612.0, 792.0)
FONT_NAME = "Helvetica"
FONT_SIZE = 12.0
LEFT_MARGIN = 72
FIRST_LINE_TOP = 720
LINE_SPACING = 20

DEFAULT_RENDER_MODE = 0
HIDDEN_RENDER_MODE = 3

# One intent, written two ways below: an unpainted fragment between two painted ones.
FRAGMENTS = (
    ("FIRST VISIBLE PARAGRAPH", DEFAULT_RENDER_MODE),
    ("HIDDEN INSTRUCTION MARKER", HIDDEN_RENDER_MODE),
    ("SECOND VISIBLE PARAGRAPH", DEFAULT_RENDER_MODE),
)

VARIANTS = {
    "A": "reset attempted with setTextRenderMode(0)",
    "B": "enclosed in saveState/restoreState",
}

TEXT_COLUMN = 29
MODE_COLUMN = 11


def _heading(title: str) -> str:
    """A section title framed in dashes."""
    rule = "-" * LINE_WIDTH
    return f"\n{rule}\n{title}\n{rule}"


def _page_stream(path: str) -> bytes:
    """The content stream of every page, with any filters already undone."""
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdftypes import resolve1

    with open(path, "rb") as handle:
        # get_data applies the stream's filters, so what comes back is the operators
        # themselves rather than the compressed bytes they are stored as.
        return b"".join(
            resolve1(content).get_data()
            for page in PDFPage.get_pages(handle)
            for content in page.contents
        )


def _read_fragment_modes(path: str) -> list[tuple[str, int]]:
    """Every drawn fragment with the render mode its text state carried."""
    from pdfminer.converter import PDFLayoutAnalyzer
    from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
    from pdfminer.pdfpage import PDFPage

    class ModeReader(PDFLayoutAnalyzer):
        """render_string is given the mode, render_char the characters it applies to."""

        def __init__(self, resources: PDFResourceManager) -> None:
            super().__init__(resources, pageno=1, laparams=None)
            self.fragments: list[tuple[str, int]] = []
            self._mode = DEFAULT_RENDER_MODE
            self._current: list[str] = []

        def render_string(self, textstate, seq, ncs, graphicstate) -> None:
            self._mode = textstate.render
            self._current = []
            super().render_string(textstate, seq, ncs, graphicstate)
            if self._current:
                self.fragments.append(("".join(self._current), self._mode))

        def render_char(
            self, matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate
        ) -> float:
            self._current.append(font.to_unichr(cid))
            return super().render_char(
                matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate
            )

    resources = PDFResourceManager()
    reader = ModeReader(resources)
    interpreter = PDFPageInterpreter(resources, reader)
    try:
        with open(path, "rb") as handle:
            for page in PDFPage.get_pages(handle):
                interpreter.process_page(page)
    finally:
        reader.close()
    return reader.fragments


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


def build_variant(path: str, variant: str) -> list[int]:
    """Write one page of FRAGMENTS and return the modes the code asked reportlab for."""
    from reportlab.pdfgen import canvas

    page = canvas.Canvas(path, pagesize=PAGE_SIZE)
    requested: list[int] = []
    previous = DEFAULT_RENDER_MODE
    top = FIRST_LINE_TOP

    for text, intended in FRAGMENTS:
        enclose = variant == "B" and intended != DEFAULT_RENDER_MODE
        if enclose:
            page.saveState()
        item = page.beginText(LEFT_MARGIN, top)
        item.setFont(FONT_NAME, FONT_SIZE)
        # A asks for the mode wherever the intent changes, which is how it reads when the
        # mode is taken for a property of the text. B asks only where a mode is wanted and
        # leaves the ending to restoreState.
        if intended != previous and (variant == "A" or intended != DEFAULT_RENDER_MODE):
            item.setTextRenderMode(intended)
            requested.append(intended)
        item.textLine(text)
        page.drawText(item)
        if enclose:
            page.restoreState()
        previous = intended
        top -= LINE_SPACING

    page.showPage()
    page.save()
    return requested


def show_library_mechanism() -> None:
    """Part 1: the code that decides whether an operator is written."""
    from reportlab.pdfgen import canvas
    from reportlab.pdfgen.textobject import PDFTextObject

    print(_heading("PART 1 - THE DECISION IN THE LIBRARY"))

    method = PDFTextObject.setTextRenderMode
    name = f"{PDFTextObject.__module__}.{PDFTextObject.__qualname__}.{method.__name__}"
    try:
        source = inspect.getsource(method)
    except (OSError, TypeError) as exc:
        # Reading the installed source is the whole of this part. Guessing at what it says
        # would be worth less than stopping and naming what could not be read.
        raise RuntimeError(f"the source of {name} could not be read: {exc}") from exc

    print(f"\n{name}, as installed:\n")
    # Dedented from its place in the class so the longest line fits the output width.
    print(textwrap.dedent(source).rstrip())

    # A canvas needs somewhere to write; nothing is kept, so it writes to memory.
    fresh = canvas.Canvas(io.BytesIO()).beginText(LEFT_MARGIN, FIRST_LINE_TOP)
    initial = fresh._textRenderMode

    print(f"\n_textRenderMode in a text object straight from beginText: {initial}")
    print(
        f"that value is the mode a reset asks for ({DEFAULT_RENDER_MODE}), so the guard holds: "
        f"{initial == DEFAULT_RENDER_MODE}"
    )


def show_stream_operators(paths: dict[str, str], requested: dict[str, list[int]]) -> None:
    """Part 2: what each variant asked for, and what reached the page."""
    print(_heading("PART 2 - WHAT REACHES THE PAGE STREAM"))

    for variant, description in VARIANTS.items():
        operators = re.findall(rb"(\d+)\s+Tr", _page_stream(paths[variant]))
        written = ", ".join(match.decode() for match in operators)
        asked = ", ".join(str(mode) for mode in requested[variant])
        print(f"\nVariant {variant} - {description}")
        print(f"    setTextRenderMode asked for:  {asked}")
        print(f"    Tr operators in the stream:   {written or 'none'}")


def show_extracted_modes(paths: dict[str, str]) -> None:
    """Part 3: the mode each fragment ends up with, read back out of the file."""
    print(_heading("PART 3 - THE MODE EACH FRAGMENT ENDS UP WITH"))

    read = {variant: _read_fragment_modes(path) for variant, path in paths.items()}

    print()
    print(
        f"{'fragment':<{TEXT_COLUMN}}{'intended':<{MODE_COLUMN}}"
        f"{'variant A':<{MODE_COLUMN}}{'variant B'}"
    )
    print("-" * LINE_WIDTH)

    unpainted = {variant: 0 for variant in VARIANTS}
    for index, (text, intended) in enumerate(FRAGMENTS):
        actual = {}
        for variant, fragments in read.items():
            found, mode = fragments[index]
            if found != text:
                raise RuntimeError(f"variant {variant} reads {found!r} where {text!r} was written")
            actual[variant] = mode
            if intended == DEFAULT_RENDER_MODE and mode != DEFAULT_RENDER_MODE:
                unpainted[variant] += 1
        print(
            f"{text!r:<{TEXT_COLUMN}}{intended:<{MODE_COLUMN}}"
            f"{actual['A']:<{MODE_COLUMN}}{actual['B']}"
        )

    counts = ", ".join(f"{variant} {count}" for variant, count in unpainted.items())
    print(f"\nFragments meant to be painted that are not: {counts}")


def main() -> None:
    """Build both variants, print the three parts, and leave nothing behind."""
    check_dependencies()
    directory = tempfile.mkdtemp()
    try:
        paths = {variant: str(Path(directory) / f"{variant}.pdf") for variant in VARIANTS}
        requested = {variant: build_variant(path, variant) for variant, path in paths.items()}

        show_library_mechanism()
        show_stream_operators(paths, requested)
        show_extracted_modes(paths)

        # Without these the output cannot be checked against another run: part 1 prints the
        # source of whichever reportlab happens to be installed.
        print(_heading("ENVIRONMENT"))
        print()
        print(f"    {'python':<16} {'.'.join(str(part) for part in sys.version_info[:3])}")
        for distribution in ("reportlab", "pdfminer.six"):
            print(f"    {distribution:<16} {version(distribution)}")
    finally:
        shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    main()
