"""Source-agnostic pipeline for pseudonimizzatore_legale.

The stages exchange candidates and decisions rather than editing text in sequence:

    normalize → detect → resolve identities → apply policy → render once → verify

Judicial roles are detected alongside private people. They become exact keep decisions
only in late policy, so a judge's surname cannot veto an unrelated party globally.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace

import regex as re

from . import patterns as P
from . import protect, seeds as seeds_mod, text as text_mod
from .config import Config
from .labels import Registry
from .model import (
    Candidate,
    Decision,
    Entity,
    EntityRecord,
    Mention,
    ResidualFinding,
    Verification,
)
from .policy import (
    PRI_ADDRESS,
    PRI_COMPANY,
    PRI_PERSON_FULL,
    PRI_PERSON_TOKEN,
    PRI_PROTECTED,
    PRI_STRUCTURED,
    resolve,
)
from .verification import verify

REPORT_SCHEMA_VERSION = 1


@dataclass
class Report:
    """Auditable result metadata for one document.

    Replacement/decision offsets refer to normalized input; residual offsets refer to
    returned output. When ``sanitize`` is true, normalized input differs from raw text.
    """

    mapping: dict[str, str] = field(default_factory=dict)
    protected: list[str] = field(default_factory=list)
    replacements: int = 0
    replacement_spans: list[tuple[int, int]] = field(default_factory=list)
    risk: float = 0.0
    schema_version: int = REPORT_SCHEMA_VERSION
    status: str = "not_run"
    residuals: list[ResidualFinding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    entity_records: list[EntityRecord] = field(default_factory=list)
    offset_space: str = "normalized_input"
    residual_offset_space: str = "output"

    @property
    def entities(self) -> int:
        """Number of distinct replacement tags emitted."""
        return len(set(self.mapping.values()))


def _first_group(match: re.Match) -> int:
    for index in range(1, (match.lastindex or 0) + 1):
        if match.group(index) is not None:
            return index
    return 0


def _candidate(
    text: str,
    start: int,
    end: int,
    *,
    kind: str,
    source: str,
    priority: int,
    role: str = "Nominativo",
    score: float = 1.0,
    full_name: bool = True,
    label: str | None = None,
    value: str | None = None,
    protection: str | None = None,
    reason: str = "",
) -> Candidate:
    return Candidate(
        mention=Mention(
            text=text[start:end],
            start=start,
            end=end,
            role=role,
            score=score,
            kind=kind,
            source=source,
            full_name=full_name,
        ),
        priority=priority,
        label=label,
        value=value,
        protection=protection,
        reason=reason,
    )


def _propose_protections(
    text: str,
    evidence,
    out: list[Candidate],
    conflicting_judges: set[tuple[str, ...]],
) -> None:
    for start, end in evidence.spans:
        protection = evidence.span_kinds[(start, end)]
        if protection == "judge":
            name = evidence.span_names[(start, end)]
            key = tuple(sorted(token.casefold() for token in name.split() if token))
            if key in conflicting_judges:
                continue
        kind = "JUDGE" if protection == "judge" else "CASE_NUMBER"
        out.append(_candidate(
            text,
            start,
            end,
            kind=kind,
            source=f"legal_role:{protection}",
            priority=PRI_PROTECTED,
            role="Giudice" if protection == "judge" else "Numero",
            protection=protection,
            reason=("explicit judicial-role evidence" if protection == "judge"
                    else "procedural identifier kept by policy"),
        ))


_PRIVATE_ROLE_SOURCES = {
    "regex:cf_adiacente",
    "regex:counsel",
    "regex:difeso_da",
    "regex:biografico",
    "regex:party_role",
    "regex:qualifica",
    "regex:proposto_da",
    "regex:nei_confronti",
    "regex:party_list",
    "regex:counsel_list",
    "regex:counsel_surname",
    "regex:legal_party_block",
}

# A broad ALL-CAPS party window can contain a prosecutor or judge mentioned before its
# terminator. It is useful detection evidence but not strong enough by itself to revoke
# an exact judicial-role keep decision.
_STRICT_PRIVATE_ROLE_SOURCES = _PRIVATE_ROLE_SOURCES - {"regex:legal_party_block"}
# A courtesy title names a person without saying which side they are on, and judges
# carry one as often as anybody: "Relatore … il dott. Andrea De Col" is the judge.
_NEUTRAL_SOURCES = frozenset({"regex:titolo"})
_COMPANY_INTRO = re.compile(
    r"(?i:(?:(?:di|del|della|dei|degli|delle|il|lo|la|le|gli|e)\s+)+)"
)


def _token_owners(entities: list[Entity], min_len: int) -> dict[str, list[Entity]]:
    owners: dict[str, list[Entity]] = defaultdict(list)
    for entity in entities:
        for token in seeds_mod.rare_tokens(entity.display, min_len):
            owners[token.casefold()].append(entity)
    return owners


def _propose_people(
    text: str,
    entities: list[Entity],
    cfg: Config,
    out: list[Candidate],
) -> None:
    """Propose full names, unique aliases, and conservative ambiguous aliases."""
    owners = _token_owners(entities, cfg.min_token_len)
    ambiguous = frozenset(token for token, values in owners.items() if len(values) > 1)

    for entity in entities:
        source = "+".join(sorted(entity.sources)) or "person"
        for pattern, is_full_name in seeds_mod.variant_patterns(
            entity,
            cfg.min_token_len,
            skip_tokens=ambiguous,
        ):
            priority = PRI_PERSON_FULL if is_full_name else PRI_PERSON_TOKEN
            for match in pattern.finditer(text):
                out.append(_candidate(
                    text,
                    match.start(),
                    match.end(),
                    kind="PERSON",
                    source=source,
                    priority=priority,
                    role=entity.role,
                    full_name=is_full_name,
                    label=entity.role,
                    value=entity.display,
                    reason=("resolved full-name alias" if is_full_name
                            else "unique distinctive alias"),
                ))

    # A surname owned by several detected people must still disappear, but assigning it
    # to one of them would be arbitrary. Use a neutral document-local entity instead.
    for token in sorted(ambiguous):
        pattern = re.compile(
            rf"(?<![\p{{L}}\p{{N}}]){re.escape(token)}(?![\p{{L}}\p{{N}}])",
            re.I,
        )
        for match in pattern.finditer(text):
            out.append(_candidate(
                text,
                match.start(),
                match.end(),
                kind="PERSON",
                source="alias:ambiguous",
                priority=PRI_PERSON_TOKEN,
                full_name=False,
                label="Nominativo",
                value=token,
                reason="alias belongs to multiple detected identities",
            ))


def _propose_structured(text: str, out: list[Candidate]) -> None:
    for label, pattern, group in P.STRUCTURED:
        for match in pattern.finditer(text):
            index = _first_group(match) if group else 0
            value = match.group(index)
            if not value:
                continue
            out.append(_candidate(
                text,
                match.start(index),
                match.end(index),
                kind=label.upper(),
                source=f"regex:{label.casefold()}",
                priority=PRI_STRUCTURED,
                role=label,
                label=label,
                value=value.strip(),
                reason="structured identifier",
            ))


def _propose_addresses(text: str, out: list[Candidate]) -> None:
    for match in P.INDIRIZZO_RESIDENZA.finditer(text):
        value = re.sub(r"\s+", " ", match.group(1)).strip()
        out.append(_candidate(
            text,
            match.start(1),
            match.end(1),
            kind="ADDRESS",
            source="regex:residential_address",
            priority=PRI_ADDRESS,
            role="Indirizzo",
            label="Indirizzo",
            value=value,
            reason="residential-address cue",
        ))


def _person_named_company_start(
    text: str,
    start: int,
    value: str,
) -> int | None:
    """Return the company start when its name has a strong personal-name signal."""
    suffix = next(
        (match for match in P.COMPANY_SUFFIX_RE.finditer(value)
         if match.end() == len(value)),
        None,
    )
    if suffix is None:
        return None
    name = value[:suffix.start()].strip()
    name = re.sub(r"(?i:^societ[àa]\s+)", "", name)
    if P.PERSON_NAMED_COMPANY_FAMILY.search(name):
        without_marker = P.PERSON_NAMED_COMPANY_FAMILY.sub("", name).strip()
        if re.search(P.NAME_TOKEN, without_marker):
            return start

    line_start = max(text.rfind("\n", 0, start) + 1, start - 100)
    context = text[line_start:start]
    for family in reversed(list(P.PERSON_NAMED_COMPANY_FAMILY.finditer(context))):
        bridge = context[family.end():]
        if not P.PERSON_NAMED_COMPANY_BRIDGE.fullmatch(bridge):
            continue
        if not re.search(P.NAME_TOKEN, f"{bridge} {name}"):
            continue
        company_start = line_start + family.start()
        prefix = P.PERSON_NAMED_COMPANY_PREFIX.search(context[:family.start()])
        if prefix:
            prefix_start = prefix.start()
            intro = _COMPANY_INTRO.match(prefix.group())
            if intro:
                prefix_start += intro.end()
            if prefix_start < family.start():
                company_start = line_start + prefix_start
        return company_start

    pair = P.PERSON_NAMED_COMPANY_PAIR.fullmatch(name)
    if pair and all(
        P.PERSON_NAMED_COMPANY_SURNAME_END.search(part)
        for part in pair.groups()
    ):
        return start
    return None


def _propose_companies(text: str, out: list[Candidate]) -> None:
    for match in P.SOCIETA.finditer(text):
        start = match.start(1)
        # Introductory articles/prepositions are prose, not part of the name.
        # Strip them before checking institutions as well: "della Equitalia ..."
        # must receive the same protection as "Equitalia ...".
        prefix = _COMPANY_INTRO.match(match.group(1))
        if prefix:
            start += prefix.end()
        value = re.sub(r"\s+", " ", text[start:match.end(1)]).strip()
        institution_name = re.sub(r"(?i:^societ[àa]\s+)", "", value)
        if P.INSTITUTION_HEAD.match(institution_name) or P.COMPANY_SUFFIX_RE.fullmatch(value):
            continue
        person_named_start = _person_named_company_start(text, start, value)
        if person_named_start is not None:
            start = person_named_start
            value = re.sub(r"\s+", " ", text[start:match.end(1)]).strip()
        out.append(_candidate(
            text,
            start,
            match.end(1),
            kind="ORGANIZATION",
            source=("regex:person_named_company" if person_named_start is not None
                    else "regex:private_company"),
            priority=PRI_COMPANY,
            role="Società",
            label="Società",
            value=value,
            reason=("private company with a strong personal-name signal"
                    if person_named_start is not None else "private company"),
        ))


def _allocate_replacements(decisions: list[Decision]) -> tuple[list[Decision], Registry]:
    """Allocate tags only for accepted redactions, in document order."""
    registry = Registry()
    allocated: list[Decision] = []
    for decision in decisions:
        if decision.action == "keep":
            allocated.append(decision)
            continue
        label = decision.label or decision.role or "Nominativo"
        value = decision.value or decision.text
        tag = registry.tag(label, value)
        allocated.append(replace(decision, replacement=tag, entity_id=tag))
    return allocated, registry


def _render(
    text: str,
    decisions: list[Decision],
) -> tuple[str, list[tuple[int, int]], list[tuple[int, int]]]:
    """Apply accepted decisions once and return normalized/output audit offsets."""
    parts: list[str] = []
    cursor = 0
    output_length = 0
    replacements: list[tuple[int, int]] = []
    protected_output: list[tuple[int, int]] = []

    for decision in decisions:
        before = text[cursor:decision.start]
        parts.append(before)
        output_length += len(before)
        if decision.action == "keep":
            parts.append(decision.text)
            protected_output.append((output_length, output_length + len(decision.text)))
            output_length += len(decision.text)
        else:
            replacement = decision.replacement or "Nominativo"
            parts.append(replacement)
            output_length += len(replacement)
            replacements.append((decision.start, decision.end))
        cursor = decision.end

    tail = text[cursor:]
    parts.append(tail)
    return "".join(parts), replacements, protected_output


def _entity_records(decisions: list[Decision]) -> list[EntityRecord]:
    grouped: dict[str, list[Decision]] = defaultdict(list)
    for decision in decisions:
        if decision.action == "redact" and decision.entity_id:
            key = decision.entity_id
        else:
            key = f"kept:{decision.kind}:{decision.text.casefold()}"
        grouped[key].append(decision)

    records = []
    for entity_id, items in grouped.items():
        first = items[0]
        records.append(EntityRecord(
            entity_id=entity_id,
            kind=first.kind,
            role=first.role,
            action=first.action,
            aliases=tuple(sorted({item.text for item in items}, key=str.casefold)),
            sources=tuple(sorted({item.source for item in items})),
        ))
    return records


def _expected_aliases(entities: list[Entity], decisions: list[Decision], cfg: Config) -> set[str]:
    redacted = {
        (decision.label, (decision.value or "").casefold())
        for decision in decisions
        if decision.action == "redact"
    }
    aliases: set[str] = set()
    for entity in entities:
        if (entity.role, entity.display.casefold()) not in redacted:
            continue
        for value in entity.variants | {entity.display}:
            aliases.update(seeds_mod.name_orders(value))
        aliases.update(seeds_mod.rare_tokens(entity.display, cfg.min_token_len))
    return aliases


def _role_conflicts(entities: list[Entity], evidence) -> list[str]:
    warnings = []
    for entity in entities:
        if evidence.matches_identity(entity.display) and entity.sources & _PRIVATE_ROLE_SOURCES:
            warnings.append(
                f"conflicting judicial/private-role evidence for {entity.display!r}"
            )
    return warnings


def _conflicting_judges(entities: list[Entity], evidence) -> set[tuple[str, ...]]:
    """Judicial identities also supported by an explicit private-role detector."""
    return {
        entity.key
        for entity in entities
        if evidence.matches_identity(entity.display)
        and entity.sources & _STRICT_PRIVATE_ROLE_SOURCES
    }


def residual_risk(anonymized: str, report: Report) -> float:
    """Compatibility triage score; prefer the more explicit ``Report.status``."""
    score = 0.0
    if report.residuals:
        score = max(score, 0.7)
    if report.warnings:
        score = max(score, 0.5)
    if P.CODICE_FISCALE.search(anonymized) or P.EMAIL.search(anonymized):
        score = max(score, 0.9)
    return round(score, 3)


def anonymize(raw: str, config: Config | None = None, **overrides) -> tuple[str, Report]:
    """Pseudonymize one Italian legal document.

    Returns ``(text, report)``. Policy comes from either a ``Config`` or keyword
    overrides, never both.

    >>> out, report = anonymize("Il sig. Mario Rossi, C.F. RSSMRA80A01H501U, ricorre.")
    >>> "Mario Rossi" in out
    False
    >>> report.mapping["RSSMRA80A01H501U"]
    'CF_1'
    """
    if config is not None and overrides:
        raise TypeError("pass either `config` or keyword overrides, not both")
    cfg = config if config is not None else Config(**overrides)

    text = text_mod.sanitize(raw) if cfg.sanitize else raw
    text = text_mod.normalize_quotes(text)

    protection_evidence = protect.collect(text)
    people = seeds_mod.collect(text, cfg)
    if cfg.keep_judges:
        # An identity found only through a title, which also carries judicial evidence,
        # is that judge. Seeding it would replace every mention, the bench list included.
        people = [person for person in people
                  if not (person.sources <= _NEUTRAL_SOURCES
                          and protection_evidence.matches_identity(person.display))]

    candidates: list[Candidate] = []
    _propose_protections(
        text,
        protection_evidence,
        candidates,
        _conflicting_judges(people, protection_evidence),
    )
    _propose_people(text, people, cfg, candidates)
    _propose_structured(text, candidates)
    _propose_addresses(text, candidates)
    _propose_companies(text, candidates)

    accepted = resolve(candidates, len(text), cfg)
    accepted, registry = _allocate_replacements(accepted)
    output, replacement_spans, protected_output = _render(text, accepted)

    warnings = _role_conflicts(people, protection_evidence)
    aliases = _expected_aliases(people, accepted, cfg)
    if cfg.verify:
        verification = verify(
            output,
            protected_spans=protected_output,
            expected_aliases=aliases,
            replacements=len(replacement_spans),
            warnings=warnings,
        )
    else:
        verification = Verification(status="not_run", warnings=tuple(warnings))

    protected_names = sorted({
        decision.text
        for decision in accepted
        if decision.action == "keep" and decision.kind == "JUDGE"
    })
    report = Report(
        mapping=registry.mapping(),
        protected=protected_names,
        replacements=len(replacement_spans),
        replacement_spans=replacement_spans,
        status=verification.status,
        residuals=list(verification.residuals),
        warnings=list(verification.warnings),
        decisions=accepted,
        entity_records=_entity_records(accepted),
    )
    report.risk = residual_risk(output, report)
    return output, report
