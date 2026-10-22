# Architecture

The library is a flat, document-local pipeline for Italian legal decisions. Its main
design choice is to separate evidence collection from output policy: detectors propose
spans, policy resolves every proposal together, and the text is rewritten once.

```mermaid
flowchart LR
    A["Raw legal text"] --> B["Normalize"]
    B --> C["Detect evidence"]
    C --> D["Resolve person identities and aliases"]
    D --> E["Apply late policy and span priorities"]
    E --> F["Allocate document-local tags"]
    F --> G["Render once"]
    G --> H["Review-only residual checks"]
    H --> I["Output + Report"]
```

## Design constraints

1. **Recall is the privacy objective.** An identity counts as removed only when every
   annotated occurrence and alias is gone. A document fails when one identity remains.
2. **One legal pipeline.** General legal cues and layouts are shared across courts;
   archive names never route to separate implementations.
3. **Policy is late and span-local.** Judicial evidence cannot globally veto a surname.
4. **One rewrite.** All offsets are resolved against a stable normalized input before
   rendering, avoiding cascading substitutions and offset drift.
5. **Simple extension points.** The first-name list and optional NER only add person
   seeds; both use the same identity, policy and rendering stages as legal-context
   detectors.
6. **Verification does not mutate.** Residual checks only produce review evidence.

## Pipeline stages

### 1. Normalize

`text.py` applies NFKC normalization, removes zero-width characters, normalizes quotes,
decodes entities, repairs line-wrap hyphenation, strips HTML tags and flattens light
Markdown when `sanitize=True`. Only real tag names are stripped, each tag on one line
and never right after another `<`: the `<<…>>` many judges type as quotation marks is
text, and a generic `<letters…>` pattern used to delete it — together with everything
up to the next `>`, paragraphs away. Detection and replacement offsets refer to this
normalized text, not necessarily the raw input bytes.

### 2. Detect evidence

The runtime has a small set of complementary detectors:

- `patterns.py`: structured PII, legal roles, person cues, party blocks, addresses and
  organization/legal-form patterns;
- `protect.py`: exact judicial-role and procedural-number evidence;
- `seeds.py`: private-person seeds from legal context and the weak first-name list;
- `ner.py`: optional transformer person mentions.

None of these modules edits text or decides that an identity is globally safe. Private
companies are detected even when the default policy later declines to redact them.

### 3. Resolve document-local people

`SeedSet` merges order-insensitive full identities and their observed variants. Once a
person is established, `variant_patterns` proposes:

- exact and case-insensitive full spellings;
- common surname-first/given-name-first rotations;
- bare tokens only when they are long and absent from the legal common-word list.

Strong private-role cues may seed an exact all-common name such as `Antonio De Luca`,
but it contributes no unsafe bare-token propagation. When a token belongs to more than
one detected person, the token is still redacted under a neutral identity instead of
being assigned arbitrarily.

The bundled first-name list covers names registered in Italy and is intentionally used
as weak evidence. One linear token scan proposes only adjacent full names: ordinary
`Given Surname`, or the ALL-CAPS `SURNAME GIVEN` form used in headings. Across a line
break the two tokens must share a case style and the next line must read as the rest of
the name, and a name inside a street, a saint's or a town's (`Viale Pietro
Pietramellara`, `San Giorgio`, `Vittorio Veneto`) is refused. A listed first name alone
is a seed only after a salutation or a kinship cue (`Caro Paolo,`, `il figlio minore
Tommaso`), and folds into the one full name it belongs to. A common first name of a
detected person (`Paolo` of `Paolo Gennari`) is then proposed case-sensitively, only when
one detected person owns it, never after a street word or a saint and never next to
another name token. Legal common words, public institutions and company suffixes remain
guards, and the resulting identity follows the normal alias and late-policy path. The JSON resource is loaded once on first use; `Config(first_names=False)` turns
the scan off.

