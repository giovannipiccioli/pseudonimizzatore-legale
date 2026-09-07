# Recall-first benchmark

Measured on 2026-08-11 with `pseudonimizzatore-legale` 0.2.0 and all 103 committed fixtures.
Transformer runs used CPU, threshold 0.3 and locally cached model weights.

## Aggregate results

| Configuration | Complete entities | Names complete | Surface recall | Span precision LB | Character precision LB | Protected kept | Complete documents |
|---|---:|---:|---:|---:|---:|---:|---:|
| regex only | 328/378 (86.8%) | 221/271 (81.5%) | 479/566 (84.6%) | 549/686 (80.0%) | 81.0% | 591/591 (100%) | 71/103 |
| + Italian NER XXL | 347/378 (91.8%) | 240/271 (88.6%) | 510/566 (90.1%) | 589/841 (70.0%) | 73.9% | 570/591 (96.4%) | 81/103 |
| + XXL and XLM-R union | 349/378 (92.3%) | 242/271 (89.3%) | 513/566 (90.6%) | 591/870 (67.9%) | 72.5% | 570/591 (96.4%) | 83/103 |

Every configuration removes 107/107 annotated structured identifiers/other entities.
The remaining gap is person recognition.

“Complete entity” is all-or-nothing: every alias and repeated occurrence must be gone.
“Complete document” is stricter again: one failed entity fails the whole document.
These are the primary privacy metrics. Surface recall is retained to show which spelling
was missed.

Span precision is a conservative lower bound over actual replacement decisions. The
gold does not exhaustively annotate all incidental PII, so a replacement outside a gold
span may still be correct. Character precision additionally penalizes overly wide spans.

## Entity recall by source

| Source | Regex | + Italian NER XXL | + XXL/XLM-R union |
|---|---:|---:|---:|
| BDGT | 96.0% | 99.4% | 99.4% |
| Cassazione | 100.0% | 100.0% | 100.0% |
| CGUE | 0.0% | 100.0% | 100.0% |
| Consiglio di Stato | 80.4% | 83.9% | 83.9% |
| Corte dei conti | 80.0% | 88.6% | 88.6% |
| Merito civile | 69.3% | 77.3% | 80.0% |

NER adds little to strongly structured Cassazione input and most to low-structure EU,
accounting and civil decisions. The two-model union adds two complete entities and two
complete documents beyond Italian NER XXL alone.

## Privacy/utility trade-off

The recall-first NER union gains 21 complete entities and 12 complete documents over
regex alone. It also creates 184 additional replacement decisions, lowers the
replacement-overlap precision bound by 12.1 points, and removes 21 protected assertions.

The protected-value change is expected under span-local policy: an explicit
`Presidente: NOME COGNOME` span stays, while an uncued later occurrence of that name is
an ordinary NER person proposal. Globally protecting judge surnames would improve the
utility number but reintroduce the more serious failure where an unrelated party with
the same surname survives.

For the stated priority—missing PII is worse than collateral removal—the ensemble is
the strongest tested configuration. Regex-only remains useful when throughput,
explainability or preservation of uncued public-role aliases matters more.

Observed end-to-end elapsed time in this run was roughly 0.6 seconds for regex-only,
21.7 seconds with Italian NER XXL and 42.4 seconds for the union. Treat these only as
relative figures; hardware, tokenizer cache and document lengths dominate runtime.

## Review heuristic

On regex-only output, the non-mutating review scan has this document-level confusion
matrix against annotated residuals:

| TP | FN | FP | TN | Recall | Precision |
|---:|---:|---:|---:|---:|---:|
| 32 | 0 | 67 | 4 | 100.0% | 32.3% |

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
