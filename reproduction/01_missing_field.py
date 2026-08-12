"""Show that the text render mode is absent from every character pdfplumber returns.

The mode is held in PDFTextState. pdfminer hands that object to render_string, and the
character object is built one call deeper, in render_char, out of a different set of
arguments: the matrix, the font, the size, the colour space and PDFGraphicState. PDFTextState
is not among them, so the field stops at the boundary between those two calls. This is a
property of how state is passed between the layers rather than of any one library: pdfplumber
reports the character objects it is handed, and they were built without the mode.

A detector reading the attributes of a pdfplumber character therefore has no field that tells
a painted fragment from an unpainted one. Part 3 puts such a detector beside one that reads
the mode where it is held, on the same file.

Run it with: python reproduction/01_missing_field.py
"""

import importlib.util
import inspect
import re
import shutil
import sys
import tempfile
import textwrap
from importlib.metadata import version
from pathlib import Path
from typing import Any

# Every third-party import in this file sits inside the function that uses it. The script has
# to be able to report a missing library as a sentence rather than as a traceback, and an
# import at module level would run before check_dependencies could say anything.

LINE_WIDTH = 78

REQUIRED_MODULES = ("pdfplumber", "reportlab")

PAGE_SIZE = (612.0, 792.0)
# One of the standard 14 fonts, present in every reader, and its WinAnsi encoding covers the
# Latin text below exactly. It must not be given anything outside that range: characters it
# cannot encode are substituted rather than refused.
FONT_NAME = "Helvetica"
FONT_SIZE = 12.0
HIDDEN_RENDER_MODE = 3

VISIBLE_FIRST = "VISIBLE PARAGRAPH"
HIDDEN_MARKER = "HIDDEN INSTRUCTION MARKER"
VISIBLE_SECOND = "SECOND VISIBLE PARAGRAPH"

# The attributes that could conceivably separate the two fragments: the font, its size, the
# fill colour together with the space that colour is expressed in, and the placement.
COMPARED_ATTRIBUTES = (
    "fontname",
    "size",
    "height",
    "non_stroking_color",
    "ncs",
    "upright",
    "matrix",
)

# White in the three colour spaces a simple document uses. A colour test is the closest a
# character attribute gets to the question of whether a fragment shows on the page.
WHITE_FILLS = ((1,), (1, 1, 1), (0, 0, 0, 0))

NAME_COLUMN = 20
VALUE_COLUMN = 28


def _heading(title: str) -> str:
    """A section title framed in dashes."""
    rule = "-" * LINE_WIDTH
    return f"\n{rule}\n{title}\n{rule}"


def _wrap(text: str) -> list[str]:
    """Break a comma-separated list to the indented width."""
    return textwrap.wrap(text, LINE_WIDTH - 4)


def _format(value: Any) -> str:
    """Render a value for the tables below, without the trailing zeros of a float."""
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, tuple):
        inner = ", ".join(_format(item) for item in value)
        return f"({inner},)" if len(value) == 1 else f"({inner})"
    return repr(value)


def _annotation(parameter: inspect.Parameter) -> str:
    """The annotation of a parameter, with module paths stripped for width."""
    annotation = parameter.annotation
    if annotation is inspect.Parameter.empty:
        return ""
    if isinstance(annotation, type):
        return annotation.__name__
    text = annotation if isinstance(annotation, str) else str(annotation)
    return re.sub(r"[A-Za-z_][\w.]*\.", "", text)


def _carried_states(function: Any, states: tuple[type, ...]) -> list[tuple[str, str]]:
    """Which of pdfminer's state objects a function takes, and under which parameter name.

    Annotations are matched by name, not by identity: a module that imports a state class for
    typing alone leaves its annotation as an unevaluated string, and nothing resolvable from
    here turns that string back into the class.
    """
    wanted = {state.__name__ for state in states}
    carried = []
    for name, parameter in inspect.signature(function).parameters.items():
        annotation = parameter.annotation
        text = annotation if isinstance(annotation, str) else getattr(annotation, "__name__", "")
        if text in wanted:
            carried.append((name, text))
    return carried


def _state_attributes(state: type) -> list[str]:
    """The attribute names of a pdfminer state class, however that version declares them.

    Read from the class rather than written out here. A list typed into this file would go on
    printing the shape of the version it was typed against, long after that stopped being the
    shape of the installed one.
    """
    slots = getattr(state, "__slots__", None)
    if slots:
        return sorted(slots)
    declared = vars(state())
    if declared:
        return sorted(declared)
    return sorted(getattr(state, "__annotations__", {}))


