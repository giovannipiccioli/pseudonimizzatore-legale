# pseudonimizzatore_legale

[Italiano](README.it.md) · **English**

`pseudonimizzatore_legale` is a local Python library for pseudonymizing Italian legal
decisions. It replaces private individuals and structured personal data with readable,
document-local tags while preserving judges, public bodies, places, and case numbers.

The distribution is named `pseudonimizzatore-legale`; Python imports use the
underscore form `pseudonimizzatore_legale`.

```python
from pseudonimizzatore_legale import anonymize

source = (
    "Il ricorrente Mario Rossi, C.F. RSSMRA80A01H501U, "
    "è rappresentato dall'avv. Laura Bianchi."
)

output, report = anonymize(source)
print(output)
```

```text
Il ricorrente Ricorrente_1, C.F. CF_1, è rappresentato dall'avv. Difensore_1.
```

The returned `report` explains what happened:

```python
print(report.mapping)
# {
#   'Mario Rossi': 'Ricorrente_1',
#   'RSSMRA80A01H501U': 'CF_1',
#   'Laura Bianchi': 'Difensore_1'
# }

print(report.status)
# passed_checks
```

> [!IMPORTANT]
> This is pseudonymization, not a guarantee of anonymity. `passed_checks` only means
> that the control heuristics found nothing. Review sensitive output before
> publication or disclosure.

## Install

Python 3.10 or newer is required. From a checkout of this repository:

```bash
python -m pip install .
```

For development:

```bash
python -m pip install -e ".[dev]"
```

The base engine works offline and has one runtime dependency. Optional transformer NER
also installs PyTorch and related tokenizer packages:

```bash
python -m pip install -e ".[ner]"
```

## What it removes

The default policy is designed for published Italian legal decisions:

| Evidence | Default action |
|---|---|
| parties, counsel, and private natural persons | replace |
| tax IDs, email/PEC, IBAN, phone, plates, identity documents, birth dates | replace |
| personally cued residential addresses | replace |
| exact judicial and public-prosecution role spans | keep |
| public bodies, institutions, and place names | keep |
| procedural case numbers and ECLI identifiers | keep |
| private companies | keep; replace likely person-named firms with `companies="person_named"`, or all detected firms with `companies=True` |
| conflicting judicial and private-role evidence for one identity | replace and flag for review |

Tags are stable only inside one document. This avoids creating a persistent identifier
that could link the same person across different decisions.

## Configure a run

Pass either a `Config` object or keyword overrides:

```python
from pseudonimizzatore_legale import Config, anonymize

config = Config(
    companies="person_named",
    keep_judges=True,
    keep_case_numbers=True,
    sanitize=True,
    verify=True,
)
output, report = anonymize(source, config)

# Equivalent for one option:
output, report = anonymize(source, companies="person_named")
```

`companies="person_named"` is deliberately precision-first. It replaces companies
with explicit family wording (`F.lli`, `Fratelli`, or `Eredi`) and simple names made
of two surname-shaped words joined by `e` or `&`, such as `Mazzetti e Franchi s.r.l.`.
It leaves ambiguous brand-like names such as `Labium spa` and `Etofi srl`, along with
many genuine single-surname firms. This is a small spelling heuristic, not a surname
registry or a claim of complete coverage. Use `companies=True` when broader company
removal is more important than precision.

There is one document-agnostic `legal` pipeline. Legacy `cassazione` and `generic`
profiles are aliases, not court-specific routers. `profile="query"` only skips the
long party-block scan for short interactive strings.

## Identity consistency

Once a person is found from strong legal context, the library propagates likely local
aliases. A surname-first header, ordinary prose, and a bare distinctive surname can
therefore receive the same tag:

```python
decision = """sul ricorso proposto da
BENATTI ROSSELLA
-ricorrente-
Rossella Benatti insiste. La Benatti ricorre.
"""

output, report = anonymize(decision)
print(output)
print(report.mapping)
```

Judicial protection is span-local. A judge named `ROSSI MARIO` cannot globally shield
a different party named `ROSSI LUCIA`.

## Understand the report

The most useful fields are:

- `status`: `passed_checks`, `needs_review`, or `not_run`;
- `mapping`: original sensitive values to emitted tags;
- `decisions`: accepted keep/redact decisions and their evidence;
- `residuals`: possible personal data still present in the returned output;
- `warnings`: conflicting evidence that requires review;
- `replacement_spans`: normalized-input offsets of actual replacements;
- `risk`: compatibility triage score; prefer `status` and concrete findings.

`mapping` and batch `*.map.json` files contain the original sensitive values. Treat
them as sensitive data. Sidecars are excluded by `.gitignore`.

