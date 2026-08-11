# Changelog

## [Unreleased]

### Added
- Project skeleton, CLI entry point, report data model.
- PDF text extraction with graphics state.
- Detector interface.
- Detectors: invisible render mode, sub-legible font size.
- JSON report serialisation.
- `palimpsest scan` command.

### Changed
- Text is extracted with `pdfminer.six` directly instead of `pdfplumber`. The
  text render mode is not reachable through `pdfplumber` at any layer: it is
  held in `PDFTextState`, which `pdfminer` never attaches to the character
  objects `pdfplumber` is built on, so neither the character attributes nor the
  underlying `LTChar` carry it. Without the render mode the invisible-text
  detector cannot exist. Driving `pdfminer` directly makes the mode available at
  the point where it passes through, in the same pass that yields the
  characters.

### Removed
- `pikepdf` dependency. No module imports it: the extraction layer reads the
  text render mode from pdfminer directly. It returns in step 3, when
  low-level access to document objects is actually needed.
