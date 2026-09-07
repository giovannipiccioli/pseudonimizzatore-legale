"""What NER actually costs, measured end to end through `anonymize()`.

The number that matters is not tokens per second but **documents per hour**, because
that is what decides whether a corpus is a coffee break or a weekend. Everything here
runs the real public API on real documents, so the timings include sanitising,
the regex layer, span resolution and rendering — not just the forward pass.

    python throughput.py                     # shipped corpus, every device available
    python throughput.py --corpus /path/to/txt/archive
    python throughput.py --n 200 --device cpu
    python throughput.py --workers 8         # project a multi-process batch run

Models must already be in the Hugging Face cache.
"""
import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from pseudonimizzatore_legale import Config, anonymize          # noqa: E402

CORPUS = Path(__file__).resolve().parent.parent / "corpus"
DEFAULT_MODEL = "DeepMount00/Italian_NER_XXL_v2"


def load_documents(root: Path, n: int) -> list[str]:
    """A deterministic sample of UTF-8 documents below ``root``."""
    import random

    files = sorted(root.rglob("*.txt"))
    random.Random(0).shuffle(files)
    return [path.read_text(encoding="utf-8") for path in files[:n]]


def devices_to_try(requested: str | None) -> list[str | None]:
    if requested:
        return [requested]
    out: list[str | None] = ["cpu"]
    try:
        import torch
        if torch.backends.mps.is_available():
            out.append("mps")
        if torch.cuda.is_available():
            out.append("cuda")
    except ImportError:
        return []
    return out


def run(docs: list[str], cfg: Config) -> tuple[float, list[float]]:
    per_doc = []
    for text in docs:
        t0 = time.perf_counter()
        anonymize(text, cfg)
        per_doc.append(time.perf_counter() - t0)
    return sum(per_doc), per_doc


def report(label: str, total: float, per_doc: list[float], workers: int) -> None:
    n = len(per_doc)
    rate = n / total
    hours_1m = 1_000_000 / (rate * workers) / 3600
    print(f"{label:26s} {total / n * 1000:8.1f} ms/doc  "
          f"{statistics.median(per_doc) * 1000:8.1f} ms median  "
          f"{rate:7.1f} doc/s  →  1M docs in {hours_1m:6.1f} h"
          f"{f' ({workers} workers)' if workers > 1 else ''}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60, help="documents to time")
    ap.add_argument("--corpus", type=Path, default=CORPUS,
                    help="directory recursively containing UTF-8 .txt files")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--device", default=None, help="cpu | mps | cuda (default: all)")
    ap.add_argument("--workers", type=int, default=1,
                    help="processes assumed when projecting the 1M-document figure")
    args = ap.parse_args()

    docs = load_documents(args.corpus, args.n)
    if not docs:
        sys.exit("no documents found")
    chars = sum(len(d) for d in docs) / len(docs)
    print(f"{len(docs)} documents, {chars:,.0f} characters each on average\n")

    total, per_doc = run(docs, Config())
    report("regex only", total, per_doc, args.workers)
    baseline = total

    for device in devices_to_try(args.device):
        cfg = Config(ner=args.model, ner_device=device)
        try:
            anonymize(docs[0], cfg)                  # load the model outside the timing
        except Exception as exc:                     # noqa: BLE001 — report and move on
            print(f"{'NER ' + str(device):26s} unavailable: {exc}")
            continue
        total, per_doc = run(docs, cfg)
        report(f"NER on {device}", total, per_doc, args.workers)
        print(f"{'':26s} {total / baseline:8.0f}× slower than regex alone")


if __name__ == "__main__":
    main()
