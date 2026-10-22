"""Pseudonym allocation for Italian legal documents.

Tags name the *kind* of data, never the person:

    Nominativo_1, Società_1, CF_1, Email_1, Pec_1, IVA_1, Iban_1, Telefono_1,
    Indirizzo_1, …

and, with ``Config(roles=True)``, a person's role: Ricorrente_1, Resistente_1,
Difensore_1. Roles help a reader follow a decision, but they are inferred, so the
default keeps the plainer tag.

The obvious alternative — initials, "Mario Rossi" → "M. R." — is worse on every axis
that matters here. Initials still carry information (the Garante treats them as
pseudonymous, not anonymous), they collide constantly at corpus scale, and the
disambiguation they then need ("M. R. (2)") reads badly. A tag says nothing about who
the person is.

**Counters restart at 1 for every document.** Consistency is per document by design, so
`Nominativo_1` in one file has no relationship to `Nominativo_1` in another. Two
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
    """Allocates one stable tag per distinct entity, per document.

    `prior` is an earlier `mapping()` of the same document. Its entities keep their
    tags and new ones are numbered after them, so a review edit never renumbers the
    rest:

    >>> registry = Registry({"Mario Rossi": "Nominativo_2"})
    >>> registry.tag("Nominativo", "Anna Verdi"), registry.tag("Nominativo", "MARIO ROSSI")
    ('Nominativo_3', 'Nominativo_2')
    """

    def __init__(self, prior: dict[str, str] | None = None) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._tags: dict[tuple[str, str], str] = {}      # (role, key) -> tag
        self._display: dict[tuple[str, str], str] = {}   # (role, key) -> readable text
        self._prior: dict[tuple[str, str], str] = {}
        for value, tag in (prior or {}).items():
            role, _, number = tag.rpartition("_")
            if number.isdigit():
                self._prior[(role, value.casefold())] = tag
                self._counters[role] = max(self._counters[role], int(number))

    def tag(self, role: str, value: str, fixed: str | None = None) -> str:
        """Return the tag for `value`, allocating a new one on first sight.

        Entities are deduplicated case-insensitively — the same e-mail address written
        two ways is one entity and gets one tag — while the report keeps the first
        spelling actually seen, so it stays readable. `fixed` is a tag chosen by the
        reviewer; it consumes no number.
        """
        key = (role, value.casefold())
        existing = self._tags.get(key)
        if existing is not None:
            return existing
        tag = fixed or self._prior.get(key)
        if tag is None:
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
