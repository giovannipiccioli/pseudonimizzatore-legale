"""Score the engine on the non-decision document corpus and print where it falls short.

`corpus_documents/` holds the documents a professional pseudonymizes before sharing:
briefs, contracts, letters, minutes, expert reports, e-mails, powers of attorney and
requests to the Agenzia delle Entrate, plus a small `narrativa` family of public-domain
prose used as an uncued-name stress test. Like score_corpus.py this is a
**measurement**, not a test suite: no pass/fail, no exit code to gate on.

    python score_documents.py                  # default, first_names=False, + NER if cached
    python score_documents.py email            # one family
    python score_documents.py -v               # show surrounding text for each leak
    python score_documents.py --no-ner         # skip the transformer run
    python score_documents.py --quiet          # tables only, no per-document lines

The columns are score_corpus.py's, computed by the same `evaluation.metrics.score_output`.
The gold additionally tags every must-remove surface with a `shape` and every identity
with a `kind` (name, identifier, address, birth), so the leaks can be grouped by the
layout that produced them. TOTAL is over the legal-document families; `narrativa` is
reported on its own row and kept out of TOTAL because it is not a document a client
uploads, only a measure of names that no layout announces.

The NER configuration runs on top of the default (first-name list on) with
`DeepMount00/Italian_NER_XXL_v2`, threshold 0.3, CPU. It runs only when the weights are
already in the Hugging Face cache; this script never downloads.
"""
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import regex as re  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pseudonimizzatore_legale import Config, anonymize          # noqa: E402
from pseudonimizzatore_legale import text as text_mod            # noqa: E402
from evaluation.metrics import score_output                      # noqa: E402

CORPUS = Path(__file__).resolve().parent / "corpus_documents"
STRESS = {"narrativa"}
NER_MODEL = "DeepMount00/Italian_NER_XXL_v2"
NER_OPTIONS = {"ner": NER_MODEL, "ner_threshold": 0.3, "ner_device": "cpu"}


def pct(ok, total):
    return 100 * ok / total if total else 0.0


def accumulate(counter, score):
    for field in score.__dataclass_fields__:
        if field not in {"leaked", "lost"}:
            counter[field] += getattr(score, field)


def ner_cached(model_id):
    """Whether the model's weights are already in the local Hugging Face cache."""
    try:
        from huggingface_hub import try_to_load_from_cache
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError as exc:
        return False, f"NER dependencies missing ({exc.name})"
    for name in ("model.safetensors", "pytorch_model.bin"):
        if isinstance(try_to_load_from_cache(model_id, name), str):
            return True, ""
    return False, f"{model_id} weights not in the Hugging Face cache"


def documents(only):
    for gold_path in sorted(CORPUS.rglob("*.gold.json")):
        family = gold_path.parent.name
        if only and family != only and only not in gold_path.name:
            continue
        yield family, gold_path