Party blocks are read as lists. After an applicant cue (`proposto da`, `ricorso di`) or
a counter-party cue (`nei confronti di`, or `nei confronti` or `contro` ending its line,
as the administrative and civil headings print them) every name of a list separated by
commas, semicolons or `e` is seeded, not only the first: a mass appeal lists dozens of
applicants after one cue. The list ends at the first item that is not name-shaped, and
institutions inside it are left to the public-body guards. A name followed by
`rappresentato e difeso` is a party as well. Companies and public bodies stand in the
same places, so a hit from these cues is refused when the text continues it into an
organisation: a legal form after it (`… S.r.l.`), or a capitalised word and a
preposition before it (`Comune di …`).

Court text wraps names, so a few anchors read a name across a line break (counsel,
`difeso da`, the codice fiscale's neighbour, the signature block, NER mentions). Past the
break the capture keeps the next line only if it reads as the rest of the name: no
common word unless a listed first name, no heading or role word, no field label after
it. Otherwise `Giudice: avv. Biagio Stomeo⏎Segretario: …` became one person and the
rewrite deleted the label and the break. Lists of counsel or parties may wrap but end at
a blank line, and a phone number stays on its line.

### 4. Apply policy and resolve overlaps

`policy.py` filters candidates using `Config`, then greedily accepts non-overlapping
spans by evidence priority and length:

For companies, `False` rejects every company candidate, `"person_named"` accepts only
the conservative family-marker and two-surname subset, and `True` accepts every
detected private company. Public-institution guards apply before these choices.

| Priority | Evidence |
|---:|---|
| 120 | structured personal data |
| 100 | exact judicial-role and procedural-number keeps |
| 40 | cued or letterhead address, birthplace or residence town |
| 35 | private company |
| 30 | full person identity |
| 20 | distinctive or ambiguous person token |

Structured PII deliberately outranks kept case identifiers, so a birth date such as
`12/03/1974` cannot survive because a substring resembles a case number.

For company candidates, `companies=False` keeps every company,
`companies="person_named"` accepts only candidates with a conservative family-name
signal, and `companies=True` accepts them all. Accepted company spans outrank person
aliases so a surname shared with a partner or shareholder does not leave part of the
company name visible.

Judicial protection applies only to the explicit role span. For example:

```text
Presidente: ROSSI MARIO       -> kept
ROSSI LUCIA, ricorrente       -> redacted
La Rossi insiste              -> redacted
```

If one complete identity has both judicial and strong private-role evidence, the
privacy-first conflict rule removes its occurrences and emits a warning. A broad party
window alone is not strong enough to revoke an explicit judicial role, because legal
headers can contain prosecutors inside that window.

A courtesy title is not a private role. A name whose only evidence is a title
(`il dott. X`) is left alone when the same name holds an explicit judicial role in the
document, and `avv.` after a judicial rank (`il consigliere avv. X`) is a title, not a
counsel cue: older TAR decisions introduce the reporting judge that way, and the title
used to turn the bench into parties. A title on a name with no judicial role still
marks a person.

`keep_judges=False` and `keep_case_numbers=False` remove their keep decisions; they do
not add special redactors. Public institutions are rejected as person/company
candidates. A place is proposed only in a biographic slot ("nato a Stia", "residente a
Pratovecchio") and only if ISTAT lists it as a comune, current or suppressed, or, for a
birthplace, when its country follows in brackets (`nato a Wenzhou (Repubblica Popolare
Cinese)`); a court seat or any other mention of a town is never a candidate.

An address is proposed after a personal cue (residence, domicile, `con studio in`, a
property `sito in`) or as the address line of a letterhead, a signature or an addressee
block. A block that names a public body or a company is theirs and stays, as do a
registered office (`con sede in`), the Avvocatura's domicile, a statutory domicile at the
court, and a property cue right after a public body. A public office's mailbox (an
address on a public administration's domain with no first name in it, such as
`dp.treviso@pce.agenziaentrate.it`) is not personal data and is not proposed either.

### 5. Allocate tags and render once

Only accepted redactions receive tags from `labels.Registry`. The registry is local to
one call and deduplicates values case-insensitively. Accepted decisions are already
non-overlapping and ordered, so `_render` joins untouched slices and replacements in a
single pass.

This ordering also means `Report.mapping` contains only values that actually received
an output tag; overlap-suppressed proposals never allocate one.

### 6. Verify without rewriting

`verification.py` scans returned output for:

- structured identifiers;
- strong private-role cues;
- known aliases selected for redaction;
- broad 2–4-token capitalized name candidates;
- role conflicts;
- long documents with no detections.

Only a person finding wholly contained in an accepted public-role span is exempt.
Structured PII is never suppressed merely because it overlaps a kept span.

The scan is deliberately broad: on the current evaluation it finds every annotated
leaking document but produces many false review alarms. `passed_checks` consequently
means “no bundled heuristic fired,” not “anonymous” or “safe to publish.” Running a
second transformer pass would add cost without independent evidence, so verification
does not do that.

## Shared data and report contract

`model.py` holds immutable or small shared records:

- `Mention`: one detector observation;
- `Entity`: one document-local person and its variants/sources;
- `Candidate`: a proposed span before policy;
- `Decision`: an accepted keep/redact action;
- `EntityRecord`: compact grouped audit data;
- `ResidualFinding` and `Verification`: output-review evidence.

The public call remains:

```python
output, report = anonymize(text, config=None, **overrides)
```

The first five `Report` fields retain positional compatibility:
`mapping`, `protected`, `replacements`, `replacement_spans`, `risk`. New audit fields
are additive and recursively JSON serializable.

Coordinate spaces are explicit:

- `replacement_spans`, `decisions`: `normalized_input`;
- `residuals`: `output`.

An offset map back to raw pre-normalization text is intentionally not implemented; it
would add substantial complexity. Set `sanitize=False` only when byte-stable input
coordinates matter more than normalization recall.

## Batch safety

`batch.py` uses independent worker processes because no identity state crosses document
boundaries. It rejects overlapping source/destination trees and in-place file writes,
decodes UTF-8 strictly, and returns errors per file.

Output and sidecar writes use same-directory temporary files followed by atomic
replacement. Symbolic links in destination paths are rejected, as are overlapping
source/output trees and in-place writes.

Resume is opt-in. Optional mapping sidecars include source and output SHA-256 values,
the JSON-shaped configuration, engine version and report schema. A sidecar-backed
output is skipped only when all five still match. Explicit resume without a sidecar is
based only on output existence and is counted as unvalidated in the summary. Sidecars
contain original PII and are excluded by `.gitignore`.

## Why there is no document router

Court-specific routers tend to turn every new archive into another pipeline with its
own bugs and metrics. This library instead models structures that recur across Italian
decisions: role cues, bench lists, party blocks, biographic clauses, counsel lists,
public institutions and procedural identifiers. A pattern is added only when it
describes a reusable legal-text structure and has positive and negative tests.

`profile="query"` is only a performance shortcut that omits the long block scan. The
legacy `cassazione` and `generic` names normalize to `legal` and have no behavioral
branches.

A broader non-legal mode is intentionally not another profile yet. Its removal policy
and false-positive budget need a separately annotated general-Italian corpus first;
adding that branch before it can be measured would create operational complexity with
no defensible default.

## Optional NER and future training

NER emits `Mention` records and stops there. The common identity and policy layers are
what keep regex and model behavior auditable and comparable. An ensemble is simply the
union of mentions from several backends.

Custom-model training is intentionally paused. A future synthetic-data model should be
introduced as another `NerBackend`, benchmarked on complete-entity recall, complete
documents, protected-value survival and replacement precision, and should not create a
parallel anonymization pipeline.

## Known limitations

- Deterministic person recall remains weakest in low-structure civil and EU material.
- Optional NER improves recall but may remove uncued public-role aliases; exact role
  spans remain protected.
- A party list ends at the first item that is not name-shaped, and a name no cue
  introduces ("motivi aggiunti presentati da X") stays in clear unless it is also
  seen in a cued position.
- Review findings have high recall and low precision and therefore require triage.
- The evaluation corpus is useful but small (124 documents) and not a legal guarantee.
- PDF/OCR extraction quality is outside the package; malformed text can still hide PII.

See [`evaluation/RECALL_BENCHMARK.md`](evaluation/RECALL_BENCHMARK.md) for current
numbers and reproduction commands.
