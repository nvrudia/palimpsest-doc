# Palimpsest-doc

> A palimpsest is a manuscript page from which the text has been erased
> and overwritten — yet the older text still shows through.

Detect divergence between what a human reads in a document and what an
automated pipeline actually ingests.

## The problem

Documents arriving from outside — contracts, tender submissions, filings —
are increasingly processed by automated pipelines. Content hidden inside the
file itself never reaches the person who reads it, but reaches the machine
that processes it: invisible rendering modes, zero-size glyphs, remapped
font tables, disabled layers, metadata, hidden DOCX fragments.

Existing defences operate on the text level, after it has already entered
the pipeline. Palimpsest-doc works one layer earlier — at ingestion.

## The approach

Not a probability score, but a fact: a document has a visual representation
and a textual one. A human reads the first; a machine receives the second.
Where they diverge, that divergence can be located, quoted and reproduced.

The threat model assumes the document was authored by an interested party —
a counterparty, an applicant, a bidder — not by an anonymous attacker.

## Status

Pre-alpha. Not usable yet.

## License

EUPL-1.2