def run(label, overrides, docs, verbose, quiet):
    """Anonymize every document under one configuration and tally the metrics."""
    totals, per_family = Counter(), {}
    shape_total, kind_total, kind_ok = Counter(), Counter(), Counter()
    leaks, losses = [], []
    elapsed = 0.0
    if not quiet:
        print(f"\n=== {label} " + "=" * (120 - len(label)))
    for family, gold_path in docs:
        doc = gold_path.with_suffix("").with_suffix(".txt")
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        raw = doc.read_text(encoding="utf-8")
        cfg = Config(**{**gold.get("config", {}), **overrides})
        original = text_mod.sanitize(raw) if cfg.sanitize else raw
        original = text_mod.normalize_quotes(original)
        t0 = time.perf_counter()
        out, rep = anonymize(raw, cfg)
        elapsed += time.perf_counter() - t0
        score = score_output(original, out, gold, rep.replacement_spans)

        targets = [per_family.setdefault(family, Counter())]
        if family not in STRESS:
            targets.append(totals)
        for counter in targets:
            accumulate(counter, score)
            counter["docs"] += 1
            counter["clean_docs"] += not score.leaked
            counter["damage_free_docs"] += not score.lost
            counter["review_docs"] += rep.status == "needs_review"
        if family not in STRESS:
            if score.leaked and rep.status == "needs_review":
                totals["review_true_positive"] += 1
            elif score.leaked:
                totals["review_false_negative"] += 1
            elif rep.status == "needs_review":
                totals["review_false_positive"] += 1
            else:
                totals["review_true_negative"] += 1

        shapes = gold.get("shapes", {})
        if family not in STRESS:
            shape_total.update(shapes.values())
            for group in gold.get("must_remove_entities", []):
                kind_total[group["kind"]] += 1
                kind_ok[group["kind"]] += not set(group["values"]) & set(score.leaked)
        kind_of = {value: group.get("kind", "other")
                   for group in gold.get("must_remove_entities", [])
                   for value in group["values"]}
        doc_leaks = []
        for value in score.leaked:
            context = ""
            match = re.search(rf"(?<![\p{{L}}\p{{N}}]){re.escape(value)}(?![\p{{L}}\p{{N}}])", out)
            if match:
                context = out[max(0, match.start() - 60):match.end() + 40].replace("\n", " ⏎ ")
            doc_leaks.append((family, doc.stem, value, shapes.get(value, "?"),
                              kind_of.get(value, "?"), context))
        leaks += doc_leaks
        losses += [(family, doc.stem, value) for value in score.lost]

        if not quiet:
            status = "ok  " if not (score.leaked or score.lost) else "FAIL"
            review = " REVIEW" if rep.status == "needs_review" else ""
            print(f"{status} {family}/{doc.stem:40s} "
                  f"entities {score.entity_ok}/{score.entity_total}  "
                  f"surfaces {score.surface_ok}/{score.surface_total}  "
                  f"keep {score.keep_ok}/{score.keep_total}  "
                  f"({rep.replacements} subs){review}")
            for _, _, value, shape, _, context in doc_leaks:
                print(f"       LEAK not removed: {value!r} [{shape}]")
                if verbose:
                    print(f"             …{context}…")
            for value in score.lost:
                print(f"       LOST wrongly removed: {value!r}")

    return {"label": label, "totals": totals, "per_family": per_family, "leaks": leaks,
            "losses": losses, "seconds": elapsed, "shape_total": shape_total,
            "kind_total": kind_total, "kind_ok": kind_ok}


def row(name, score):
    return (f"{name:18s} "
            f"{score['entity_ok']:>4d}/{score['entity_total']:<4d} "
            f"{pct(score['entity_ok'], score['entity_total']):>6.1f}% "
            f"{score['surface_ok']:>4d}/{score['surface_total']:<4d} "
            f"{pct(score['surface_ok'], score['surface_total']):>6.1f}% "
            f"{score['prediction_ok']:>4d}/{score['prediction_total']:<4d} "
            f"{pct(score['prediction_ok'], score['prediction_total']):>6.1f}% "
            f"{score['keep_ok']:>4d}/{score['keep_total']:<4d} "
            f"{pct(score['keep_ok'], score['keep_total']):>6.1f}% "
            f"{score['clean_docs']:>4d}/{score['docs']:<4d} "
            f"{score['review_docs']:>4d}/{score['docs']:<4d}")


