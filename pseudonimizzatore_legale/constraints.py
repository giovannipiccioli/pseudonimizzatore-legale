"""Document-local review state. The public representation is ordinary JSON data."""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass, replace

import regex as re

from .labels import DATA_PREFIXES, ROLE_PREFIXES, role_key
from .model import Candidate, Decision, Mention, person_key
from .policy import PRI_USER
from .text import normalize_quotes


@dataclass(frozen=True)
class TextAnchor:
    """A quotation and its exact surroundings in normalized input coordinates."""

    quote: str
    prefix: str = ""
    suffix: str = ""

    def __post_init__(self):
        if not self.quote:
            raise ValueError("a text anchor needs a nonempty quotation")

    @classmethod
    def capture(cls, text: str, start: int, end: int, *, context: int = 24) -> TextAnchor:
        """Capture a selection in Analysis.text. Context stops at a line boundary."""
        if not 0 <= start < end <= len(text) or context < 0:
            raise ValueError("invalid selection or context length")
        prefix = text[max(0, start - context):start].rsplit("\n", 1)[-1]
        suffix = text[end:end + context].split("\n", 1)[0]
        anchor = cls(text[start:end], prefix, suffix)
        if anchor.locate(text) != (start, end):
            raise ValueError("the selection and its context do not identify a unique occurrence")
        return anchor

    def locate(self, text: str) -> tuple[int, int] | None:
        """Return the selected span only when the excerpt matches exactly once."""
        # At a line or document edge there may be no context on one side.
        # A saved whole word must not attach to the beginning of a longer one.
        left = r"(?<!\w)" if not self.prefix and self.quote[0].isalnum() else ""
        right = r"(?!\w)" if not self.suffix and self.quote[-1].isalnum() else ""
        pattern = re.compile(left + re.escape(self.prefix + self.quote + self.suffix) + right)
        match = pattern.search(text)
        if match is None or pattern.search(text, match.start() + 1):
            return None
        start = match.start() + len(self.prefix)
        return start, start + len(self.quote)


def _fold(value: str) -> str:
    return " ".join(normalize_quotes(value).split()).casefold()


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value


def _fields(row: dict, allowed: set[str]) -> None:
    if not isinstance(row, dict):
        raise ValueError("state entries must be objects")
    unknown = row.keys() - allowed
    if unknown:
        raise ValueError(f"unknown state fields: {sorted(unknown)}")


