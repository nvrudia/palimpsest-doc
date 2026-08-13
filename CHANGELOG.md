# Changelog

## [Unreleased]

### Added
- Project skeleton, CLI entry point, report data model.
- PDF text extraction with graphics state.
- Detector interface.
- Detectors: invisible render mode, sub-legible font size.
- JSON report serialisation.
- `palimpsest scan` command.
- Rendering layer over PDFium, through `pypdfium2`. It answers how many pixels a
  fragment painted, which is a question the text layer cannot answer about
  itself. PDFium shares no code with pdfminer, so the two are independent
  readings of one file: agreement between them is evidence, whereas a parser
  agreeing with itself is not. Pillow is not used; the raster is read from the
  bitmap's raw buffer, because `pypdfium2` has no dependencies of its own and
  Pillow would have entered as a runtime requirement disguised as a test one.
- Pixel verification of all eight text render modes. Modes 0, 1, 2, 4, 5 and 6
  paint; modes 3 and 7 paint nothing. This was measured, not read off the
  specification, and it is what the invisible-text detector now rests on.
- Detector: text whose fill colour matches the page background. Colours are
  compared as luminance, since `(1.0, 1.0, 1.0)` in DeviceRGB and `(1.0,)` in
  DeviceGray are the same white. DeviceGray, DeviceRGB and DeviceCMYK are
  supported and any other space is skipped rather than guessed at. The CMYK
  conversion is an approximation, so CMYK is held to a stricter threshold: the
  approximation was measured against PDFium at up to 0.058 away from the truth
  near white, which is wider than the 0.05 the exact spaces use, so only a
  coincidence that error cannot manufacture is reported.
- Detector: text lying wholly outside the displayed area of the page. Partial
  overlap is not reported -- text crossing the edge of a page is ordinary, and a
  detector firing on it would bury the case it exists for.
- The page background is measured by rendering rather than assumed to be white,
  sampled from a frame along the edge of the page. The most frequent colour of a
  whole page is the colour of whatever covers most of it, which on a scan
  carrying one large image is the image.
- Fixture self-verification now counts pixels as well as reading the text layer.
  The earlier check read the file through the same extraction layer the tests
  exercise, so a misreading shared by both would have satisfied it.

### Changed
- Text is extracted with `pdfminer.six` directly instead of `pdfplumber`. The
  text render mode is not reachable through `pdfplumber` at any layer: it is
  held in `PDFTextState`, which `pdfminer` never attaches to the character
  objects `pdfplumber` is built on, so neither the character attributes nor the
  underlying `LTChar` carry it. Without the render mode the invisible-text
  detector cannot exist. Driving `pdfminer` directly makes the mode available at
  the point where it passes through, in the same pass that yields the
  characters.

- The detector list is built once per scan instead of held as a module
  constant, because two detectors measure the rendered page and need the
  document to do it. The order is written out in one place and no branch adds to
  it: findings are evidence, and evidence that reorders itself between runs on
  one unchanged file cannot be cited.

### Removed
- `pikepdf` dependency. No module imports it: the extraction layer reads the
  text render mode from pdfminer directly. It returns in step 3, when
  low-level access to document objects is actually needed.

### Known limitations
- Documents containing a page with a `/Rotate` entry are refused, and the scan
  stops with an error rather than reporting the pages it could read. A report
  showing no findings, produced while half the checks silently did not run, is
  the outcome this tool exists to prevent.

  The two readings themselves agree on rotation: measured at 0, 90, 180 and 270
  degrees, pdfminer reports glyph coordinates in the rotated display space, and
  the mapping in `render.py` lands on the painted ink every time. Two things do
  not follow. `visible_area` takes the page size from PDFium's `get_bbox`, which
  ignores `/Rotate` while the rasteriser does not, so the two disagree over which
  dimension is which; and grouping glyphs into runs compares baselines and
  horizontal gaps, so a rotated line of text arrives as one run per character and
  findings would quote single letters.

  Lifting the restriction is therefore work in the extraction layer, not in the
  renderer. Documents scanned in landscape do carry this entry, so it has to be
  lifted.
