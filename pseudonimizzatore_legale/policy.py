"""Late policy application and deterministic overlap resolution.

Detection never decides that text is safe to keep. Judicial roles and case numbers are
ordinary candidates carrying protection evidence; this module applies the configured
policy after every detector has run. That prevents a judge's surname from globally
vetoing an unrelated party with the same surname.
"""
from __future__ import annotations

from dataclasses import replace

from .config import Config
from .labels import role_key
from .model import Candidate, Decision, person_key

# Higher priority wins a contested span. These values describe evidence strength, not
# detector execution order. A reviewer's explicit edit outranks every detector.
PRI_USER = 200
PRI_STRUCTURED = 120
PRI_PROTECTED = 100
PRI_ADDRESS = 40
PRI_COMPANY = 35
PRI_PERSON_FULL = 30
PRI_PERSON_TOKEN = 20


def _enabled(candidate: Candidate, config) -> bool:
    if candidate.protection == "case_number":
        return config.keep_case_numbers
    if candidate.mention.kind == "ORGANIZATION" and candidate.entity_id is None:
        if config.companies == "person_named":
            return candidate.mention.source == "regex:person_named_company"
        return bool(config.companies)
    return True


def apply_person_policy(candidates: list[Candidate], people: dict[tuple, dict],
                        config: Config) -> list[Candidate]:
    """Apply person policy to identified mentions while retaining their match strength."""
    proposed = []
    for candidate in candidates:
        mention = candidate.mention
        if (mention.kind == "PERSON" and candidate.value and mention.source != "alias:ambiguous"
                and "conflict:judicial_role" not in mention.source):
            person = people.get(person_key(candidate.value), {})
            keep = person.get("action") == "keep" or (
                "action" not in person and role_key(mention.role) in config.keep_roles)
            if keep:
                # A weak token may yield to a longer identity just as it would for redaction.
                priority = PRI_PROTECTED if mention.full_name else candidate.priority
                candidate = replace(candidate, protection="person", priority=priority,
                                    reason="person kept by role policy or explicit choice")
        proposed.append(candidate)
    return proposed


def resolve(candidates: list[Candidate], length: int, config, *,
            warnings: list[str] | None = None) -> list[Decision]:
    """Apply policy, then select one non-overlapping action for each character."""
    eligible = [candidate for candidate in candidates if _enabled(candidate, config)]
    if any(c.protection == "person" for c in eligible):
        # A confirmed identity can invalidate a shorter keep. A detector alone
        # can overrun a name, for example by reading GENERALE as part of it.
        full_private = [
            c.mention for c in eligible
            if c.protection is None and c.mention.kind == "PERSON" and c.mention.full_name
            and "user" in c.mention.source.split("+")
        ]
        protected = [
            c for c in eligible if c.protection == "person" and any(
                m.start <= c.mention.start and c.mention.end <= m.end
                and (m.start, m.end) != (c.mention.start, c.mention.end)
                for m in full_private
            )
        ]
        if protected:
            blocked = set(protected)
            eligible = [replace(c, protection=None, priority=PRI_PERSON_FULL,
                                reason="shorter keep conflicted with a private full name")
                        if c in blocked else c for c in eligible]
            if warnings is not None:
                warnings.append("a person keep matched inside a longer private name")
    # A saved literal may straddle the boundary of a longer detected identifier.
    # Let the complete identifier win so redacting one word never exposes the rest.
    requested = [c for c in eligible if c.priority == PRI_USER]
    if requested:
        identifiers = [c.mention for c in eligible if c.priority in (PRI_STRUCTURED, PRI_ADDRESS)]
        people = [c.mention for c in eligible if c.priority == PRI_PERSON_FULL and c.mention.full_name]
        blocked = set()
        for candidate in requested:
            start, end = candidate.mention.start, candidate.mention.end
            if any(m.start < end and start < m.end and (start > m.start or end < m.end)
                   for m in identifiers):
                blocked.add(candidate)
            elif any(m.start <= start and end <= m.end and (start, end) != (m.start, m.end)
                     for m in people):
                blocked.add(candidate)
        if blocked:
            eligible = [c for c in eligible if c not in blocked]
            if warnings is not None:
                warnings.append("skipped a partial match to preserve a longer detected entity")
    eligible.sort(
        key=lambda candidate: (
            -candidate.priority,
            -(candidate.mention.end - candidate.mention.start),
            candidate.mention.start,
        )
    )

    taken = bytearray(length)
    accepted: list[Decision] = []
    for candidate in eligible:
        mention = candidate.mention
        if mention.start >= mention.end or mention.end > length:
            continue
        if any(taken[mention.start:mention.end]):
            continue
        taken[mention.start:mention.end] = b"\x01" * (mention.end - mention.start)

        keep = candidate.protection is not None
        accepted.append(
            Decision(
                start=mention.start,
                end=mention.end,
                text=mention.text,
                kind=mention.kind,
                source=mention.source,
                action="keep" if keep else "redact",
                reason=candidate.reason or (
                    f"protected {candidate.protection}" if keep else "detector match"
                ),
                role=mention.role,
                entity_id=candidate.entity_id,
                label=candidate.label,
                value=candidate.value,
            )
        )

    accepted.sort(key=lambda decision: decision.start)
    return accepted