def report(result):
    """score_corpus.py's per-source table and summary, for one configuration."""
    print(f"\n{result['label']}  ({result['seconds']:.1f} s)")
    print("-" * 146)
    print(f"{'family':18s} {'entity recall':>20s} {'surface recall':>20s} "
          f"{'precision LB':>18s} {'kept':>18s} {'complete docs':>14s} {'review':>10s}")
    for family, score in sorted(result["per_family"].items()):
        if family not in STRESS:
            print(row(family, score))
    score = result["totals"]
    print(row("TOTAL", score))
    for family in sorted(STRESS & set(result["per_family"])):
        print(row(f"({family})", result["per_family"][family]))
    kinds = "  ".join(f"{kind} {result['kind_ok'][kind]}/{result['kind_total'][kind]}"
                      for kind in sorted(result["kind_total"]))
    print(
        f"\nComplete name entities:       {score['name_entity_ok']}/"
        f"{score['name_entity_total']} = "
        f"{pct(score['name_entity_ok'], score['name_entity_total']):.1f}%\n"
        f"Complete identifiers/other:   {score['identifier_entity_ok']}/"
        f"{score['identifier_entity_total']} = "
        f"{pct(score['identifier_entity_ok'], score['identifier_entity_total']):.1f}%\n"
        f"Complete entities by kind:    {kinds}\n"
        f"Partially removed entities:   {score['entity_partial']}\n"
        f"Completely missed entities:   {score['entity_missed']}\n"
        f"Gold-character precision LB:  {score['predicted_char_ok']}/"
        f"{score['predicted_char_total']} = "
        f"{pct(score['predicted_char_ok'], score['predicted_char_total']):.1f}%\n"
        f"Damage-free documents:        {score['damage_free_docs']}/{score['docs']}\n"
        f"Review heuristic (TP/FN/FP/TN): "
        f"{score['review_true_positive']}/{score['review_false_negative']}/"
        f"{score['review_false_positive']}/{score['review_true_negative']}\n"
        f"Review recall / precision:    "
        f"{pct(score['review_true_positive'], score['review_true_positive'] + score['review_false_negative']):.1f}% / "
        f"{pct(score['review_true_positive'], score['review_true_positive'] + score['review_false_positive']):.1f}%"
    )


def compare(results):
    """Shapes and collateral damage side by side across configurations."""
    labels = [r["label"] for r in results]
    width = max(len(label) for label in labels) + 2
    print("\n" + "=" * 146)
    print("Leaked surfaces by shape (legal documents; leaked/annotated per configuration)")
    print(f"{'shape':30s}" + "".join(f"{label:>{width}s}" for label in labels))
    shape_total = results[0]["shape_total"]
    leaked = [Counter(shape for family, _, _, shape, _, _ in r["leaks"] if family not in STRESS)
              for r in results]
    for shape in sorted(shape_total, key=lambda s: (-leaked[0][s], -shape_total[s], s)):
        if any(counter[shape] for counter in leaked):
            cells = "".join(f"{f'{counter[shape]}/{shape_total[shape]}':>{width}s}"
                            for counter in leaked)
            print(f"{shape:30s}{cells}")
    print(f"{'(shapes with no leak)':30s}"
          + "".join(f"{sum(shape_total[s] for s in shape_total if not c[s]):>{width}d}"
                    for c in leaked))

    for result in results:
        print(f"\nCollateral damage, {result['label']}: {len(result['losses'])} protected values lost")
        for family, stem, value in result["losses"]:
            print(f"   {family}/{stem:42s} {value!r}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    verbose = "-v" in sys.argv
    quiet = "--quiet" in sys.argv
    only = args[0] if args else None
    docs = list(documents(only))
    if not docs:
        sys.exit(f"no documents found (filter={only!r})")

    configs = [("default", {}), ("first_names=False", {"first_names": False})]
    if "--no-ner" in sys.argv:
        print("NER skipped (--no-ner).")
    else:
        cached, reason = ner_cached(NER_MODEL)
        if cached:
            configs.append(("default + NER XXL t=0.3", NER_OPTIONS))
        else:
            print(f"NER skipped: {reason}.")

    results = [run(label, overrides, docs, verbose, quiet) for label, overrides in configs]
    for result in results:
        report(result)
    compare(results)
    print(
        "\nPrecision LB counts only replacements overlapping an annotated must-remove "
        "span; unannotated true PII is conservatively counted against it.")


if __name__ == "__main__":
    main()
