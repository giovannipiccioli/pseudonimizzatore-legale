# Evaluation

The evaluation directory measures privacy recall, collateral removal and review
behavior on 103 committed Italian legal-decision fixtures. Identities in the fixtures
are invented; the private source archives are not required to run a score.

Unit tests are the CI gate. Corpus scores are measurements rather than pass/fail tests:
adding a difficult document can correctly lower a metric.

## Main score

```bash
python evaluation/score_corpus.py
python evaluation/score_corpus.py corte_conti
python evaluation/score_corpus.py -v
```

Current regex-only result:

| Source | Complete entities | Surface recall | Span precision LB | Protected kept | Complete documents |
|---|---:|---:|---:|---:|---:|
| BDGT | 166/173 (96.0%) | 174/181 (96.1%) | 245/313 (78.3%) | 194/194 | 19/23 |
| Cassazione | 37/37 (100.0%) | 57/57 (100.0%) | 65/94 (69.1%) | 131/131 | 25/25 |
| CGUE | 0/2 (0.0%) | 0/3 (0.0%) | 0/0 | 17/17 | 7/8 |
| Consiglio di Stato | 45/56 (80.4%) | 90/112 (80.4%) | 79/91 (86.8%) | 60/60 | 6/16 |
| Corte dei conti | 28/35 (80.0%) | 55/68 (80.9%) | 51/58 (87.9%) | 133/133 | 10/15 |
| Merito civile | 52/75 (69.3%) | 103/145 (71.0%) | 109/130 (83.8%) | 56/56 | 4/16 |
| **Total** | **328/378 (86.8%)** | **479/566 (84.6%)** | **549/686 (80.0%)** | **591/591** | **71/103** |

The scorer also reports:

- names: 221/271 complete (81.5%);
- structured identifiers/other: 107/107 complete (100%);
- character-overlap precision lower bound: 11,427/14,110 (81.0%);
- review heuristic: TP/FN/FP/TN = 32/0/67/4, or 100% recall and 32.3%
  precision for finding documents with an annotated residual.

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
| `build_corpus/` | regenerate fixtures from private source archives |
| `corpus_stats.py` | rebuild the packaged common-word resource from any corpus |

Rebuild the common-word resource explicitly:

```bash
python evaluation/corpus_stats.py /path/to/legal/txt --documents 3000
```

Rebuild fixtures only when the private archive roots are configured:

```bash
python evaluation/build_corpus/build_fixtures.py --help
python evaluation/build_corpus/build_fixtures.py
python evaluation/build_corpus/check_fixtures.py
```

The gold policy is privacy-first for a complete identity carrying both judicial and
private-role evidence: that identity belongs in `must_remove`. A public prosecutor with
only a judicial-role cue belongs in `must_keep`. These rules mirror runtime late policy
and prevent internally contradictory annotations.
