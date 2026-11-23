"""Source-agnostic pipeline for pseudonimizzatore_legale.

The stages exchange candidates and decisions rather than editing text in sequence:

    normalize → detect → resolve identities → apply policy → render once → verify

Judicial roles are detected alongside private people. They become exact keep decisions
only in late policy, so a judge's surname cannot veto an unrelated party globally.

`anonymize` is `render(analyze(...))`. Case metadata and review decisions enter
the same pipeline through `state=`. Supplied people use the same
name propagation as people detected automatically.

>>> doc = "Il sig. Mario Rossi ricorre. Sentito Zappacosta."
>>> analysis = analyze(doc)
>>> [(row.placeholder, row.aliases, row.spans) for row in analysis.entities]
[('Nominativo_1', ('Mario Rossi',), ((8, 19),))]
>>> state = analysis.state
>>> state["people"].append({"name": "Zappacosta"})
>>> render(analyze(doc, state=state))[0]
'Il sig. Nominativo_1 ricorre. Sentito Nominativo_2.'
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field, replace
from hashlib import sha256

import regex as re

from . import patterns as P
from . import protect, seeds as seeds_mod, text as text_mod
from .config import Config
from .constraints import ReviewState
from .labels import role_key
from .model import (
    Candidate,
    Decision,
    Entity,
    EntityRecord,
    Mention,
    ResidualFinding,
    Verification,
    person_key,
)
from .policy import (
    PRI_ADDRESS,
    PRI_COMPANY,
    PRI_PERSON_FULL,
    PRI_PERSON_TOKEN,
    PRI_PROTECTED,
    PRI_STRUCTURED,
    apply_person_policy,
    resolve,
)
from .verification import verify

REPORT_SCHEMA_VERSION = 4


@dataclass
class Report:
    """Auditable result metadata for one document.

    Replacement/decision offsets refer to normalized input; residual offsets refer to
    returned output. When ``sanitize`` is true, normalized input differs from raw text.
    ``unresolved`` lists occurrence decisions that could not be located uniquely.
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
    unresolved: list[dict] = field(default_factory=list)
    state: dict = field(default_factory=dict)

    @property
    def entities(self) -> int:
        """Number of distinct replacement tags emitted."""
        return len({d.replacement for d in self.decisions if d.replacement is not None})


@dataclass(frozen=True)
class Analysis:
    """Everything decided about one document, before it is rewritten.

    ``text`` is the normalized input, and every offset refers to it. ``entities`` are
    the review-panel rows, one per matched document identity with all its spans.
    """

    text: str
    config: Config
    decisions: tuple[Decision, ...]
    entities: tuple[EntityRecord, ...]
    mapping: dict[str, str]
    expected_aliases: frozenset[str]
    warnings: tuple[str, ...]
    unresolved: tuple[dict, ...] = ()
    dismissed_spans: tuple[tuple[int, int], ...] = ()
    state: dict = field(default_factory=dict)


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


def _propose_case_numbers(text: str, evidence, out: list[Candidate]) -> None:
    for start, end in evidence.spans:
        out.append(_candidate(
            text, start, end,
            kind="CASE_NUMBER",
            source="legal_role:case_number",
            priority=PRI_PROTECTED,
            role="Numero",
            protection="case_number",
            reason="procedural identifier kept by policy",
        ))


def _supplied_role(person: dict) -> str | None:
    role = person.get("role")
    if role is None:
        return None
    return {"persona": "Nominativo", "avvocato": "Difensore"}.get(role, role.title())


# Broad party blocks can include a bench list. Require a stronger private-role cue
# before letting a detected private identity override the judicial evidence.
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
}

def _classify_judges(people: list[Entity], judicial_names: set[str],
                     submitted: dict[tuple, dict], warnings: list[str]) -> list[Entity]:
    """Add judicial evidence to the same identity list used by all person matchers."""
    by_key = {person.key: person for person in people}
    for name in sorted(judicial_names):
        key = person_key(name)
        explicit = submitted.get(key)
        entity = by_key.get(key)
        if explicit and explicit.get("role") not in (None, "giudice"):
            continue
        if entity and entity.sources & _PRIVATE_ROLE_SOURCES:
            warning = f"conflicting judicial/private-role evidence for {entity.display!r}"
            if warning not in warnings:
                warnings.append(warning)
            if not explicit or explicit.get("role") != "giudice":
                continue
            # A keep action or policy must not win over strong private evidence.
            entity.sources.add("conflict:judicial_role")
        if entity is None:
            entity = by_key[key] = Entity(name, "Giudice")
        entity.role = "Giudice"
        entity.variants.add(name)
        entity.sources.add("legal_role:judge")
    return list(by_key.values())