def check_dependencies() -> None:
    """Confirm the demonstration libraries are importable, or say which one is not."""
    # find_spec answers the question without executing the module, so a library that is
    # present but raises on import is reported by the import itself, where it belongs.
    missing = [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]
    if not missing:
        return
    print("This script needs libraries that the palimpsest-doc package does not depend on.")
    print(f"Not importable: {', '.join(missing)}")
    print()
    print("Install with:")
    print(f"    pip install {' '.join(missing)}")
    sys.exit(1)


def build_sample(path: str) -> None:
    """Write a page holding two painted fragments and one drawn in render mode 3."""
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdftypes import resolve1
    from reportlab.pdfgen import canvas

    page = canvas.Canvas(path, pagesize=PAGE_SIZE)

    text = page.beginText(72, 720)
    text.setFont(FONT_NAME, FONT_SIZE)
    text.textLine(VISIBLE_FIRST)
    page.drawText(text)

    # The render mode belongs to the graphics state and survives BT/ET, so the fragment that
    # sets it is enclosed in q/Q; without that, the fragment after it would inherit mode 3 as
    # well. setTextRenderMode(0) is not used to undo it: reportlab compares the request
    # against a counter that a fresh beginText initialises to 0, so the request matches, no Tr
    # operator is written, and the mode left in the file is the previous one.
    page.saveState()
    text = page.beginText(72, 700)
    text.setFont(FONT_NAME, FONT_SIZE)
    text.setTextRenderMode(HIDDEN_RENDER_MODE)
    text.textLine(HIDDEN_MARKER)
    page.drawText(text)
    page.restoreState()

    text = page.beginText(72, 680)
    text.setFont(FONT_NAME, FONT_SIZE)
    text.textLine(VISIBLE_SECOND)
    page.drawText(text)

    page.showPage()
    page.save()

    # A script whose whole subject is an unpainted fragment may not quietly produce a file
    # without one. The content stream is the only place that settles whether the operator was
    # written, so it is read back and searched for it.
    operator = f"{HIDDEN_RENDER_MODE} Tr".encode()
    with open(path, "rb") as handle:
        stream = b"".join(
            resolve1(content).get_data()
            for sheet in PDFPage.get_pages(handle)
            for content in sheet.contents
        )
    if operator not in stream:
        raise RuntimeError(
            f"the sample was written without a {operator.decode()!r} operator, so it carries no "
            "unpainted text and demonstrates nothing"
        )


def show_character_attributes(path: str) -> None:
    """Part 1: the whole of what a pdfplumber character object carries."""
    import pdfplumber

    print(_heading("PART 1 - THE ATTRIBUTES OF A CHARACTER OBJECT"))
    with pdfplumber.open(path) as document:
        characters = document.pages[0].chars
        # Characters arrive in content stream order, so the marker can be located by index in
        # the concatenated text and the same index used to pick the character out.
        text = "".join(character["text"] for character in characters)
        visible = characters[0]
        hidden = characters[text.index(HIDDEN_MARKER)]

        print(f"\nEvery key of a character object, {len(visible)} of them:")
        for line in _wrap(", ".join(sorted(visible))):
            print(f"    {line}")

        print("\nThe first character of a painted fragment beside the first of the unpainted:")
        print()
        header = (
            f"{'attribute':<{NAME_COLUMN}} "
            f"{'painted ' + repr(visible['text']):<{VALUE_COLUMN}} "
            f"{'unpainted ' + repr(hidden['text'])}"
        )
        print(header)
        print("-" * LINE_WIDTH)
        for name in COMPARED_ATTRIBUTES:
            print(
                f"{name:<{NAME_COLUMN}} "
                f"{_format(visible.get(name)):<{VALUE_COLUMN}} "
                f"{_format(hidden.get(name))}"
            )

        differing = [name for name in COMPARED_ATTRIBUTES if visible.get(name) != hidden.get(name)]
        naming_mode = sorted(key for key in visible if "render" in key or "mode" in key)

    print(f"\nOf those, the ones that differ: {', '.join(differing) or 'none'}")
    print(f"Keys naming a render mode: {', '.join(naming_mode) or 'none'}")


