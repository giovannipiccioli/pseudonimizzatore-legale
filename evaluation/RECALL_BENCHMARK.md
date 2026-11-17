# Recall-first benchmark

Measured on all 124 committed fixtures on 2026-11-17, with the library at the commit
that last changed this file. The transformer runs used CPU, threshold 0.3 and locally
cached model weights.

## Aggregate results

| Configuration | Complete entities | Names complete | Surface recall | Span precision LB | Character precision LB | Protected kept | Complete documents |
|---|---:|---:|---:|---:|---:|---:|---:|
| contextual baseline (`first_names=False`) | 448/488 (91.8%) | 333/373 (89.3%) | 705/768 (91.8%) | 782/942 (83.0%) | 84.2% | 722/726 (99.4%) | 97/124 |
| default (+ first-name list) | 472/488 (96.7%) | 357/373 (95.7%) | 746/768 (97.1%) | 817/989 (82.6%) | 83.5% | 718/726 (98.9%) | 111/124 |
| + Italian NER XXL, list disabled | 475/488 (97.3%) | 360/373 (96.5%) | 748/768 (97.4%) | 836/1126 (74.2%) | 76.8% | 698/726 (96.1%) | 111/124 |
| default + Italian NER XXL | 477/488 (97.7%) | 362/373 (97.1%) | 751/768 (97.8%) | 838/1130 (74.2%) | 76.7% | 696/726 (95.9%) | 113/124 |

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

| Source | Context only | + First names | + Italian NER XXL, list disabled | Default + Italian NER XXL |
|---|---:|---:|---:|---:|
| BDGT | 96.5% | 98.8% | 99.4% | 99.4% |
| Cassazione | 90.2% | 94.1% | 100.0% | 100.0% |
| CGUE | 0.0% | 50.0% | 50.0% | 50.0% |
| Consiglio di Stato | 96.0% | 100.0% | 98.0% | 100.0% |
| TAR | 93.4% | 97.2% | 97.2% | 98.1% |
| Corte dei conti | 87.2% | 97.4% | 97.4% | 97.4% |
| Merito civile | 80.6% | 91.0% | 91.0% | 91.0% |

NER adds most where the layout announces little: EU opinions, accounting and civil
decisions, and the people a penal decision names only in its narrative — victims,
witnesses — which no role cue introduces.

## Privacy/utility trade-off

The first-name detector gains 24 complete entities and 14 complete documents over the
contextual baseline. It creates 47 additional replacement decisions, lowers the
replacement-overlap precision bound by 0.4 points, and removes four protected
assertions. It reaches the same complete-document count as Italian NER XXL, with three
fewer complete entities and substantially less collateral removal.

Italian NER XXL gains 27 complete entities and 14 complete documents over the same
contextual baseline. It creates 184 additional replacement decisions, lowers the
replacement-overlap precision bound by 8.8 points, and removes 24 protected assertions.

The two do not add up: on top of the default, Italian NER XXL gains five complete
entities and two complete documents, for 141 more replacement decisions, 8.4 points of
precision bound and 22 protected assertions.

The protected-value change is expected under span-local policy: an explicit
`Presidente: NOME COGNOME` span stays, while an uncued later occurrence of that name is
an ordinary NER person proposal. Globally protecting judge surnames would improve the
utility number but reintroduce the more serious failure where an unrelated party with
the same surname survives.

For the stated priority—missing PII is worse than collateral removal—default + NER has
the highest entity recall. The first-name list captures most of that gain with far
lower runtime and deployment complexity.

Observed end-to-end elapsed time for the corpus was roughly 1.0 seconds for the
contextual baseline, 1.1 seconds with first names, and 25-27 seconds with Italian NER XXL.
Treat these only as relative figures; hardware, tokenizer cache and document lengths
dominate runtime.

## Review heuristic

The non-mutating review scan has these document-level confusion matrices against
annotated residuals:

| Configuration | TP | FN | FP | TN | Recall | Precision |
|---|---:|---:|---:|---:|---:|---:|
| contextual baseline | 27 | 0 | 93 | 4 | 100.0% | 22.5% |
| + first names | 13 | 0 | 107 | 4 | 100.0% | 10.8% |

This is deliberately noisy. It is a review queue, not evidence that one of the four
`passed_checks` documents is anonymous.

## Reproduce

```bash
python evaluation/score_corpus.py
python evaluation/score_corpus.py --no-first-names

python evaluation/ner/ab_corpus.py \
  --model DeepMount00/Italian_NER_XXL_v2 \
  --threshold 0.3 --device cpu --no-first-names

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
