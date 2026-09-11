# Recall-first benchmark

Measured on 2026-09-11 with `pseudonimizzatore-legale` 0.3.0 and all 124 committed fixtures.
Transformer runs used CPU, threshold 0.3 and locally cached model weights.

## Aggregate results

| Configuration | Complete entities | Names complete | Surface recall | Span precision LB | Character precision LB | Protected kept | Complete documents |
|---|---:|---:|---:|---:|---:|---:|---:|
| regex only | 441/503 (87.7%) | 326/388 (84.0%) | 692/794 (87.2%) | 757/878 (86.2%) | 87.1% | 700/700 (100%) | 89/124 |
| + Italian NER XXL | 472/503 (93.8%) | 357/388 (92.0%) | 742/794 (93.5%) | 827/1081 (76.5%) | 78.6% | 676/700 (96.6%) | 102/124 |

Every configuration removes 115/115 annotated structured identifiers/other entities.
The remaining gap is person recognition.

The XXL + XLM-R union has not been re-measured on this corpus. On the earlier
103-fixture corpus (2026-08-11) it added two complete entities and two complete
documents beyond Italian NER XXL alone.

“Complete entity” is all-or-nothing: every alias and repeated occurrence must be gone.
“Complete document” is stricter again: one failed entity fails the whole document.
These are the primary privacy metrics. Surface recall is retained to show which spelling
was missed.

Span precision is a conservative lower bound over actual replacement decisions. The
gold does not exhaustively annotate all incidental PII, so a replacement outside a gold
span may still be correct. Character precision additionally penalizes overly wide spans.

## Entity recall by source

| Source | Regex | + Italian NER XXL |
|---|---:|---:|
| BDGT | 96.0% | 99.4% |
| Cassazione | 90.2% | 100.0% |
| CGUE | 0.0% | 50.0% |
| Consiglio di Stato | 94.0% | 98.0% |
| TAR | 90.7% | 95.3% |
| Corte dei conti | 76.7% | 88.4% |
| Merito civile | 67.5% | 76.6% |

NER adds most where the layout announces little: EU opinions, accounting and civil
decisions, and the people a penal decision names only in its narrative — victims,
witnesses — which no role cue introduces.

## Privacy/utility trade-off

Italian NER XXL gains 31 complete entities and 13 complete documents over regex alone.
It also creates 203 additional replacement decisions, lowers the replacement-overlap
precision bound by 9.7 points, and removes 24 protected assertions.

The protected-value change is expected under span-local policy: an explicit
`Presidente: NOME COGNOME` span stays, while an uncued later occurrence of that name is
an ordinary NER person proposal. Globally protecting judge surnames would improve the
utility number but reintroduce the more serious failure where an unrelated party with
the same surname survives.

For the stated priority—missing PII is worse than collateral removal—NER is the
stronger configuration. Regex-only remains useful when throughput, explainability or
preservation of uncued public-role aliases matters more.

Observed end-to-end elapsed time in this run was roughly 0.8 seconds for regex-only and
28.5 seconds with Italian NER XXL. Treat these only as relative figures; hardware,
tokenizer cache and document lengths dominate runtime.

## Review heuristic

On regex-only output, the non-mutating review scan has this document-level confusion
matrix against annotated residuals:

| TP | FN | FP | TN | Recall | Precision |
|---:|---:|---:|---:|---:|---:|
| 35 | 0 | 85 | 4 | 100.0% | 29.2% |

This is deliberately noisy. It is a review queue, not evidence that one of the four
`passed_checks` documents is anonymous.

## Reproduce

```bash
python evaluation/score_corpus.py

python evaluation/ner/ab_corpus.py \
  --model DeepMount00/Italian_NER_XXL_v2 \
  --threshold 0.3 --device cpu

python evaluation/ner/ab_corpus.py \
  --model DeepMount00/Italian_NER_XXL_v2 \
  --model Davlan/xlm-roberta-base-ner-hrl \
  --threshold 0.3 --device cpu
```

For a network-isolated run after caching the weights:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
python evaluation/ner/ab_corpus.py \
  --model DeepMount00/Italian_NER_XXL_v2 \
  --threshold 0.3 --device cpu
```

The corpus builder and annotation policy are documented in
[`corpus/README.md`](corpus/README.md).
