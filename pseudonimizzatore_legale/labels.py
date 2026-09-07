"""Pseudonym allocation for Italian legal documents.

Tags name the *role*, never the person:

    Ricorrente_1, Resistente_1, Difensore_1, Nominativo_1, Società_1,
    CF_1, Email_1, Pec_1, IVA_1, Iban_1, Telefono_1, Indirizzo_1, …

The obvious alternative — initials, "Mario Rossi" → "M. R." — is worse on every axis
that matters here. Initials still carry information (the Garante treats them as
pseudonymous, not anonymous), they collide constantly at corpus scale, and the
disambiguation they then need ("M. R. (2)") reads badly. A role tag says what the
person *is* in the proceeding, which is the part a reader actually needs, and says
nothing about who they are.

**Counters restart at 1 for every document.** Consistency is per document by design, so
`Ricorrente_1` in one file has no relationship to `Ricorrente_1` in another. Two
consequences follow, and both are deliberate: the batch path needs no shared state and
parallelises trivially, and two documents about the same person cannot be linked back
together through their tags.
"""
from collections import defaultdict

#: Every role word this module can emit. Detection must refuse to treat these as names,
#: otherwise a second pass over an already-processed file re-detects its own output and
#: rewrites `Nominativo_1` to `Difensore_1_1`. Running the tool twice has to be a no-op:
#: batches get resumed, re-run after a rule change, and fed from mixed directories.
RESERVED = frozenset({
    "Ricorrente", "Resistente", "Difensore", "Rappresentante", "Nominativo",
    "Terzo", "Società", "Associazione", "Consorzio", "Banca", "Ditta",
    "CF", "Email", "Pec", "IVA", "Iban", "Telefono", "Targa",
    "Indirizzo", "Documento", "Data_nascita", "Luogo", "Numero",
})


class Registry:
    """Allocates one stable tag per distinct entity, per document."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._tags: dict[tuple[str, str], str] = {}      # (role, key) -> tag
        self._display: dict[tuple[str, str], str] = {}   # (role, key) -> readable text

    def tag(self, role: str, value: str) -> str:
        """Return the tag for `value`, allocating a new one on first sight.

        Entities are deduplicated case-insensitively — the same e-mail address written
        two ways is one entity and gets one tag — while the report keeps the first
        spelling actually seen, so it stays readable.
        """
        key = (role, value.casefold())
        existing = self._tags.get(key)
        if existing is not None:
            return existing
        self._counters[role] += 1
        tag = f"{role}_{self._counters[role]}"
        self._tags[key] = tag
        self._display[key] = value
        return tag

    def mapping(self) -> dict[str, str]:
        """Every allocation made, as ``{original text: tag}``, for the run report."""
        return {self._display[k]: v for k, v in self._tags.items()}

    def __len__(self) -> int:
        return len(self._tags)
