# Legal significance of ingestion divergences

Authors: Oleksii Tsarapkin (legal analysis), Mykola Rudia (editing)

This document records which divergences between the visible and the
extracted content of a contract carry legal consequences, how a finding
should be reported so that it can be relied upon, and which classes of
document require special handling. The legal analysis is Oleksii
Tsarapkin's, drawn from contract practice; the final section, marked as
editorial, records how the analysis maps onto the tool.

## 1. Where a divergence costs the most

Three areas of a contract.

**Liability.** The limit of liability, exceptions to the limit, penalties
and damages. A hidden exception can in effect remove a limitation the
parties agreed. This surfaces only when a claim is made.

**The principal obligation and money.** Subject matter, scope, price,
currency, time limits and payment terms. A single omitted "not" or a
changed number can change the outcome of the transaction.

**Dispute resolution.** Governing law, court or arbitration. Costs, the
ability to protect a right and the enforceability of a decision depend on
it.

If only three findings out of twenty can be shown, show those that change
liability, an obligation, or the means of protection. Priority is set by
content, not by the mechanism of concealment.

## 2. What does not matter

Line breaks, technical spaces, font, text position, page numbering — so
long as they change neither meaning nor legibility.

Two qualifications:

- **Headers and footers must not be excluded automatically.** They can
  carry a date, a version number or a reservation.
- **White text must be read before it is classified.** Only after reading
  it can one decide whether it is a template remnant.

In Word documents the main text, deleted text in tracked changes,
comments and field codes must be kept apart. A lawyer's comment or a
rejected revision must not appear in a conclusion as an operative term of
the contract.

A tool that keeps reporting trivia without explaining its significance
stops being read carefully.

## 3. How a finding must be reported

A finding must be a verifiable fact: the specific file, version, page or
clause, a verbatim quotation, and the method of detection. It is followed
by an explanation of which contractual provision the divergence affects.

Example of a finding:

> In the contract file, in the section on liability, the text "Limitation
> of liability does not apply" was found; it is not displayed in ordinary
> viewing of the page. It contradicts the visible provision limiting
> liability.

Example of the corresponding message to a counterparty:

> When checking the file you sent, a divergence was found in the
> provision on liability; please confirm the agreed text and provide a
> corrected version.

**Record the divergence, not the intent.** A conclusion that a
substitution was deliberate requires separate evidence. Which term is
legally operative is decided with regard to what was agreed and signed.

## 4. Documents that will break a tool

**Word files with unaccepted tracked changes.** The No Markup view shows
the text with changes applied, but the revisions remain in the file. A
tool must distinguish main, inserted and deleted text.

**Contracts with annexes and supplementary agreements.** Subject, price
and time limits can sit in a specification held in a separate file. A
supplementary agreement can amend the main contract. One file does not
give the full picture.

**Bilingual contracts.** Both language versions must be checked, together
with the clause stating which language prevails.

**Scans and PDFs with recognised text.** A recognition error in a digit,
a negation or a table row can look like a substitution. Verification
against the image is required.

**Complex tables, text boxes, footnotes, headers and footers, automatic
cross-references and formulas.**

**A tool must state explicitly what it checked and what remained outside
the check.**

## 5. Practice: how agreed and signed versions are compared

The practical method is to compare the last agreed version, with all
agreed changes accepted, against the version signed by the counterparty.
For Word files this is done with the Compare function. A scan must also
be checked against the image, since the recognised text can contain
errors.

It is advisable to sign the final agreed version first and keep one's own
copy for later comparison. For paper documents: a seal impression across
the edges of fanned-out sheets, or binding of numbered sheets with the
binding point and the sheet count certified. When a document comes back,
its content and completeness are checked.

## 6. What is worth checking before signing

Beyond the current scope of the tool:

- correspondence to the agreed version;
- completeness of the document set: are all documents present, are
  cross-references correct;
- consistency: do sums, time limits, definitions and payment terms match
  across the different parts of the set; were changes made after
  agreement;
- authority of the signatories;
- in Word: unaccepted revisions, comments, hidden text and fields.

Word's Document Inspector helps, but does not cover all methods of
concealment — in particular white text on a white background and objects
covered by other objects.

The original must be preserved. Checking and cleaning are carried out on a
copy, so that information about how changes were agreed is not lost.

A useful result from a tool is the exact location of the divergence, a
quotation, its possible effect on obligations, and the limits of the
check. This gives a lawyer grounds to determine what needs to be
clarified before signing.

## 7. Implications for Palimpsest-doc (editorial)

This section is the maintainer's reading of the analysis above, not part
of it.

| Analysis | Consequence for the tool | Status |
|---|---|---|
| §4: state what was checked and what was not | every report carries a coverage statement | implemented with this change |
| §3: record the divergence, not the intent | finding explanations describe what is in the file, never why | already the rule; to be audited |
| §1: priority is set by content | severity raised by location in liability, principal obligation or dispute-resolution provisions | funded milestone: severity model |
| §2: headers, footers and white text are not excluded automatically | no detector suppresses findings by page region | already the case; kept as a rule |
| §2, §4: tracked changes, comments, field codes | DOCX layer separates main, inserted and deleted text, comments and fields | funded milestone: DOCX layer |
| §4: annexes, supplementary agreements, bilingual sets | document-set analysis | outside the current proposal |
| §4: OCR errors resemble substitution | recognised text is never treated as a finding without comparison to the image | design constraint |
| §6: objects covered by other objects | candidate detector | funded milestone: remaining PDF detectors |
| §6: consistency of sums, terms and definitions across a set | quantitative consistency | separate project |
