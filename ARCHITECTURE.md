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
5. **Simple extension points.** Optional NER supplies the same `Mention` objects as the
   regex detectors and uses the same identity, policy and rendering stages.
6. **Verification does not mutate.** Residual checks only produce review evidence.

## Pipeline stages

### 1. Normalize

`text.py` applies NFKC normalization, removes zero-width characters, normalizes quotes,
decodes entities, repairs line-wrap hyphenation and flattens light Markdown when
`sanitize=True`. Detection and replacement offsets therefore refer to this normalized
text, not necessarily the raw input bytes.

### 2. Detect evidence

The runtime has a small set of complementary detectors:

- `patterns.py`: structured PII, legal roles, person cues, party blocks, addresses and
  organization/legal-form patterns;
- `protect.py`: exact judicial-role and procedural-number evidence;
- `seeds.py`: private-person seeds from legal context;
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

### 4. Apply policy and resolve overlaps

`policy.py` filters candidates using `Config`, then greedily accepts non-overlapping
spans by evidence priority and length:

| Priority | Evidence |
|---:|---|
| 120 | structured personal data |
| 100 | exact judicial-role and procedural-number keeps |
| 40 | personally cued residential address |
| 30 | full person identity |
| 20 | distinctive or ambiguous person token |
| 10 | private company |

Structured PII deliberately outranks kept case identifiers, so a birth date such as
`12/03/1974` cannot survive because a substring resembles a case number.

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

`keep_judges=False` and `keep_case_numbers=False` remove their keep decisions; they do
not add special redactors. Public institutions are rejected as person/company
candidates. Places are not proposed in the first place.

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

## Optional NER and future training

NER emits `Mention` records and stops there. The common identity and policy layers are
what keep regex and model behavior auditable and comparable. An ensemble is simply the
union of mentions from several backends.

Custom-model training is intentionally paused. A future synthetic-data model should be
introduced as another `NerBackend`, benchmarked on complete-entity recall, complete
documents, protected-value survival and replacement precision, and should not create a
parallel anonymization pipeline.

## Known limitations

- Regex-only person recall remains weakest in low-structure civil and EU material.
- Optional NER improves recall but may remove uncued public-role aliases; exact role
  spans remain protected.
- Review findings have high recall and low precision and therefore require triage.
- The evaluation corpus is useful but small (103 documents) and not a legal guarantee.
- PDF/OCR extraction quality is outside the package; malformed text can still hide PII.

See [`evaluation/RECALL_BENCHMARK.md`](evaluation/RECALL_BENCHMARK.md) for current
numbers and reproduction commands.
