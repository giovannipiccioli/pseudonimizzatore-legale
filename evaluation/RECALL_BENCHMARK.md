# Recall-first benchmark

Measured on all 124 committed fixtures. The contextual and Italian NER XXL rows were
recorded on 2026-09-14 with `pseudonimizzatore-legale` 0.3.0; the first-name row was
measured on 2026-10-13. The transformer run used CPU, threshold 0.3 and locally cached
model weights. It predates the first-name detector, so that row has the list disabled.

## Aggregate results

| Configuration | Complete entities | Names complete | Surface recall | Span precision LB | Character precision LB | Protected kept | Complete documents |
|---|---:|---:|---:|---:|---:|---:|---:|
| contextual baseline (`first_names=False`) | 446/488 (91.4%) | 331/373 (88.7%) | 702/768 (91.4%) | 779/896 (86.9%) | 87.7% | 724/726 (99.7%) | 96/124 |
| default (+ first-name list) | 470/488 (96.3%) | 355/373 (95.2%) | 743/768 (96.7%) | 814/961 (84.7%) | 85.8% | 720/726 (99.2%) | 109/124 |
| + Italian NER XXL, list disabled | 473/488 (96.9%) | 358/373 (96.0%) | 744/768 (96.9%) | 834/1079 (77.3%) | 79.5% | 698/726 (96.1%) | 109/124 |

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

| Source | Context only | + First names | + Italian NER XXL, list disabled |
|---|---:|---:|---:|
| BDGT | 96.0% | 98.3% | 99.4% |
| Cassazione | 90.2% | 94.1% | 100.0% |
| CGUE | 0.0% | 50.0% | 50.0% |
| Consiglio di Stato | 96.0% | 100.0% | 98.0% |
| TAR | 92.5% | 96.2% | 96.2% |
| Corte dei conti | 87.2% | 97.4% | 97.4% |
| Merito civile | 80.6% | 91.0% | 89.6% |

NER adds most where the layout announces little: EU opinions, accounting and civil
decisions, and the people a penal decision names only in its narrative — victims,
witnesses — which no role cue introduces.

## Privacy/utility trade-off

The first-name detector gains 24 complete entities and 13 complete documents over the
contextual baseline. It creates 65 additional replacement decisions, lowers the
replacement-overlap precision bound by 2.2 points, and removes four protected
assertions. On this corpus it reaches the same complete-document count as the older XXL
run, with three fewer complete entities and substantially less collateral removal.

Italian NER XXL gains 27 complete entities and 13 complete documents over the same
contextual baseline. It creates 183 additional replacement decisions, lowers the
replacement-overlap precision bound by 9.6 points, and removes 26 protected assertions.

The protected-value change is expected under span-local policy: an explicit
`Presidente: NOME COGNOME` span stays, while an uncued later occurrence of that name is
an ordinary NER person proposal. Globally protecting judge surnames would improve the
utility number but reintroduce the more serious failure where an unrelated party with
the same surname survives.

For the stated priority—missing PII is worse than collateral removal—the existing NER
measurement still has the highest entity recall. The first-name list captures most of
that gain with far lower runtime and deployment complexity. The combined default + NER
configuration has not yet been measured, so gains should not be assumed to add.

Observed end-to-end elapsed time was roughly 0.88 seconds for the contextual baseline,
0.92 seconds with first names, and 24.2 seconds in the earlier Italian NER XXL run.
Treat these only as relative figures; hardware, tokenizer cache and document lengths
dominate runtime.

## Review heuristic

The non-mutating review scan has these document-level confusion matrices against
annotated residuals:

| Configuration | TP | FN | FP | TN | Recall | Precision |
|---|---:|---:|---:|---:|---:|---:|
| contextual baseline | 28 | 0 | 92 | 4 | 100.0% | 23.3% |
| + first names | 15 | 0 | 105 | 4 | 100.0% | 12.5% |

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
