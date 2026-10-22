# Evaluation

The evaluation directory measures privacy recall, collateral removal and review
behavior on 124 committed Italian legal-decision fixtures. Identities in the fixtures
are invented; the private source archives are not required to run a score.

Unit tests are the CI gate. Corpus scores are measurements rather than pass/fail tests:
adding a difficult document can correctly lower a metric.

## Main score

```bash
python evaluation/score_corpus.py
python evaluation/score_corpus.py corte_conti
python evaluation/score_corpus.py -v
```

Current deterministic default (legal context plus the first-name list):

| Source | Complete entities | Surface recall | Span precision LB | Protected kept | Complete documents |
|---|---:|---:|---:|---:|---:|
| BDGT | 170/173 (98.3%) | 179/182 (98.4%) | 250/315 (79.4%) | 197/197 | 20/23 |
| Cassazione | 48/51 (94.1%) | 78/81 (96.3%) | 88/110 (80.0%) | 137/137 | 24/25 |
| CGUE | 1/2 (50.0%) | 2/3 (66.7%) | 1/1 (100.0%) | 17/17 | 7/8 |
| Consiglio di Stato | 50/50 (100.0%) | 98/98 (100.0%) | 77/89 (86.5%) | 78/78 | 16/16 |
| TAR | 102/106 (96.2%) | 197/204 (96.6%) | 205/227 (90.3%) | 81/85 | 18/21 |
| Corte dei conti | 38/39 (97.4%) | 68/69 (98.6%) | 60/68 (88.2%) | 140/140 | 14/15 |
| Merito civile | 61/67 (91.0%) | 121/131 (92.4%) | 133/151 (88.1%) | 70/72 | 10/16 |
| **Total** | **470/488 (96.3%)** | **743/768 (96.7%)** | **814/961 (84.7%)** | **720/726** | **109/124** |

The scorer also reports:

- names: 355/373 complete (95.2%);
- structured identifiers/other: 115/115 complete (100%);
- character-overlap precision lower bound: 16,543/19,275 (85.8%);
- damage-free documents (no protected value lost): 121/124;
- review heuristic: TP/FN/FP/TN = 15/0/105/4, or 100% recall and 12.5%
  precision for finding documents with an annotated residual.

Use `python evaluation/score_corpus.py --no-first-names` for the contextual baseline:
446/488 complete entities, 331/373 complete names and 96/124 complete documents.

## Metric definitions

**Complete-entity recall is primary.** All annotated aliases and repeated occurrences
of one identity must disappear. Removing two of three spellings scores that entity as a
failure.

**Complete documents are stricter.** One missed entity fails the entire document. This
is closest to the operational concern that one surviving name can make the output
unusable.

**Surface recall is retained for continuity.** It counts strings rather than identities
and is mainly useful for diagnosing the missed spelling.

**Span precision is a lower bound.** A predicted replacement is counted correct when it
overlaps an annotated must-remove span. The corpus does not exhaustively annotate every
incidental sensitive or harmless span, so unannotated true PII is conservatively counted
against this metric. Character overlap additionally penalizes overly wide spans.

**Protected kept** checks selected judges/public roles, institutions, places and case
numbers. It is a collateral-damage sentinel, not exhaustive classical precision.

**Review recall/precision** compares `Report.status` with annotated leaks. The broad
review scanner is intentionally noisy and never certifies `passed_checks` documents.

## NER comparison

```bash
python evaluation/ner/ab_corpus.py \
  --model DeepMount00/Italian_NER_XXL_v2 \
  --threshold 0.3 --device cpu

python evaluation/ner/ab_corpus.py \
  --model DeepMount00/Italian_NER_XXL_v2 \
  --model Davlan/xlm-roberta-base-ner-hrl \
  --threshold 0.3 --device cpu
```

Install `.[ner]` first. See [`RECALL_BENCHMARK.md`](RECALL_BENCHMARK.md) for the current
full comparison and interpretation.

## Repository contents

| Path | Purpose |
|---|---|
| `score_corpus.py` | regex-only per-document and per-source score |
| `metrics.py` | shared entity, surface, keep and replacement-overlap metrics |
| `ner/ab_corpus.py` | regex versus one NER model or a mention union |
| `ner/throughput.py` | end-to-end timing on an explicit corpus root |
| `corpus/` | committed text and gold fixtures |
| `build_corpus/` | regenerate fixtures from private source archives, and audit them for real names |
| `corpus_stats.py` | rebuild the packaged common-word resource from any corpus |

Rebuild the common-word resource explicitly:

```bash
python evaluation/corpus_stats.py /path/to/legal/txt --documents 3000
```

Rebuild fixtures only when the private archive roots are configured, then check them
twice — the heuristic gate, and an NER model whose list you read by eye:

```bash
python evaluation/build_corpus/build_fixtures.py --help
python evaluation/build_corpus/build_fixtures.py
python evaluation/build_corpus/check_fixtures.py
python evaluation/build_corpus/ner_audit.py
```

The gold policy is privacy-first for a complete identity carrying both judicial and
private-role evidence: that identity belongs in `must_remove`. A public prosecutor with
only a judicial-role cue belongs in `must_keep`. These rules mirror runtime late policy
and prevent internally contradictory annotations.
