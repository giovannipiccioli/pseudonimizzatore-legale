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

# Canonical person roles and the prefixes used with Config(roles=True).
ROLE_PREFIXES = {
    "persona": "Nominativo",
    "ricorrente": "Ricorrente",
    "resistente": "Resistente",
    "avvocato": "Difensore",
    "rappresentante": "Rappresentante",
    "giudice": "Giudice",
    "notaio": "Notaio",
    "testimone": "Testimone",
    "terzo": "Terzo",
    "locatore": "Nominativo",
    "locatrice": "Nominativo",
    "conduttore": "Nominativo",
    "conduttrice": "Nominativo",
}


def role_key(role: str) -> str:
    """Map the engine's role names and public role identifiers to the same key."""
    key = role.strip().casefold()
    return {"nominativo": "persona", "difensore": "avvocato"}.get(key, key)


# Data categories are independent of a reviewer's chosen placeholder.
DATA_PREFIXES = {prefix.casefold(): prefix for prefix in (
    "Dato", "CF", "IVA", "Iban", "Pec", "Email", "Telefono", "Documento",
    "Conto", "Numero_carta", "Albo", "Targa", "Data_nascita", "Indirizzo", "Luogo", "Numero",
    "Società", "Associazione", "Consorzio", "Banca", "Ditta",
)}

RESERVED = frozenset(ROLE_PREFIXES.values()) | frozenset(DATA_PREFIXES.values())
