"""Late policy application and deterministic overlap resolution.

Detection never decides that text is safe to keep. Judicial roles and case numbers are
ordinary candidates carrying protection evidence; this module applies the configured
policy after every detector has run. That prevents a judge's surname from globally
vetoing an unrelated party with the same surname.
"""
from __future__ import annotations

from .model import Candidate, Decision

# Higher priority wins a contested span. These values describe evidence strength, not
# detector execution order.
PRI_STRUCTURED = 120
PRI_PROTECTED = 100
PRI_ADDRESS = 40
PRI_PERSON_FULL = 30
PRI_PERSON_TOKEN = 20
PRI_COMPANY = 10


def _enabled(candidate: Candidate, config) -> bool:
    if candidate.protection == "judge":
        return config.keep_judges
    if candidate.protection == "case_number":
        return config.keep_case_numbers
    if candidate.mention.kind == "ORGANIZATION":
        return config.companies
    return True


def resolve(candidates: list[Candidate], length: int, config) -> list[Decision]:
    """Apply policy, then select one non-overlapping action for each character."""
    eligible = [candidate for candidate in candidates if _enabled(candidate, config)]
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
                label=candidate.label,
                value=candidate.value,
            )
        )

    accepted.sort(key=lambda decision: decision.start)
    return accepted
