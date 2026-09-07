"""Build a domain-common-word list from an arbitrary Italian legal corpus."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import random

import regex as re


TOKEN = re.compile(r"[\p{L}][\p{L}'’]+")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="directory recursively containing .txt files")
    parser.add_argument("--documents", type=int, default=3000)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "pseudonimizzatore_legale/resources/common_words.json",
    )
    args = parser.parse_args()

    files = sorted(args.root.rglob("*.txt"))
    random.Random(11).shuffle(files)
    files = files[:args.documents]
    if not files:
        raise SystemExit(f"no .txt documents found under {args.root}")

    lengths: list[int] = []
    frequency: Counter[str] = Counter()
    for path in files:
        raw = path.read_text(encoding="utf-8")
        if len(raw) < 400 or "Server Error" in raw[:200]:
            continue
        lengths.append(len(raw))
        frequency.update({match.group(0).casefold() for match in TOKEN.finditer(raw)})

    if not lengths:
        raise SystemExit("no usable documents found")
    threshold = max(3, int(len(lengths) * 0.02))
    common = sorted(word for word, count in frequency.items() if count >= threshold)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(common, ensure_ascii=False) + "\n", encoding="utf-8")

    lengths.sort()
    percentile = lambda value: lengths[min(len(lengths) - 1, int(len(lengths) * value))]
    print(f"documents: {len(lengths)}")
    print(
        f"characters: p10={percentile(.10):,}, median={percentile(.50):,}, "
        f"p90={percentile(.90):,}, max={lengths[-1]:,}"
    )
    print(f"common words: {len(common):,} (document frequency >= {threshold})")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