_COMPANY_INTRO = re.compile(
    r"(?i:(?:(?:di|del|della|dei|degli|delle|il|lo|la|le|gli|e)\s+)+)"
)

#: A capitalised common noun opening a sentence ("Socio della Alfa S.r.l.") is prose,
#: not part of the company name; the name pattern takes any capitalised word.
_COMPANY_LEAD_NOUN = re.compile(
    r"(?P<noun>\p{L}+)\s+(?i:(?:di|del|della|dei|degli|delle)\s+)")


def _company_lead_length(value: str) -> int:
    """Length of a leading common noun plus its preposition, else 0."""
    lead = _COMPANY_LEAD_NOUN.match(value)
    if lead and lead.group("noun").casefold() in seeds_mod.common_words():
        return lead.end()
    return 0


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
    ambiguous = {token for token, values in owners.items() if len(values) > 1}
    for entity in entities:
        source = "+".join(sorted(entity.sources)) or "person"
        judicial = role_key(entity.role) == "giudice"
        for pattern, is_full_name in seeds_mod.variant_patterns(
            entity,
            cfg.min_token_len,
            skip_tokens=ambiguous,
        ):
            if judicial and not is_full_name:
                continue
            priority = PRI_PERSON_FULL if is_full_name else PRI_PERSON_TOKEN
            for match in pattern.finditer(text):
                if judicial and len(match.group().split()) != len(entity.display.split()):
                    continue
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
        if role_key(entity.role) == "giudice":
            continue
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


