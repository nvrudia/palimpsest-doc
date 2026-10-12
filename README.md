# Palimpsest-doc

> A palimpsest is a manuscript page from which the text has been erased
> and overwritten — yet the older text still shows through.

Detect divergence between what a human reads in a document and what an
automated pipeline actually ingests.

## The problem

Documents arriving from outside — contracts, tender submissions, filings —
are increasingly processed by automated pipelines. Content present in the
file may never reach the person who reads it while reaching the machine that
processes it: invisible rendering modes, sub-legible type, text the colour of
the page, text positioned outside the visible area, remapped font tables,
hidden DOCX fragments.

Existing defences operate on the text level, after it has already entered the
pipeline. Palimpsest-doc works one layer earlier — at ingestion.

## The approach

Not a probability score, but a fact. A document has a visual representation
and a textual one. A human reads the first; a machine receives the second.
Where they diverge, the divergence is located, quoted and reproduced.

Claims about visibility are measured rather than assumed. The tool reads each
document twice through unrelated implementations — parsing with
`pdfminer.six` and rasterising with PDFium — and a finding must hold under
both.

**Two threat models, not one.** The first is a document authored by an
interested party: a counterparty, an applicant, a bidder. The second has no
author at all. A generation library that compares a requested value against
its own record rather than the state of the file will leak state between
fragments; a font that cannot encode a character will substitute one that
can. Both produce a document a human and a machine read differently, and
neither requires an adversary. A defence that looks for the signatures of
intent does not see the second case.

## Status

Working, pre-release. The command line interface is stable enough to use; the
API is not, and will change.

Four detectors, 58 tests, CI on Python 3.11 and 3.14. Not yet on PyPI.

## Usage

```
palimpsest scan document.pdf
palimpsest scan document.pdf --json
```

Exit codes follow the convention used by code analysers, so the tool can be
placed in a pipeline without parsing its output:

| code | meaning |
|---|---|
| 0 | document read, no findings |
| 1 | document read, findings present |
| 2 | document could not be read or analysed |

The readable output carries the SHA-256 of the file, the time of the scan and
the tool version, so that a finding is bound to a specific document. `--json`
emits the report and nothing else.

## Detectors

| name | what it reports |
|---|---|
| `invisible_render_mode` | text drawn in a mode that paints nothing on the page |
| `text_color_matches_background` | text whose colour does not differ from the page background |
| `text_outside_page_area` | text positioned entirely outside the visible area |
| `sub_legible_font_size` | text below the size at which type is legible |

Each finding carries the detector, a severity, the location, the evidence
quoted verbatim from the document, and an explanation of what was observed.
Explanations describe what is in the file, not what anyone intended by it.

## What it does not do

- DOCX. Only PDF for now.
- OCR, and therefore scanned documents.
- Rotated pages (`/Rotate`) are refused rather than analysed. The page size
  used for geometry does not account for rotation, and run grouping assumes
  horizontal text.
- Text visible on the page but missing from the extraction. This direction of
  divergence is mostly recognition noise; the reverse is the signal.

## Reproducing the observations

`reproduction/` holds three self-contained scripts demonstrating failures
found while building the tool: a field that does not cross a boundary between
two layers of a parsing library, a call that reports success and emits
nothing, and characters silently redistributed across fallback fonts. They
require dependencies the package itself does not use; see
`reproduction/README.md`.

## Use of generative AI

This project was built with the assistance of a large language model, and
that assistance is disclosed here rather than left to be inferred.

**What the model did.** Code was written through Claude Code against written
specifications, one file at a time, with each file reviewed before the next
was started. The model also drafted documentation and the accompanying
paper.

**What it did not do.** Design decisions, thresholds, scope and dependency
choices were made by the maintainer. Several of the model's proposals were
tested and rejected: an approach built on `pdfplumber` was abandoned after
reconnaissance showed the text rendering mode is unreachable through it; a
suggested fixture reset was shown by measurement to emit nothing; a proposed
threshold direction was corrected after being argued to be backwards. Where
the model asserted a mechanism, the assertion was measured before it was
relied upon.

**How it is recorded.** Commits carry a `Co-Authored-By` trailer where the
model participated. Contributions originating from a specific person's
expertise carry `Suggested-by`.

**Why it is stated at all.** The subject of this tool is output that looks
correct and is not, so a claim about how the tool itself was produced should
be checkable. The commit history shows the sequence.

## Contributing

Issues describing a document class the tool handles badly are the most useful
contribution, particularly with the reasoning for why the divergence matters.
Do not attach real documents: describe the case and the generator will build
a synthetic equivalent.

See `CONTRIBUTORS` for who has worked on this.

## Paper

*Silent Degradation in Document Processing Pipelines: Two Independent Case
Studies* describes a class of failure that produces plausible output, passes
verification, and is detectable only against the source, with instances from
two unrelated systems. Preprint: https://doi.org/10.5281/zenodo.23310803

## License

EUPL-1.2
