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

Current regex-only result:

| Source | Complete entities | Surface recall | Span precision LB | Protected kept | Complete documents |
|---|---:|---:|---:|---:|---:|
| BDGT | 166/173 (96.0%) | 175/182 (96.2%) | 246/314 (78.3%) | 197/197 | 19/23 |
| Cassazione | 46/51 (90.2%) | 73/81 (90.1%) | 79/95 (83.2%) | 137/137 | 23/25 |
| CGUE | 0/2 (0.0%) | 0/3 (0.0%) | 0/0 | 17/17 | 7/8 |
| Consiglio di Stato | 47/50 (94.0%) | 92/98 (93.9%) | 74/84 (88.1%) | 78/78 | 13/16 |
| TAR | 97/107 (90.7%) | 189/206 (91.7%) | 199/215 (92.6%) | 83/83 | 16/21 |
| Corte dei conti | 33/43 (76.7%) | 60/77 (77.9%) | 55/57 (96.5%) | 132/132 | 8/15 |
| Merito civile | 52/77 (67.5%) | 103/147 (70.1%) | 104/113 (92.0%) | 56/56 | 3/16 |
| **Total** | **441/503 (87.7%)** | **692/794 (87.2%)** | **757/878 (86.2%)** | **700/700** | **89/124** |

The scorer also reports:

- names: 326/388 complete (84.0%);
- structured identifiers/other: 115/115 complete (100%);
- character-overlap precision lower bound: 15,451/17,741 (87.1%);
- damage-free documents (no protected value lost): 124/124;
- review heuristic: TP/FN/FP/TN = 35/0/85/4, or 100% recall and 29.2%
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
