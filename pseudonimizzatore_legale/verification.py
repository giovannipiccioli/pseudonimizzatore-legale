"""Review-oriented residual checks over pseudonymized output.

These checks never rewrite text and never claim that a document is safe.
``passed_checks`` means only that these inexpensive heuristics found nothing;
``needs_review`` identifies a higher-priority manual-review candidate.
"""
from __future__ import annotations

from collections.abc import Iterable

import regex as re

from . import patterns as P
from .model import ResidualFinding, Verification


_PRIVATE_PERSON_CUE = re.compile(
    rf"(?i:\b(?:contribuente|ricorrente|controricorrente|resistente|appellante|"
    rf"appellato|imputato|indagato|convenuto|attore|opponente|istante|debitore|"
    rf"creditore|erede|testimone|persona\s+fisica)\b)"
    rf"[\s,:;-]{{1,20}}(?:[dD]ott\.?(?:ssa)?\s+|[sS]ig\.?(?:ra)?\s+)?"
    rf"({P.FULL_NAME})"
)

_ALREADY_ANONYMIZED = re.compile(
    r"\(?[Oo]missis\)?|\bOMISSIS\b|\b\p{Lu}\.\s?\p{Lu}\.(?:\s?\p{Lu}\.)?"
    r"(?![\p{L}])"
)

_POSSIBLE_PERSON = re.compile(
    rf"(?<![\p{{L}}'’])({P.FULL_NAME})(?![\p{{L}}'’])"
)


def _contained(span: tuple[int, int], protected: Iterable[tuple[int, int]]) -> bool:
    start, end = span
    return any(other_start <= start and end <= other_end
               for other_start, other_end in protected)


def _whole_value(value: str) -> re.Pattern:
    return re.compile(
        rf"(?<![\p{{L}}\p{{N}}]){re.escape(value)}(?![\p{{L}}\p{{N}}])",
        re.I,
    )


def verify(
    output: str,
    *,
    protected_spans: Iterable[tuple[int, int]] = (),
    expected_aliases: Iterable[str] = (),
    replacements: int = 0,
    warnings: Iterable[str] = (),
) -> Verification:
    """Return residual findings in output coordinates without modifying ``output``."""
    protected = tuple(protected_spans)
    findings: dict[tuple[int, int, str], ResidualFinding] = {}

    def add(start: int, end: int, kind: str, source: str, reason: str) -> None:
        # Only a person finding wholly inside an accepted public-role span is exempt.
        # Structured PII must never be hidden by partial overlap with a kept case id.
        if kind == "PERSON" and _contained((start, end), protected):
            return
        text = output[start:end]
        if not text or re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ]+_\d+", text):
            return
        findings[(start, end, kind)] = ResidualFinding(
            start=start,
            end=end,
            text=text,
            kind=kind,
            source=source,
            reason=reason,
        )

    # Structured detectors are deterministic and independent of person seeding.
    for label, pattern, group in P.STRUCTURED:
        for match in pattern.finditer(output):
            index = 1 if group and match.lastindex else 0
            if group and match.lastindex:
                index = next(
                    (i for i in range(1, match.lastindex + 1)
                     if match.group(i) is not None),
                    0,
                )
            add(match.start(index), match.end(index), label.upper(),
                "verification:structured", f"residual {label}")

    # Deliberately broader than the conservative primary regex seeder.
    for match in _PRIVATE_PERSON_CUE.finditer(output):
        value = match.group(1)
        if P.INSTITUTION_HEAD.search(value) or P.ORG_HEAD.search(value):
            continue
        tokens = [token.casefold().strip(".,;:") for token in value.split()]
        if value.isupper() and any(
            token in P.SECTION_HEADING_TOKENS for token in tokens
        ):
            continue
        add(match.start(1), match.end(1), "PERSON", "verification:private-role",
            "person-like text remains after a private-party cue")

    # Review-only high-recall scan. Unlike the primary seeder it needs no legal cue:
    # any remaining 2–4-token capitalized phrase is surfaced for inspection. This
    # intentionally accepts false alarms; it never rewrites text.
    for match in _POSSIBLE_PERSON.finditer(output):
        value = match.group(1)
        if _ALREADY_ANONYMIZED.search(value):
            continue
        # FULL_NAME stops at the underscore in a generated tag and can otherwise read
        # "La Ricorrente_1" as the two-token name "La Ricorrente".
        if re.match(r"_\d+", output[match.end(1):]):
            continue
        if (P.INSTITUTION_HEAD.search(value) or P.ORG_HEAD.search(value)
                or P.COMPANY_SUFFIX_RE.search(value) or P.STREET_HEAD.match(value)):
            continue
        tokens = [token.casefold().strip(".,;:") for token in value.split()]
        if value.isupper() and any(
            token in P.SECTION_HEADING_TOKENS for token in tokens
        ):
            continue
        add(match.start(1), match.end(1), "PERSON", "verification:name-shape",
            "unresolved capitalized name candidate")

    # A known entity alias surviving the rewrite is always worth review. Exact judicial
    # spans are excluded above, which handles a party sharing a surname with a judge.
    for alias in sorted(set(expected_aliases), key=len, reverse=True):
        if len(alias.strip()) < 3:
            continue
        for match in _whole_value(alias).finditer(output):
            add(match.start(), match.end(), "PERSON", "verification:alias",
                "alias of an entity selected for redaction remains")

    words = output.count(" ") + 1
    pre_anonymized = len(_ALREADY_ANONYMIZED.findall(output)) >= 3
    if words > 300 and replacements == 0 and not pre_anonymized:
        findings[(0, 0, "DOCUMENT")] = ResidualFinding(
            start=0,
            end=0,
            text="",
            kind="DOCUMENT",
            source="verification:coverage",
            reason="long document contains no detected removable entity",
        )

    warning_tuple = tuple(dict.fromkeys(warnings))
    residuals = tuple(sorted(findings.values(), key=lambda item: (item.start, item.end)))
    status = "needs_review" if residuals or warning_tuple else "passed_checks"
    return Verification(status=status, residuals=residuals, warnings=warning_tuple)