def show_layer_signatures() -> None:
    """Part 2: the call chain, and the point at which the mode stops travelling."""
    from pdfminer.converter import PDFLayoutAnalyzer
    from pdfminer.layout import LTChar
    from pdfminer.pdfdevice import PDFTextDevice
    from pdfminer.pdfinterp import PDFGraphicState, PDFTextState

    print(_heading("PART 2 - WHERE THE FIELD STOPS"))

    states = (PDFTextState, PDFGraphicState)
    chain = (
        ("PDFTextDevice.render_string", PDFTextDevice.render_string),
        ("PDFLayoutAnalyzer.render_char", PDFLayoutAnalyzer.render_char),
        ("LTChar.__init__", LTChar.__init__),
    )

    for label, function in chain:
        print(f"\n{label}")
        for name, parameter in inspect.signature(function).parameters.items():
            if name == "self":
                continue
            print(f"    {name:<14} {_annotation(parameter)}")

    print("\nThe state objects each of them is handed:")
    for label, function in chain:
        carried = [f"{name}: {kind}" for name, kind in _carried_states(function, states)]
        for index, entry in enumerate(carried or ["none"]):
            print(f"    {label if index == 0 else '':<33}{entry}")

    text_state = _state_attributes(PDFTextState)
    graphics_state = _state_attributes(PDFGraphicState)

    print("\nPDFGraphicState, the state object LTChar is built with:")
    for line in _wrap(", ".join(graphics_state)):
        print(f"    {line}")
    print("\nPDFTextState, which the character is not built with:")
    for line in _wrap(", ".join(text_state)):
        print(f"    {line}")

    print(f"\n'render' among the attributes of PDFTextState:     {'render' in text_state}")
    print(f"'render' among the attributes of PDFGraphicState: {'render' in graphics_state}")
    print("\nrender_string is the last call that holds both states. render_char and")
    print("LTChar are given PDFGraphicState alone, and it has no member for the mode,")
    print("so the character is assembled from everything about its appearance except")
    print("whether it is painted.")


def detect_via_pdfplumber(path: str) -> list[str]:
    """Look for unpainted text using only what a character object carries.

    With no field for the mode, the fill colour is the one attribute bearing on whether a
    fragment reaches the page, so the test asks whether that colour is white.
    """
    import pdfplumber

    fragments = []
    with pdfplumber.open(path) as document:
        for page in document.pages:
            found = [
                character["text"]
                for character in page.chars
                if tuple(character["non_stroking_color"] or ()) in WHITE_FILLS
            ]
            if found:
                fragments.append("".join(found))
    return fragments


def detect_via_pdfminer(path: str) -> list[str]:
    """Look for unpainted text by reading the mode where it is held, in PDFTextState."""
    from pdfminer.converter import PDFLayoutAnalyzer
    from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
    from pdfminer.pdfpage import PDFPage

    class ModeReader(PDFLayoutAnalyzer):
        """Keeps the fragments whose text state carried mode 3.

        render_string is given the mode; render_char is given the character. The chain
        between them is synchronous, so the mode noted by the first is the mode of every
        character seen by the second until the next call.
        """

        def __init__(self, resources: PDFResourceManager) -> None:
            super().__init__(resources, pageno=1, laparams=None)
            self.fragments: list[str] = []
            self._mode = 0
            self._current: list[str] = []

        def render_string(self, textstate, seq, ncs, graphicstate) -> None:
            self._mode = textstate.render
            self._current = []
            super().render_string(textstate, seq, ncs, graphicstate)
            if self._mode == HIDDEN_RENDER_MODE and self._current:
                self.fragments.append("".join(self._current))

        def render_char(
            self, matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate
        ) -> float:
            if self._mode == HIDDEN_RENDER_MODE:
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


def show_detector_consequence(path: str) -> None:
    """Part 3: the same file put to a detector on each side of the boundary."""
    print(_heading("PART 3 - WHAT EACH DETECTOR REPORTS"))

    by_attributes = detect_via_pdfplumber(path)
    by_render_mode = detect_via_pdfminer(path)

    print("\ndetect_via_pdfplumber, over the attributes of each character:")
    print(f"    {', '.join(repr(item) for item in by_attributes) or 'nothing reported'}")
    print("\ndetect_via_pdfminer, over textstate.render:")
    print(f"    {', '.join(repr(item) for item in by_render_mode) or 'nothing reported'}")

    unreported = [item for item in by_render_mode if item not in by_attributes]
    print("\nIn the file, painted by nothing, and reported only by the second:")
    for item in unreported:
        print(f"    {item!r}")
    if not unreported:
        print("    none")


def main() -> None:
    """Build the sample, print the three parts, and leave nothing behind."""
    check_dependencies()
    directory = tempfile.mkdtemp()
    try:
        path = str(Path(directory) / "sample.pdf")
        build_sample(path)
        show_character_attributes(path)
        show_layer_signatures()
        show_detector_consequence(path)

        # Without these the output cannot be checked against another run: the attribute names
        # in parts 1 and 2 are read from whatever versions happen to be installed.
        print(_heading("ENVIRONMENT"))
        print()
        print(f"    {'python':<16} {'.'.join(str(part) for part in sys.version_info[:3])}")
        for distribution in ("pdfplumber", "pdfminer.six", "reportlab"):
            print(f"    {distribution:<16} {version(distribution)}")
    finally:
        shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    main()
