"""Score the engine against the annotated corpus and print where it falls short.

This is a **measurement**, not a test suite: there is no pass/fail and no exit code to
gate on. Recall on real court documents is a number that moves, and the useful question
is "which shapes is it missing, and did that change?" — not "is it green?".

    python score_corpus.py                # every document, per-source totals
    python score_corpus.py cassazione     # one source
    python score_corpus.py -v             # show surrounding text for each leak

The primary metric is **entity recall**: every occurrence and spelling of an identity
must be gone or that entity fails. The historical surface-form recall and document
clean rate remain visible. Precision is a conservative lower bound because the corpus
does not exhaustively annotate ordinary non-sensitive text; `kept` remains the exact
sentinel for the protected values which are annotated.
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

import regex as re

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))
from pseudonimizzatore_legale import Config, anonymize          # noqa: E402
from pseudonimizzatore_legale import text as text_mod            # noqa: E402
from evaluation.metrics import score_output            # noqa: E402

CORPUS = Path(__file__).resolve().parent / "corpus"


def pct(ok, total):
    return 100 * ok / total if total else 0.0


def accumulate(counter, score):
    for field in score.__dataclass_fields__:
        if field not in {"leaked", "lost"}:
            counter[field] += getattr(score, field)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    verbose = "-v" in sys.argv
    only = args[0] if args else None

    totals = Counter()
    per_source = {}
    for gold_path in sorted(CORPUS.rglob("*.gold.json")):
        doc = gold_path.with_suffix("").with_suffix(".txt")
        # A source name selects that family exactly — "tar" is also a substring of
        # "tributario" — and anything else is matched against the corpus-relative path.
        rel = gold_path.relative_to(CORPUS)
        if only and (rel.parts[0] != only if (CORPUS / only).is_dir() else only not in str(rel)):
            continue
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        raw = doc.read_text(encoding="utf-8")
        cfg = Config(**gold.get("config", {}))
        original = text_mod.sanitize(raw) if cfg.sanitize else raw
        original = text_mod.normalize_quotes(original)
        out, rep = anonymize(raw, cfg)
        score = score_output(original, out, gold, rep.replacement_spans)
        accumulate(totals, score)
        totals["docs"] += 1
        totals["clean_docs"] += not score.leaked
        totals["damage_free_docs"] += not score.lost
        totals["review_docs"] += rep.status == "needs_review"
        if score.leaked and rep.status == "needs_review":
            totals["review_true_positive"] += 1
        elif score.leaked:
            totals["review_false_negative"] += 1
        elif rep.status == "needs_review":
            totals["review_false_positive"] += 1
        else:
            totals["review_true_negative"] += 1
        src = doc.parent.name
        source_score = per_source.setdefault(src, Counter())
        accumulate(source_score, score)
        source_score["docs"] += 1
        source_score["clean_docs"] += not score.leaked
        source_score["damage_free_docs"] += not score.lost
        source_score["review_docs"] += rep.status == "needs_review"

        status = "ok  " if not (score.leaked or score.lost) else "FAIL"
        review = " REVIEW" if rep.status == "needs_review" else ""
        print(f"{status} {src}/{doc.stem:38s} "
              f"entities {score.entity_ok}/{score.entity_total}  "
              f"surfaces {score.surface_ok}/{score.surface_total}  "
              f"keep {score.keep_ok}/{score.keep_total}  "
              f"({rep.replacements} subs, risk {rep.risk}){review}")
        for s_ in score.leaked:
            print(f"       LEAK not removed: {s_!r}")
            if verbose:
                m = re.search(re.escape(s_), out)
                if m:
                    print(f"             …{out[max(0,m.start()-60):m.end()+40]}…")
        for s_ in score.lost:
            print(f"       LOST wrongly removed: {s_!r}")

    print("\n" + "-" * 146)
    print(f"{'source':18s} {'entity recall':>20s} {'surface recall':>20s} "
          f"{'precision LB':>18s} {'kept':>18s} {'complete docs':>14s} {'review':>10s}")
    for src, score in sorted(per_source.items()):
        print(f"{src:18s} "
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
    score = totals
    print(f"{'TOTAL':18s} "
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
    print(
        f"\nComplete name entities:       {score['name_entity_ok']}/"
        f"{score['name_entity_total']} = "
        f"{pct(score['name_entity_ok'], score['name_entity_total']):.1f}%\n"
        f"Complete identifiers/other:   {score['identifier_entity_ok']}/"
        f"{score['identifier_entity_total']} = "
        f"{pct(score['identifier_entity_ok'], score['identifier_entity_total']):.1f}%\n"
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
        f"{pct(score['review_true_positive'], score['review_true_positive'] + score['review_false_positive']):.1f}%\n"
        "Precision LB counts only replacements overlapping an annotated must-remove "
        "span; unannotated true PII is conservatively counted against it."
    )


if __name__ == "__main__":
    main()