def _propose_initials(text: str, cfg: Config, out: list[Candidate]) -> None:
    """Propose the initials some sources write in place of a name ("A.G.").

    `seeds.initials` decides who is a person; here they become candidates like any other
    person, so roles, tags, judges and overlaps go through the same policy. The tag is
    allocated per initials, not per spelling: "A. G." and "A.G." are one person.
    """
    for mention in seeds_mod.initials(text, everywhere=cfg.initials == "all"):
        out.append(_candidate(
            text,
            mention.start,
            mention.end,
            kind="PERSON",
            source=mention.source,
            priority=PRI_PERSON_FULL,
            role=mention.role,
            label=mention.role,
            value=seeds_mod.initials_key(mention.text),
            reason=("initials behind a person cue, or the same initials again"
                    if mention.source == "regex:initials"
                    else "initials, in a source that writes its parties as initials"),
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
        # After the institution guard, which needs the head words ("Agenzia delle …").
        start += _company_lead_length(text[start:match.end(1)])
        value = re.sub(r"\s+", " ", text[start:match.end(1)]).strip()
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
            if decision.source != "user:occurrence":
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
        if decision.entity_id:
            grouped[decision.entity_id].append(decision)

    records = []
    for entity_id, items in grouped.items():
        first = items[0]
        records.append(EntityRecord(
            entity_id=entity_id,
            kind=first.kind,
            role=first.role,
            action=_resolved_action(items),
            aliases=tuple(sorted({item.text for item in items},
                                 key=lambda alias: (alias.casefold(), alias))),
            sources=tuple(sorted({item.source for item in items})),
            spans=tuple((item.start, item.end) for item in items),
            placeholder=next((item.replacement for item in items if item.replacement), None),
        ))
    return records


def _resolved_action(decisions: list[Decision]) -> str:
    actions = {decision.action for decision in decisions}
    return "mixed" if len(actions) > 1 else decisions[0].action


def _expected_aliases(
    entities: list[Entity],
    decisions: list[Decision],
    cfg: Config,
) -> set[str]:
    redacted = {
        person_key(decision.value or decision.text)
        for decision in decisions
        if decision.action == "redact" and decision.kind == "PERSON"
    }
    aliases: set[str] = set()
    for entity in entities:
        if entity.key not in redacted:
            continue
        for value in entity.variants | {entity.display}:
            aliases.update(seeds_mod.name_orders(value))
        aliases.update(seeds_mod.rare_tokens(entity.display, cfg.min_token_len))
    return aliases


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


def _detect(text, cfg, seeds, evidence, submitted):
    """Collect native candidates, optionally seeding additional person identities."""
    people = seeds.all((person["name"], _supplied_role(person)) for person in submitted.values())
    warnings = []
    judicial_names = evidence.names | {person["name"] for person in submitted.values()
                                      if person.get("role") == "giudice"}
    people = _classify_judges(people, judicial_names, submitted, warnings)

    candidates: list[Candidate] = []
    _propose_case_numbers(text, evidence, candidates)
    _propose_people(text, people, cfg, candidates)
    if cfg.first_names:
        _propose_given_names(text, people, cfg, candidates)
    if cfg.initials:
        _propose_initials(text, cfg, candidates)
    _propose_structured(text, candidates)
    _propose_addresses(text, candidates)
    _propose_places(text, candidates)
    _propose_companies(text, candidates)
    return people, candidates, warnings


def analyze(
    raw: str,
    config: Config | None = None,
    *,
    state: dict | None = None,
    mentions: tuple[Mention, ...] = (),
) -> Analysis:
    """Detect, resolve and tag one document without rewriting it.

    ``mentions`` are person mentions from a NER run on ``normalize(raw, config)``, one
    more seed source. Supply metadata or a previous report's ``state`` to carry decisions forward.
    """
    cfg = config if config is not None else Config()
    text = normalize(raw, cfg)
    review = ReviewState(state)
    revision = sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()
    rules = list(review.by_id.values())
    seeds = seeds_mod.collect_seeds(text, cfg, mentions=mentions)
    evidence = protect.collect(text)
    native = None
    if not rules and not review.content["occurrences"]:
        review.content["discovery_revision"] = revision
    elif rules and review.content.get("discovery_revision") == revision:
        # Reconstruct the native matches from the source. This also lets a reviewer
        # change a tag without turning a contextual match into a literal rule.
        native = _detect(text, cfg, deepcopy(seeds), evidence, {})
        _, candidates, _ = native
        native_candidates = apply_person_policy(candidates, {}, cfg)
        baseline = ReviewState(None)
        for decision in resolve(native_candidates, len(text), cfg):
            baseline.assign(decision, cfg)
        rules = review.changed_rules(baseline)

    submitted = {person_key(row["name"]): row for row in rules if "name" in row}
    if native is None or submitted:
        native = _detect(text, cfg, seeds, evidence, submitted)
    people, candidates, warnings = native
    if rules:
        review.complete_metadata(people, candidates, cfg)
        candidates = review.bind_person_aliases(candidates, submitted)
    candidates = apply_person_policy(candidates, submitted, cfg)
    if rules:
        candidates += list(review.literal_candidates(text, candidates, people, rules))
    accepted = resolve(candidates, len(text), cfg, warnings=warnings)
    decisions = [review.assign(d, cfg) for d in accepted]
    decisions, dismissed, unresolved = review.apply_occurrences(text, decisions, cfg)
    if unresolved:
        warnings.append("some occurrence decisions could not be applied uniquely")
    if any(d.source == "alias:ambiguous" for d in decisions):
        warnings.append("an ambiguous alias could not be attributed to one identity")
    tags_by_value = defaultdict(set)
    for decision in decisions:
        if decision.replacement is not None:
            tags_by_value[decision.value or decision.text].add(decision.replacement)
    mapping = {value: next(iter(tags)) for value, tags in tags_by_value.items() if len(tags) == 1}
    return Analysis(
        text=text,
        config=cfg,
        decisions=tuple(decisions),
        entities=tuple(_entity_records(decisions)),
        mapping=mapping,
        expected_aliases=frozenset(_expected_aliases(people, decisions, cfg)),
        warnings=tuple(warnings),
        unresolved=tuple(unresolved),
        dismissed_spans=tuple(dismissed),
        state=review.content,
    )


def _output_span(start: int, end: int, decisions: tuple[Decision, ...]) -> tuple[int, int] | None:
    """Translate an intact input span past earlier substitutions."""
    shift = 0
    for decision in decisions:
        if decision.start >= end:
            break
        if decision.replacement is not None:
            if decision.end > start:
                return None
            shift += len(decision.replacement) - (decision.end - decision.start)
    return start + shift, end + shift


def render(analysis: Analysis) -> tuple[str, Report]:
    """Apply an analysis's decisions once and verify the result."""
    output, replacement_spans, protected_output = _render(analysis.text, analysis.decisions)
    if analysis.config.verify:
        acknowledged = set(analysis.dismissed_spans)
        acknowledged.update((d.start, d.end) for d in analysis.decisions
                            if d.action == "keep" and d.source == "user:literal")
        verification = verify(
            output,
            protected_spans=protected_output,
            expected_aliases=analysis.expected_aliases,
            replacements=len(replacement_spans),
            warnings=analysis.warnings,
            dismissed_spans={span for start, end in acknowledged
                             if (span := _output_span(start, end, analysis.decisions)) is not None},
        )
    else:
        verification = Verification(status="not_run", warnings=analysis.warnings)

    protected_names = sorted({
        decision.text
        for decision in analysis.decisions
        if decision.action == "keep" and decision.kind == "PERSON"
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
        unresolved=list(analysis.unresolved),
        state=deepcopy(analysis.state),
    )
    report.risk = residual_risk(output, report)
    return output, report


def anonymize(raw: str, config: Config | None = None, *,
              state: dict | None = None, **overrides) -> tuple[str, Report]:
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
    return render(analyze(raw, cfg, state=state))
