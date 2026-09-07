"""Score the annotated corpus with NER off, then on, and print the difference.

The question this answers is not "does NER find more names" — it obviously does — but
whether it completely removes more identities. One entity fails if any occurrence of
any alias remains. Historical surface-form recall, a conservative replacement-precision
lower bound, protected-value survival and complete-document rate remain visible too.

* **removed** goes up if NER finds parties the layout does not announce;
* **kept** may go down because only explicit judicial-role spans are retained; an
  uncued judge alias is intentionally treated like any other NER person proposal.

The second number is the one that decides it. Over-removing a judge is a data-quality
failure the regex path currently has at zero, and trading that away for recall is not
obviously worth it.

    python ab_corpus.py                                   # default model, whole corpus
    python ab_corpus.py --model Babelscape/wikineural-multilingual-ner
    python ab_corpus.py --model model/a --model model/b  # union detections
    python ab_corpus.py --source merito_civile --show     # one source, with detail
    python ab_corpus.py --threshold 0.8

Models must already be in the Hugging Face cache — this never downloads.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from pseudonimizzatore_legale import Config, anonymize          # noqa: E402
from pseudonimizzatore_legale import text as text_mod            # noqa: E402
from evaluation.metrics import score_output            # noqa: E402

CORPUS = Path(__file__).resolve().parent.parent / "corpus"
DEFAULT_MODEL = "DeepMount00/Italian_NER_XXL_v2"

def accumulate(counter, score):
    for field in score.__dataclass_fields__:
        if field not in {"leaked", "lost"}:
            counter[field] += getattr(score, field)


def score(cfg_factory, docs, label):
    """Run every document and tally removed/kept, plus timing."""
    stats, per_source = Counter(), {}
    leaked_new, lost_new = [], []
    elapsed = 0.0
    detail = {}

    for gold_path in docs:
        doc = gold_path.with_suffix("").with_suffix(".txt")
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        raw = doc.read_text(encoding="utf-8")
        cfg = cfg_factory(gold.get("config", {}))

        t0 = time.perf_counter()
        original = text_mod.sanitize(raw) if cfg.sanitize else raw
        original = text_mod.normalize_quotes(original)
        out, report = anonymize(raw, cfg)
        elapsed += time.perf_counter() - t0

        src = doc.parent.name
        p = per_source.setdefault(src, Counter())
        metrics = score_output(original, out, gold, report.replacement_spans)
        accumulate(stats, metrics)
        accumulate(p, metrics)
        stats["docs"] += 1
        p["docs"] += 1
        stats["clean_docs"] += metrics.entity_ok == metrics.entity_total
        p["clean_docs"] += metrics.entity_ok == metrics.entity_total
        stats["damage_free_docs"] += metrics.keep_ok == metrics.keep_total
        p["damage_free_docs"] += metrics.keep_ok == metrics.keep_total

        detail[f"{src}/{doc.stem}"] = {
            "leaked": set(metrics.leaked), "lost": set(metrics.lost)
        }
        leaked_new += [(f"{src}/{doc.stem}", s) for s in metrics.leaked]
        lost_new += [(f"{src}/{doc.stem}", s) for s in metrics.lost]

    return {"label": label, "stats": stats, "per_source": per_source,
            "seconds": elapsed, "detail": detail,
            "leaked": leaked_new, "lost": lost_new}


def pct(c, ok, total):
    return 100 * c[ok] / c[total] if c[total] else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="append", dest="models",
                    help="model id; repeat to union several detectors")
    ap.add_argument("--threshold", type=float, default=0.60)
    ap.add_argument("--device", default=None, help="cpu | mps | cuda (default: auto)")
    ap.add_argument("--source", default=None, help="limit to one corpus source")
    ap.add_argument("--show", action="store_true", help="list what changed, per document")
    ap.add_argument("--compact", action="store_true", help="omit per-source rows")
    args = ap.parse_args()

    docs = sorted(CORPUS.rglob("*.gold.json"))
    if args.source:
        docs = [d for d in docs if d.parent.name == args.source]
    if not docs:
        sys.exit(f"no documents found (source={args.source!r})")

    models = args.models or [DEFAULT_MODEL]
    model_spec = models[0] if len(models) == 1 else tuple(models)
    print(f"{len(docs)} documents | model {' + '.join(models)} | "
          f"threshold {args.threshold}\n")

    off = score(lambda g: Config(**g), docs, "regex only")
    on = score(lambda g: Config(**g, ner=model_spec, ner_threshold=args.threshold,
                                ner_device=args.device), docs, "regex + NER")

    hdr = (f"{'':18s} {'entity recall':>19s} {'surface recall':>19s} "
           f"{'precision LB':>16s} {'kept':>18s} {'complete docs':>13s} {'sec':>7s}")
    print(hdr); print("-" * len(hdr))
    for r in (off, on):
        c = r["stats"]
        print(f"{r['label']:18s} "
              f"{c['entity_ok']:>4d}/{c['entity_total']:<4d}"
              f"{pct(c,'entity_ok','entity_total'):>6.1f}% "
              f"{c['surface_ok']:>4d}/{c['surface_total']:<4d}"
              f"{pct(c,'surface_ok','surface_total'):>6.1f}% "
              f"{c['prediction_ok']:>4d}/{c['prediction_total']:<4d}"
              f"{pct(c,'prediction_ok','prediction_total'):>6.1f}% "
              f"{c['keep_ok']:>4d}/{c['keep_total']:<4d}"
              f"{pct(c,'keep_ok','keep_total'):>6.1f}% "
              f"{c['clean_docs']:>4d}/{c['docs']:<4d} {r['seconds']:>7.1f}")
    d_ent = (pct(on["stats"], "entity_ok", "entity_total")
             - pct(off["stats"], "entity_ok", "entity_total"))
    d_surface = (pct(on["stats"], "surface_ok", "surface_total")
                 - pct(off["stats"], "surface_ok", "surface_total"))
    d_kp = (pct(on["stats"], "keep_ok", "keep_total")
            - pct(off["stats"], "keep_ok", "keep_total"))
    slow = on["seconds"] / off["seconds"] if off["seconds"] else float("nan")
    print("-" * len(hdr))
    print(f"{'delta':18s} {d_ent:>+18.1f}% {d_surface:>+18.1f}% "
          f"{'':16s} {d_kp:>+17.1f}% {'':11s} {slow:>6.0f}×\n")

    if not args.compact:
        print(f"{'source':18s} {'entity recall off→on':>24s} "
              f"{'surface recall off→on':>25s} {'kept off→on':>21s}")
        for src in sorted(off["per_source"]):
            a, b = off["per_source"][src], on["per_source"][src]
            print(f"{src:18s} "
                  f"{pct(a,'entity_ok','entity_total'):>9.1f}% →"
                  f"{pct(b,'entity_ok','entity_total'):>9.1f}% "
                  f"{pct(a,'surface_ok','surface_total'):>9.1f}% →"
                  f"{pct(b,'surface_ok','surface_total'):>9.1f}% "
                  f"{pct(a,'keep_ok','keep_total'):>8.1f}% →"
                  f"{pct(b,'keep_ok','keep_total'):>8.1f}%")

    for result in (off, on):
        c = result["stats"]
        print(
            f"\n{result['label']}: names {c['name_entity_ok']}/"
            f"{c['name_entity_total']} complete "
            f"({pct(c,'name_entity_ok','name_entity_total'):.1f}%), "
            f"identifiers/other {c['identifier_entity_ok']}/"
            f"{c['identifier_entity_total']} complete "
            f"({pct(c,'identifier_entity_ok','identifier_entity_total'):.1f}%), "
            f"partial {c['entity_partial']}, missed {c['entity_missed']}, "
            f"character precision LB "
            f"{pct(c,'predicted_char_ok','predicted_char_total'):.1f}%"
        )

    # What actually changed, in both directions.
    gained = [(d, s) for d, s in off["leaked"] if s not in on["detail"][d]["leaked"]]
    broke = [(d, s) for d, s in on["lost"] if s not in off["detail"][d]["lost"]]
    new_leaks = [(d, s) for d, s in on["leaked"] if s not in off["detail"][d]["leaked"]]

    print(f"\nNER newly removed : {len(gained)} surface assertions")
    print(f"NER newly removed protected assertions: {len(broke)}")
    print(f"NER newly missed  : {len(new_leaks)}")

    if args.show:
        for title, items in (("NEWLY REMOVED (good)", gained),
                             ("NEWLY BROKEN (bad)", broke),
                             ("NEWLY MISSED", new_leaks)):
            if items:
                print(f"\n--- {title} ---")
                for doc, s in items[:40]:
                    print(f"   {doc:52s} {s!r}")


if __name__ == "__main__":
    main()
