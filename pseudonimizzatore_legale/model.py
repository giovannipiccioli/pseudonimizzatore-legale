"""Shared data structures for detection, policy and audit output.

The pipeline deliberately passes data, not rewritten text, between stages. Detectors
emit mentions and candidates; policy turns them into decisions; the renderer applies
the accepted decisions once; verification only inspects the result.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Mention:
    """One possible entity mention, with offsets into the normalized input text."""

    # Keep these first five fields stable: optional NER integrations historically
    # construct Mention positionally.
    text: str
    start: int
    end: int
    role: str = "Nominativo"
    score: float = 1.0
    kind: str = "PERSON"
    source: str = "regex"
    full_name: bool = True


@dataclass
class Entity:
    """A document-local person identity before policy is applied."""

    display: str
    role: str
    variants: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)

    @property
    def key(self) -> tuple[str, ...]:
        """Order-insensitive identity: ``ROSSI MARIO`` equals ``Mario Rossi``."""
        return tuple(sorted(token.casefold() for token in self.display.split() if token))


@dataclass(frozen=True)
class Candidate:
    """A detector proposal awaiting policy and overlap resolution."""

    mention: Mention
    priority: int
    label: str | None = None
    value: str | None = None
    protection: str | None = None       # ``judge`` or ``case_number``
    reason: str = ""


@dataclass(frozen=True)
class Decision:
    """One accepted, non-overlapping action in normalized-input coordinates."""

    start: int
    end: int
    text: str
    kind: str
    source: str
    action: str                         # ``redact`` or ``keep``
    reason: str
    role: str | None = None
    entity_id: str | None = None
    replacement: str | None = None
    label: str | None = None
    value: str | None = None


@dataclass(frozen=True)
class EntityRecord:
    """Compact audit record for one accepted document-local entity."""

    entity_id: str
    kind: str
    role: str | None
    action: str
    aliases: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class ResidualFinding:
    """Something left in the output which warrants review (output offsets)."""

    start: int
    end: int
    text: str
    kind: str
    source: str
    reason: str


@dataclass(frozen=True)
class Verification:
    """Result of non-mutating review checks over the rewritten document."""

    status: str                         # ``passed_checks`` or ``needs_review``
    residuals: tuple[ResidualFinding, ...] = ()
    warnings: tuple[str, ...] = ()
