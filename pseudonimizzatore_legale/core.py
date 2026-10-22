"""Source-agnostic pipeline for pseudonimizzatore_legale.

The stages exchange candidates and decisions rather than editing text in sequence:

    normalize → detect → resolve identities → apply policy → render once → verify

Judicial roles are detected alongside private people. They become exact keep decisions
only in late policy, so a judge's surname cannot veto an unrelated party globally.

`anonymize` is `render(analyze(...))`. A review tool calls the two halves itself and
feeds a reviewer's corrections back in as `Edits`, which enter the same pipeline as
one more detector: a person the reviewer adds is folded, propagated and tagged exactly
like one found automatically.

>>> doc = "Il sig. Mario Rossi ricorre. Sentito il teste Zappacosta."
>>> analysis = analyze(doc)
>>> [(row.entity_id, row.aliases, row.spans) for row in analysis.entities]
[('Nominativo_1', ('Mario Rossi',), ((8, 19),))]
>>> edits = Edits(people=(("Zappacosta", "Nominativo"),),
...               prior_tags=tuple(analysis.mapping.items()))
>>> render(analyze(doc, edits=edits))[0]
'Il sig. Nominativo_1 ricorre. Sentito il teste Nominativo_2.'
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
    PRI_USER,
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


@dataclass(frozen=True)
class Edits:
    """A reviewer's corrections, replayed on every analysis of the same document.

    Every field names text, never an internal id, so the edits still apply after the
    document is analysed again. An *alias* is any spelling of an entity in the text,
    or its value in `Analysis.mapping`. Spans are offsets into `normalize(raw)`.

    people
        ``(surface, role)``: a person detection missed. No seed guard refuses it, and
        it folds, propagates and shares surnames like any detected person. A judge
        added here is redacted. The role shows in the tag only with ``roles=True``.
    terms
        ``(surface, label)``: other data to redact wherever it occurs, any case.
    exclude
        ``alias``: stop redacting that entity. A surname it shares with another person
        stays redacted under its neutral tag.
    keep_spans
        ``(start, end)``: leave this occurrence in clear. Unlike a judge, verification
        still reports it.
    include_spans
        ``(start, end, alias)``: redact this occurrence as that entity.
    merge
        ``(alias_from, alias_to)``: the first entity takes the second one's tag.
    placeholders
        ``(alias, tag)``: a custom tag for that entity.
    prior_tags
        The items of a previous `Analysis.mapping`, so tags do not renumber between
        edits.
    """

    people: tuple[tuple[str, str], ...] = ()
    terms: tuple[tuple[str, str], ...] = ()
    exclude: tuple[str, ...] = ()
    keep_spans: tuple[tuple[int, int], ...] = ()
    include_spans: tuple[tuple[int, int, str], ...] = ()
    merge: tuple[tuple[str, str], ...] = ()
    placeholders: tuple[tuple[str, str], ...] = ()
    prior_tags: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Analysis:
    """Everything decided about one document, before it is rewritten.

    ``text`` is the normalized input, and every offset refers to it. ``entities`` are
    the review-panel rows: one per tag, or per kept spelling, with all their spans.
    """

    text: str
    config: Config
    decisions: tuple[Decision, ...]
    entities: tuple[EntityRecord, ...]
    mapping: dict[str, str]
    expected_aliases: frozenset[str]
    warnings: tuple[str, ...]


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
# an exact judicial-role keep decision. A person the reviewer adds is, on their word.
_STRICT_PRIVATE_ROLE_SOURCES = _PRIVATE_ROLE_SOURCES - {"regex:legal_party_block"} | {"user"}
# A courtesy title names a person without saying which side they are on, and judges
# carry one as often as anybody: "Relatore … il dott. Andrea De Col" is the judge.
_NEUTRAL_SOURCES = frozenset({"regex:titolo", "regex:titolo_solo", "lexicon:first_name"})
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


#: A salutation right before a first name: "Caro Paolo", unlike "BIANCHI PAOLO", is not
#: the end of someone else's surname-first name.
_SALUTATION_BEFORE = re.compile(
    r"(?<![\p{L}])(?i:car[oa]|carissim[oa]|gentil(?:e|issim[oa])|ciao|dear|hi)[^\S\n]+$")


def _propose_given_names(
    text: str,
    entities: list[Entity],
    cfg: Config,
    out: list[Candidate],
) -> None:
    """Propose the first name alone of a detected person, where it is a common word.

    A rare first name ("Ferruccio") already propagates as a distinctive token. A common
    one ("Paolo", "Luca", "Marcello") does not, so "Caro Paolo," after "Egr. Avv. Paolo
    Gennari", a letter signed "Luca" by "Avv. Luca Veronesi", or "per Rosalba e
    Marcello" after the heirs' list stayed in clear. Conservatively:

    * the name must be a listed first name and belong to exactly one detected person;
    * it is matched case-sensitively, as capitalised, ALL-CAPS or as that person's
      variants spell it ("francesca" in an e-mail);
    * it may not follow a street word or a saint ("Via Paolo Sarpi", "San Paolo"), nor
      sit next to another capitalised name token, which would make it part of someone
      else's full name ("Paolo Rossi", "BIANCHI PAOLO").
    """
    listed = seeds_mod.first_names()
    owners: dict[str, list[Entity]] = defaultdict(list)
    for entity in entities:
        distinctive = {token.casefold()
                       for token in seeds_mod.rare_tokens(entity.display, cfg.min_token_len)}
        for token in {token.casefold() for token in entity.display.split()}:
            if token in listed and token not in distinctive:
                owners[token].append(entity)

    for name, entities_with_name in sorted(owners.items()):
        if len(entities_with_name) != 1:
            continue
        entity = entities_with_name[0]
        forms = {name.capitalize(), name.upper()} | {
            token for variant in entity.variants for token in variant.split()
            if token.casefold() == name}
        pattern = re.compile(
            r"(?<![\p{L}\p{N}'’])(?:" + "|".join(map(re.escape, sorted(forms))) +
            r")(?![\p{L}\p{N}'’])")
        for match in pattern.finditer(text):
            before = text[max(0, match.start() - 40):match.start()]
            if P.NAMED_PLACE_BEFORE.search(before):
                continue                        # "Via Paolo Sarpi", "San Paolo"
            if re.match(rf"[^\S\n]+{P.NAME_TOKEN}", text[match.end():match.end() + 40]):
                continue                        # "Paolo Rossi"
            if (re.search(rf"{P.NAME_TOKEN}[^\S\n]+$", before)
                    and not _SALUTATION_BEFORE.search(before)):
                continue                        # "BIANCHI PAOLO", but not "Caro Paolo"
            out.append(_candidate(
                text,
                match.start(),
                match.end(),
                kind="PERSON",
                source="+".join(sorted(entity.sources)) + "+given_name",
                priority=PRI_PERSON_TOKEN,
                role=entity.role,
                full_name=False,
                label=entity.role,
                value=entity.display,
                reason="first name of a detected person",
            ))


def _propose_structured(text: str, out: list[Candidate]) -> None:
    for label, pattern, group in P.STRUCTURED:
        for match in pattern.finditer(text):
            index = _first_group(match) if group else 0
            value = match.group(index)
            if not value or not P.STRUCTURED_CHECKS.get(label, bool)(value.strip()):
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


def _public_block(text: str, start: int) -> bool:
    """Whether the address line at `start` closes a block that names a public body or
    a company: "Spett.le⏎Agenzia delle Entrate⏎Direzione Provinciale di Torino⏎Corso
    Bolzano 30, 10121 Torino" is the Agency's address. The block runs back to the
    previous blank line."""
    head = re.split(r"\n[^\S\n]*\n", text[max(0, start - 300):start])[-1]
    return bool(P.INSTITUTION_HEAD.search(head) or P.COMPANY_SUFFIX_RE.search(head))


#: (pattern, source, reason) for each address rule; group 1 is the address.
_ADDRESS_RULES = (
    (P.INDIRIZZO_RESIDENZA, "regex:residential_address",
     "residence, domicile, studio or property cue"),
    (P.INDIRIZZO_STUDIO_DOPO, "regex:studio_address", "notarial studio address"),
    (P.INDIRIZZO_RIGA, "regex:address_line",
     "address line of a letterhead, signature or addressee block"),
)


def _propose_addresses(text: str, out: list[Candidate]) -> None:
    for pattern, source, reason in _ADDRESS_RULES:
        for match in pattern.finditer(text):
            start, end = match.span(1)
            # A public body elects domicile at the Avvocatura dello Stato's offices
            # ("…, domiciliata in Roma, via dei Portoghesi 12, presso l'Avvocatura
            # generale"), and a party may be domiciled by statute at the court's own
            # office ("presso la Segreteria del Tar Lazio in Roma, via Flaminia, 189"):
            # public addresses, like a registered office. Look a little either side,
            # without crossing the semicolon that closes a party's clause.
            before = text[max(0, match.start() - 80):match.start()].rsplit(";", 1)[-1]
            after = text[end:end + 60].split(";", 1)[0]
            if re.search(r"(?i:avvocatura|(?:segreteria|cancelleria)\s+d)",
                         before + match.group(0) + after):
                continue
            # A property cue after a public body is that body's seat: "il Tribunale,
            # sito in …".
            if pattern is P.INDIRIZZO_RESIDENZA and P.PROPERTY_CUE.match(match.group(0)):
                head = text[max(0, match.start() - 40):match.start()]
                if P.INSTITUTION_HEAD.search(head) or P.COMPANY_SUFFIX_RE.search(head):
                    continue
            if pattern is P.INDIRIZZO_RIGA and _public_block(text, start):
                continue
            out.append(_candidate(
                text,
                start,
                end,
                kind="ADDRESS",
                source=source,
                priority=PRI_ADDRESS,
                role="Indirizzo",
                label="Indirizzo",
                value=re.sub(r"\s+", " ", match.group(1)).strip(),
                reason=reason,
            ))


def _propose_places(text: str, out: list[Candidate]) -> None:
    """Birthplace and residence towns, only in their biographic slot."""
    comuni = seeds_mod.comuni()
    for match in P.LUOGO_BIOGRAFICO.finditer(text):
        words = list(re.finditer(r"\S+", match.group(1)))
        length = next((word.end() for word in reversed(words)       # longest prefix
                       if seeds_mod.place_key(match.group(1)[:word.end()]) in comuni),
                      None)                                         # that is a comune
        # A foreign birthplace, followed by its country in brackets ("nato a Wenzhou
        # (Repubblica Popolare Cinese)"). Two capitals are an Italian province instead.
        country = match.group(2)
        if (length is None and country and match.group(0)[:3].casefold() == "nat"
                and re.fullmatch(r"\p{Lu}[\p{L}'’]+(?:\s+\p{L}[\p{L}'’]+){0,3}", country)
                and not re.fullmatch(r"\p{Lu}{2}", country)):
            length = len(match.group(1))
        if length is not None:
            out.append(_candidate(
                text,
                match.start(1),
                match.start(1) + length,
                kind="PLACE",
                source="regex:place",
                priority=PRI_ADDRESS,
                role="Luogo",
                label="Luogo",
                value=match.group(1)[:length],
                reason="birthplace or residence town",
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


def _fold(value: str) -> str:
    return " ".join(value.split()).casefold()


def _key(candidate: Candidate) -> tuple[str | None, str]:
    """The entity a candidate redacts, as tag allocation keys it."""
    return candidate.label, (candidate.value or "").casefold()


def _owner(candidates: list[Candidate], alias: str) -> Candidate | None:
    """A redaction candidate of the entity that `alias` names."""
    alias = _fold(alias)
    return next((
        candidate for candidate in candidates
        if candidate.protection is None
        and candidate.mention.source != "alias:ambiguous"
        and alias in (_fold(candidate.mention.text), _fold(candidate.value or ""))
    ), None)


def _apply_edits(text: str, candidates: list[Candidate], edits: Edits):
    """Turn reviewer edits into candidates, plus what tag allocation needs.

    Returns the candidates, the merged entity keys ``{from: to}`` and the custom tags.
    Edits outrank every detector (`PRI_USER`); at equal priority and length the earlier
    candidate wins, so a keep is listed before a term or an include on the same span.
    """
    keeps = [
        _candidate(text, start, end, kind="USER", source="user:keep", priority=PRI_USER,
                   role="Utente", protection="user", reason="kept by the reviewer")
        for start, end in edits.keep_spans
    ]
    pool = list(candidates)
    for surface, label in edits.terms:
        if not surface.split():
            continue
        literal = r"\s+".join(re.escape(token) for token in surface.split())
        pattern = re.compile(rf"(?<![\p{{L}}\p{{N}}]){literal}(?![\p{{L}}\p{{N}}])", re.I)
        pool.extend(
            _candidate(text, match.start(), match.end(), kind=label.upper(),
                       source="user:term", priority=PRI_USER, role=label, label=label,
                       value=surface, reason="term added by the reviewer")
            for match in pattern.finditer(text)
        )

    merges: dict[tuple, tuple] = {}
    for alias_from, alias_to in edits.merge:
        source, target = _owner(pool, alias_from), _owner(pool, alias_to)
        if source is None or target is None or _key(source) == _key(target):
            continue
        pool = [
            replace(candidate, label=target.label, value=target.value,
                    mention=replace(candidate.mention, role=target.mention.role))
            if _key(candidate) == _key(source) else candidate
            for candidate in pool
        ]
        merges = {old: _key(target) if new == _key(source) else new
                  for old, new in merges.items()}
        merges[_key(source)] = _key(target)

    includes = []
    for start, end, alias in edits.include_spans:
        owner = _owner(pool, alias)
        includes.append(_candidate(
            text, start, end,
            kind=owner.mention.kind if owner else "PERSON",
            source="user:include",
            priority=PRI_USER,
            role=owner.mention.role if owner else "Nominativo",
            label=owner.label if owner else "Nominativo",
            value=owner.value if owner else alias,
            reason="occurrence added by the reviewer",
        ))
    custom = {_key(owner): tag for alias, tag in edits.placeholders
              if (owner := _owner(pool, alias))}

    # A surname shared with another person is not this entity's to give back.
    excluded = {_key(owner) for alias in edits.exclude if (owner := _owner(pool, alias))}
    pool = [candidate for candidate in pool
            if _key(candidate) not in excluded
            or candidate.mention.source == "alias:ambiguous"]
    return keeps + pool + includes, merges, custom


def _allocate_replacements(
    decisions: list[Decision],
    custom: dict[tuple, str] | None = None,
    prior: dict[str, str] | None = None,
    roles: bool = True,
) -> tuple[list[Decision], Registry]:
    """Allocate tags only for accepted redactions, in document order.

    Without `roles` every person is tagged ``Nominativo``; the decision keeps its role.
    """
    registry = Registry(prior)
    custom = custom or {}
    allocated: list[Decision] = []
    for decision in decisions:
        if decision.action == "keep":
            allocated.append(decision)
            continue
        label = decision.label or decision.role or "Nominativo"
        value = decision.value or decision.text
        fixed = custom.get((label, value.casefold()))
        if not roles and decision.kind == "PERSON":
            label = "Nominativo"
        tag = registry.tag(label, value, fixed)
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
            # A reviewer's keep is a choice, not evidence that the text is public:
            # verification must still see it.
            if decision.kind != "USER":
                protected_output.append(
                    (output_length, output_length + len(decision.text)))
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
            aliases=tuple(sorted({item.text for item in items},
                                 key=lambda alias: (alias.casefold(), alias))),
            sources=tuple(sorted({item.source for item in items})),
            spans=tuple((item.start, item.end) for item in items),
        ))
    return records


def _expected_aliases(
    entities: list[Entity],
    decisions: list[Decision],
    cfg: Config,
    merges: dict[tuple, tuple] | None = None,
) -> set[str]:
    redacted = {
        (decision.label, (decision.value or "").casefold())
        for decision in decisions
        if decision.action == "redact"
    }
    merges = merges or {}
    aliases: set[str] = set()
    for entity in entities:
        key = (entity.role, entity.display.casefold())
        if merges.get(key, key) not in redacted:
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
    if (any(P.codice_fiscale_ok(m.group()) for m in P.CODICE_FISCALE.finditer(anonymized))
            or any(not P.public_mailbox(m.group()) for m in P.EMAIL.finditer(anonymized))):
        score = max(score, 0.9)
    return round(score, 3)


def normalize(raw: str, config: Config | None = None) -> str:
    """The text every offset refers to: ``raw`` sanitized (unless disabled), quotes folded.

    Run an external NER on this text, not on ``raw``, so its mentions line up.

    >>> normalize("**Mario** D’Angelo")
    "Mario D'Angelo"
    """
    cfg = config if config is not None else Config()
    text = text_mod.sanitize(raw) if cfg.sanitize else raw
    return text_mod.normalize_quotes(text)


def analyze(
    raw: str,
    config: Config | None = None,
    *,
    edits: Edits = Edits(),
    mentions: tuple[Mention, ...] = (),
) -> Analysis:
    """Detect, resolve and tag one document without rewriting it.

    ``mentions`` are person mentions from a NER run on ``normalize(raw, config)``, one
    more seed source. ``edits`` are a reviewer's corrections (see `Edits`).
    """
    cfg = config if config is not None else Config()
    text = normalize(raw, cfg)

    protection_evidence = protect.collect(text)
    people = seeds_mod.collect(text, cfg, mentions=mentions, people=edits.people)
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
    if cfg.first_names:
        _propose_given_names(text, people, cfg, candidates)
    _propose_structured(text, candidates)
    _propose_addresses(text, candidates)
    _propose_places(text, candidates)
    _propose_companies(text, candidates)
    candidates, merges, custom = _apply_edits(text, candidates, edits)

    accepted = resolve(candidates, len(text), cfg)
    accepted, registry = _allocate_replacements(
        accepted, custom, dict(edits.prior_tags), cfg.roles)
    return Analysis(
        text=text,
        config=cfg,
        decisions=tuple(accepted),
        entities=tuple(_entity_records(accepted)),
        mapping=registry.mapping(),
        expected_aliases=frozenset(_expected_aliases(people, accepted, cfg, merges)),
        warnings=tuple(_role_conflicts(people, protection_evidence)),
    )


def render(analysis: Analysis) -> tuple[str, Report]:
    """Apply an analysis's decisions once and verify the result."""
    output, replacement_spans, protected_output = _render(analysis.text, analysis.decisions)
    if analysis.config.verify:
        verification = verify(
            output,
            protected_spans=protected_output,
            expected_aliases=analysis.expected_aliases,
            replacements=len(replacement_spans),
            warnings=analysis.warnings,
        )
    else:
        verification = Verification(status="not_run", warnings=analysis.warnings)

    protected_names = sorted({
        decision.text
        for decision in analysis.decisions
        if decision.action == "keep" and decision.kind == "JUDGE"
    })
    report = Report(
        mapping=dict(analysis.mapping),
        protected=protected_names,
        replacements=len(replacement_spans),
        replacement_spans=replacement_spans,
        status=verification.status,
        residuals=list(verification.residuals),
        warnings=list(verification.warnings),
        decisions=list(analysis.decisions),
        entity_records=list(analysis.entities),
    )
    report.risk = residual_risk(output, report)
    return output, report


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
    return render(analyze(raw, cfg))