class ReviewState:
    """A private working copy, indexed for matching and numbering during one run."""

    def __init__(self, state: dict | None):
        state = {} if state is None else state
        _fields(state, {"people", "data", "occurrences", "discovery_revision"})
        self.content = {}
        if "discovery_revision" in state:
            revision = _string(state["discovery_revision"], "discovery_revision")
            if not re.fullmatch(r"[0-9a-f]{64}", revision):
                raise ValueError("discovery_revision must be a SHA-256 digest")
            self.content["discovery_revision"] = revision
        for key in ("people", "data", "occurrences"):
            rows = state.get(key, [])
            if not isinstance(rows, list):
                raise ValueError(f"{key} must be a list")
            self.content[key] = deepcopy(rows)

        self.by_id = {}
        self.people = {}
        self.data = {}
        self._ids = set()
        self._tags = set()
        self._counters = Counter()
        for collection in ("people", "data"):
            for row in self.content[collection]:
                self._read_entity(row, collection == "people")
        for row in self.content["people"] + self.content["data"]:
            self._identify(row)
        for choice in self.content["occurrences"]:
            _fields(choice, {"anchor", "action", "entity_id", "placeholder"})
            anchor = choice.get("anchor")
            _fields(anchor, {"quote", "prefix", "suffix"})
            _string(anchor.get("quote"), "quote")
            if any(not isinstance(v, str) for v in anchor.values()):
                raise ValueError("anchor context must be text")
            action = choice.get("action")
            if action not in ("keep", "redact", "dismiss"):
                raise ValueError("invalid occurrence action")
            if choice.keys() & {"entity_id", "placeholder"} and action != "redact":
                raise ValueError("only a redaction takes a target or placeholder")
            if "entity_id" in choice:
                if _string(choice["entity_id"], "entity_id") not in self.by_id:
                    raise ValueError("unknown occurrence entity_id")
                if "placeholder" in choice:
                    raise ValueError("a linked occurrence uses its entity's placeholder")
            self._reserve(choice, "placeholder", self._tags)

    @staticmethod
    def _reserve(row, field, used):
        if field in row:
            value = _string(row[field], field)
            if value in used:
                raise ValueError(f"duplicate {field}: {value}")
            used.add(value)

    def _read_entity(self, row, person):
        field = "name" if person else "value"
        category = "role" if person else "type"
        _fields(row, {field, category, "action", "placeholder", "aliases", "id"})
        value = _string(row.get(field), field)
        if "action" in row and row["action"] not in ("redact", "keep"):
            raise ValueError("entity action must be redact or keep")
        if category in row:
            key = _string(row[category], category).strip().casefold()
            if person:
                key = role_key(key)
            if key not in (ROLE_PREFIXES if person else DATA_PREFIXES):
                raise ValueError(f"unknown {category}: {key}")
            row[category] = key
        aliases = row.get("aliases", [])
        if not isinstance(aliases, list):
            raise ValueError("aliases must be a list")
        for alias in aliases:
            _string(alias, "alias")
        index = self.people if person else self.data
        key = person_key(value) if person else _fold(value)
        if key in index:
            raise ValueError(f"duplicate {field}: {value}")
        index[key] = row
        self._reserve(row, "id", self._ids)
        self._reserve(row, "placeholder", self._tags)

    def _number(self, prefix, used):
        while True:
            self._counters[prefix] += 1
            value = f"{prefix}{self._counters[prefix]}"
            if value not in used:
                used.add(value)
                return value

    def _identify(self, row):
        if "id" not in row:
            row["id"] = self._number("p" if "name" in row else "d", self._ids)
        self.by_id[row["id"]] = row

    def complete_metadata(self, people, candidates, config):
        roles = {p.key: role_key(p.role) for p in people}
        for key, row in self.people.items():
            inferred = roles.get(key)
            row.setdefault("role", inferred if inferred in ROLE_PREFIXES else "persona")
            row.setdefault("action", "keep" if row["role"] in config.keep_roles else "redact")
        detected_types = {}
        for candidate in candidates:
            if candidate.mention.kind != "PERSON":
                key = _fold(candidate.value or candidate.mention.text)
                detected_types.setdefault(key, (candidate.label or candidate.mention.role).casefold())
        for key, row in self.data.items():
            row.setdefault("type", detected_types.get(key, "dato"))
            row.setdefault("action", "redact")

    def changed_rules(self, baseline):
        """Select changes to matching on the discovery revision. IDs and tags
        are applied during allocation regardless of how a match was found.
        """
        match_fields = ("name", "value", "role", "type", "action")
        changed = []
        for index, previous in ((self.people, baseline.people), (self.data, baseline.data)):
            for key, row in index.items():
                original = previous.get(key)
                if (original is None or any(row.get(f) != original.get(f) for f in match_fields)
                        or set(row.get("aliases", ())) != set(original.get("aliases", ()))):
                    changed.append(row)
        return changed

    def bind_person_aliases(self, candidates, submitted):
        """Give a detected alternative identity and its unique mentions their owner's ID."""
        aliases = defaultdict(set)
        for row in submitted.values():
            for alias in row.get("aliases", []):
                aliases[person_key(alias)].add(row["id"])
        if not aliases:
            return candidates
        bound = []
        for candidate in candidates:
            key = person_key(candidate.value or "")
            owners = aliases.get(key, ())
            if (candidate.mention.kind == "PERSON" and candidate.mention.source != "alias:ambiguous"
                    and key not in self.people and len(owners) == 1):
                row = self.by_id[next(iter(owners))]
                candidate = replace(candidate, mention=replace(candidate.mention, role=row["role"]),
                                    label=row["role"], value=row["name"], entity_id=row["id"])
            bound.append(candidate)
        return bound

    def literal_candidates(self, text, detected, people, rules):
        """Match saved expressions even when their original detector cue is gone."""
        owners = {}
        for row in self.by_id.values():
            value = row.get("name") or row["value"]
            for spelling in [value, *row.get("aliases", [])]:
                owners.setdefault(_fold(spelling), {})[row["id"]] = row

        # A bare alias can become ambiguous when a new person enters the document.
        token_owners = defaultdict(set)
        for person in people:
            for token in person.key:
                token_owners[token].add(person.key)
        seen_kinds = {(c.label or c.mention.role).casefold(): c.mention.kind for c in detected
                      if c.mention.kind != "PERSON"}
        active_ids = {row["id"] for row in rules}
        for spelling, rows in owners.items():
            if active_ids.isdisjoint(rows):
                continue
            literal = r"\s+".join(re.escape(t) for t in spelling.split())
            pattern = re.compile(r"(?<!\w)" + literal + r"(?!\w)", re.I)
            row = next(iter(rows.values()))
            ambiguous = len(rows) > 1
            if "name" in row and token_owners.get(spelling, set()) - {person_key(row["name"])}:
                ambiguous = True
            for match in pattern.finditer(text):
                if ambiguous:
                    yield Candidate(Mention(match[0], *match.span(), source="alias:ambiguous",
                                            full_name=False), PRI_USER, "Nominativo", match[0])
                    continue
                person = "name" in row
                category = row["role"] if person else row.get("type", "dato")
                label = ROLE_PREFIXES[category] if person else DATA_PREFIXES[category]
                value = row["name"] if person else row["value"]
                mention = Mention(match[0], *match.span(), role=category, source="user:literal",
                                  kind="PERSON" if person else seen_kinds.get(category, label.upper()))
                yield Candidate(mention, PRI_USER, label, value,
                                protection="user" if row["action"] == "keep" else None,
                                reason="saved document decision", entity_id=row["id"])

    def assign(self, decision, config):
        """Attach the stable document identity and, for a redaction, its tag."""
        person = decision.kind == "PERSON"
        value = decision.value or decision.text
        index = self.people if person else self.data
        key = person_key(value) if person else _fold(value)
        row = self.by_id.get(decision.entity_id) or index.get(key)
        category = role_key(decision.role or "persona") if person else (
            decision.label or decision.role or "dato").casefold()
        if row is None:
            if person:
                row = {"name": value, "role": category if category in ROLE_PREFIXES else "persona"}
            else:
                row = {"value": value, "type": category if category in DATA_PREFIXES else "dato"}
            row["action"] = decision.action
            index[key] = row
            self.content["people" if person else "data"].append(row)
            self._identify(row)
        # Record alternative complete spellings, including spaced initials. Short
        # inferred name fragments remain subject to the engine's ambiguity checks.
        if (person and decision.source != "user:literal" and _fold(value) != _fold(decision.text)
                and (person_key(value) == person_key(decision.text) or "initials" in decision.source)):
            aliases = row.setdefault("aliases", [])
            if decision.text not in aliases:
                aliases.append(decision.text)
        replacement = self.tag(row, config) if decision.action == "redact" else None
        return replace(decision, entity_id=row["id"], replacement=replacement,
                       role=row["role"] if person else decision.role)

    def tag(self, row, config):
        if "placeholder" not in row:
            if "name" in row:
                prefix = ROLE_PREFIXES.get(row["role"], "Nominativo") if config.roles else "Nominativo"
            else:
                prefix = DATA_PREFIXES.get(row.get("type", "dato"), "Dato")
            row["placeholder"] = self._number(prefix + "_", self._tags)
        return row["placeholder"]

    def apply_occurrences(self, text, decisions, config):
        """Overlay one-passage choices on the document-wide decisions."""
        dismissed, unresolved, located = [], [], []
        for choice in self.content["occurrences"]:
            span = TextAnchor(**choice["anchor"]).locate(text)
            if span is None:
                unresolved.append(choice)
            elif choice["action"] == "dismiss":
                dismissed.append(span)
            else:
                located.append((*span, choice))

        if not located:
            return decisions, dismissed, unresolved

        result = list(decisions)
        for start, end, choice in located:
            overlaps = [d for d in decisions if d.start < end and start < d.end]
            if (any(d.start < start or end < d.end for d in overlaps)
                    or any(a < end and start < b and other is not choice for a, b, other in located)):
                unresolved.append(choice)
                continue
            surface = text[start:end]
            action = choice["action"]
            row = self.by_id.get(choice.get("entity_id"))
            exact = next((d for d in overlaps if (d.start, d.end) == (start, end)), None)
            if action == "keep" and exact:
                edited = replace(exact, action=action, source="user:occurrence",
                                 replacement=None, reason="kept at this passage")
            else:
                target = row if row is not None else choice
                replacement = self.tag(target, config) if action == "redact" else None
                edited = Decision(
                    start=start, end=end, text=surface, action=action, source="user:occurrence",
                    kind="PERSON" if "name" in target else target.get("type", "dato").upper(),
                    reason="review decision at this passage", role=target.get("role"),
                    entity_id=target.get("id"), replacement=replacement,
                    value=target.get("name") or target.get("value") or surface,
                )
            result = [d for d in result if d not in overlaps]
            result.append(edited)
        return sorted(result, key=lambda d: d.start), dismissed, unresolved
