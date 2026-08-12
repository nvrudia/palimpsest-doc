# Reproduction

The scripts in this directory reproduce the observations described in the article, and are
written to be run by the reader rather than to be imported by anything.

## Requirements

The scripts need two libraries that the `palimpsest-doc` package does not depend on:

```bash
pip install pdfplumber reportlab
```

Neither takes part in the tool: `reportlab` writes the sample document a script examines, and
`pdfplumber` is the library whose behaviour a script reports on. They are installed to
demonstrate the observation, and installing them once is enough to check it.

Each script verifies that both are present before it does anything, and names what is missing
if they are not.

## Scripts

- `01_missing_field.py` — the text render mode is held in `PDFTextState` and is not passed to
  the character object built one call deeper, so it is absent from every character
  `pdfplumber` returns; the script shows where the field stops and what a detector built on
  those attributes can and cannot see as a result.

## Reproducibility

The output is read from the installed libraries rather than written into the scripts, so a
different version may print a different set of attribute names. Each run ends with an
`ENVIRONMENT` block naming the versions it ran under. The versions these scripts were
verified against:

- Python 3.14.5
- pdfplumber 0.11.10
- pdfminer.six 20260107
- reportlab 5.0.0