## Add optional NER

NER is another person detector inside the same pipeline, not a separate anonymizer:

```python
output, report = anonymize(
    source,
    ner="DeepMount00/Italian_NER_XXL_v2",
    ner_threshold=0.3,
    ner_device="cpu",
)
```

For a recall-first union of two models:

```python
output, report = anonymize(
    source,
    ner=(
        "DeepMount00/Italian_NER_XXL_v2",
        "Davlan/xlm-roberta-base-ner-hrl",
    ),
    ner_threshold=0.3,
)
```

Model weights are downloaded by Hugging Face on first use unless already cached. The
text itself is processed locally. Review each model's license and data policy before
deploying it.

## Process a directory

```python
from pseudonimizzatore_legale import anonymize_batch

summary = anonymize_batch(
    "decisions-in",
    "decisions-out",
    workers=4,
    sidecar=True,
    resume=True,
)

for item in summary["review_queue"]:
    print(item["dst"], item["status"], item["residuals"])
```

Source and destination trees must be disjoint. Writes are atomic, destination symlinks
are rejected, and invalid UTF-8 becomes a per-file error. Resume is opt-in. With
sidecars, it validates source and output hashes, configuration, report schema, and
engine version before skipping a file.

For NER batches, start with `ner_device="cpu"`: several worker processes competing for
one accelerator can be slower than CPU workers. Use an immutable local model snapshot
for reproducible resumed runs.

## Playground

[`notebooks/01_playground.ipynb`](notebooks/01_playground.ipynb) is an executable,
annotated tour covering the one-line API, configuration, alias consistency, review
status, optional NER, and file processing. Install the notebook dependencies first:

```bash
python -m pip install -e ".[notebooks]"
jupyter lab notebooks/01_playground.ipynb
```

Every identity in the notebook and committed evaluation corpus is invented.

## Measured performance

The repository includes 124 annotated fixtures spanning tax, civil, administrative
(Consiglio di Stato and TAR), accounting, Cassazione, and EU material. Complete-entity
recall is all-or-nothing: one surviving alias fails that identity.

| Configuration | Complete entities | Surface recall | Span precision lower bound | Protected kept | Complete documents |
|---|---:|---:|---:|---:|---:|
| regex only | 441/503 (87.7%) | 692/794 (87.2%) | 757/878 (86.2%) | 700/700 | 89/124 |
| + Italian NER XXL | 472/503 (93.8%) | 742/794 (93.5%) | 827/1081 (76.5%) | 676/700 | 102/124 |

Both configurations remove 115/115 annotated structured identifiers. The review
heuristic catches all 35 documents with annotated residuals, but also flags 85 without
one. It is deliberately a recall-heavy review queue, not a safety certificate.

See [`evaluation/RECALL_BENCHMARK.md`](evaluation/RECALL_BENCHMARK.md) for definitions,
source-level results, trade-offs, and reproduction commands.

## Tests

The deterministic test suite and anonymized evaluation fixtures are included:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python evaluation/build_corpus/check_fixtures.py
python evaluation/score_corpus.py
```

Optional real-model tests run automatically when the Italian XXL model is already in
the Hugging Face cache. CI runs Python 3.10 and 3.12 and executes the playground.

## Design and project layout

The short version of the pipeline is: normalize, collect evidence, resolve local
identities, apply late span-level policy, render once, and scan the output for review.
See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the reasoning and extension points.

```text
pseudonimizzatore_legale/ runtime package
tests/                   unit and integration tests
notebooks/               executable user playground
evaluation/corpus/       124 fixtures with invented identities
evaluation/              scorers and corpus-building utilities
```

## Origin and acknowledgement

This project started from [**Anonimator**](https://github.com/avvocati-e-mac/anonimator),
the offline legal-document pseudonymizer created by **Filippo Strozzi**. In particular,
Anonimator provided the starting ideas and patterns for Italian legal roles, structured
identifiers, local processing, and hybrid regex/NER detection.

This repository reworks that starting point as a document-agnostic, test-driven Python
library with late policy resolution, document-local identity propagation, residual
review, batch safety, and entity-level evaluation. Thank you to Filippo Strozzi for
making the original project available.

## Contributing, security, and license

See [`CONTRIBUTING.md`](CONTRIBUTING.md) before sending a change. Never submit real
personal data in an issue, test, or fixture. Security and privacy reports should follow
[`SECURITY.md`](SECURITY.md).

MIT licensed. See [`LICENSE`](LICENSE). The license preserves the copyright notice for
the Anonimator-derived portions as well as this Python implementation.
