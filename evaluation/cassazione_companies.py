"""Compare the three company policies on a reproducible Cassazione sample.

The script reads existing source corpora and writes diagnostics to
``/tmp/cassazione_companies_exploration.json``. It does not modify the corpora or
notebook outputs. The counts support manual review; they are not annotated accuracy
measurements.
"""
from __future__ import annotations

import collections
import json
import random
import re
import sys
import time
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SRC_ROOT / "anonymizer"))
sys.path.insert(0, str(SRC_ROOT))

from pseudonimizzatore_legale import Config, anonymize
from pseudonimizzatore_legale import patterns as P
from pseudonimizzatore_legale.text import sanitize
from utils.ilforo_omissis import replace_omissis

BASE = Path.home() / "Documents/trib_data_unzipped"
SOURCES = {
    "italgiure": "cassazione/cassazione_italgiure_txt_norm",
    "laleggepertutti": "cassazione/cassazione_laleggepertutti_txt_norm",
    "cerdef": "cerdef_giurisprudenza_txt",
    "ilforo_civ": "cassazione/cass_civ_txt_norm",
    "ilforo_pen": "cassazione/cass_pen_txt_norm",
}
YEARS = (2000, 2010, 2020, 2025)
PUBLIC_NAME = re.compile(
    r"\b(?:Agenzia\s+delle\s+Entrate(?:\s*[-–]\s*Riscossione)?|"
    r"Agenzia\s+delle\s+Dogane|Ministero\s+(?:dell[’']Economia|delle\s+Finanze|"
    r"della\s+Giustizia)|Comune\s+di\s+[A-ZÀ-Ü][a-zà-ü]+|"
    r"Equitalia(?:\s+(?:Nord|Sud|Esatri|Nomos))?|Poste\s+Italiane|"
    r"Avvocatura\s+Generale\s+dello\s+Stato|Azienda\s+Sanitaria\s+Locale|"
    r"INPS|I\.N\.P\.S\.|INAIL|I\.N\.A\.I\.L\.)",
    re.I,
)


def company_decisions(report):
    return [
        decision
        for decision in report.decisions
        if decision.kind == "ORGANIZATION" and decision.action == "redact"
    ]


def main() -> None:
    rng = random.Random(20260909)
    summaries = []
    named_examples = []
    broad_only_examples = []
    public_changes = []
    started = time.perf_counter()

    for source, folder in SOURCES.items():
        counts = collections.Counter()
        used_years = []
        for year in YEARS:
            files = sorted((BASE / folder / str(year)).glob("ECLI_IT_CASS_*.txt"))
            if not files:
                continue
            used_years.append(year)
            for path in rng.sample(files, min(20, len(files))):
                raw = path.read_text(encoding="utf-8")
                text = (
                    replace_omissis(raw, source="ilforo", court="cassazione")
                    if source.startswith("ilforo")
                    else raw
                )
                off, _ = anonymize(text, Config(companies=False))
                named, named_report = anonymize(
                    text, Config(companies="person_named")
                )
                broad, broad_report = anonymize(text, Config(companies=True))
                named_changes = company_decisions(named_report)
                broad_changes = company_decisions(broad_report)

                counts["files"] += 1
                counts["person_named_files"] += named != off
                counts["person_named_replacements"] += len(named_changes)
                counts["all_company_files"] += broad != off
                counts["all_company_replacements"] += len(broad_changes)
                counts["files_with_remaining_legal_forms"] += bool(
                    P.COMPANY_SUFFIX_RE.search(broad)
                )

                normalized = sanitize(text)
                public_phrases = {
                    match.group().casefold()
                    for match in PUBLIC_NAME.finditer(normalized)
                }
                counts["public_mentions_checked"] += len(
                    list(PUBLIC_NAME.finditer(normalized))
                )
                for phrase in public_phrases:
                    pattern = re.compile(
                        re.escape(phrase).replace(r"\ ", r"\s+"), re.I
                    )
                    lost = max(
                        0,
                        len(pattern.findall(off)) - len(pattern.findall(broad)),
                    )
                    if lost:
                        counts["public_mentions_lost"] += lost
                        public_changes.append(
                            {
                                "source": source,
                                "file": path.name,
                                "phrase": phrase,
                                "lost": lost,
                            }
                        )

                for decision in named_changes[:3]:
                    if len(named_examples) < 60:
                        named_examples.append(
                            {
                                "source": source,
                                "file": path.name,
                                "replaced": decision.text,
                            }
                        )
                named_spans = {
                    (decision.start, decision.end) for decision in named_changes
                }
                for decision in broad_changes:
                    if (
                        (decision.start, decision.end) not in named_spans
                        and len(broad_only_examples) < 60
                    ):
                        broad_only_examples.append(
                            {
                                "source": source,
                                "file": path.name,
                                "kept_by_person_named": decision.text,
                            }
                        )

        summary = {"source": source, "years": used_years, **counts}
        summaries.append(summary)
        print(summary, flush=True)

    result = {
        "seed": 20260909,
        "max_files_per_year": 20,
        "seconds": round(time.perf_counter() - started, 2),
        "summary": summaries,
        "person_named_examples": named_examples,
        "broad_only_examples": broad_only_examples,
        "public_changes": public_changes,
    }
    report_path = Path("/tmp/cassazione_companies_exploration.json")
    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Wrote {report_path} in {result['seconds']} seconds")
    print("PERSON NAMED", json.dumps(named_examples[:25], ensure_ascii=False))
    print("BROAD ONLY", json.dumps(broad_only_examples[:25], ensure_ascii=False))
    print("PUBLIC CHANGES", public_changes)


if __name__ == "__main__":
    main()
