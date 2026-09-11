# Evaluation corpus

This directory contains 124 Italian legal-decision fixtures from seven source families.
The layout and prose come from real decisions, but every detected natural-person name
was replaced with an invented identity before the fixtures were committed. The source
archives themselves are not part of this repository.

| Source family | Documents | Main structural variation |
|---|---:|---|
| BDGT | 23 | tax panels, role fields, counsel/contact blocks |
| Cassazione | 25 | surname-first headers, prose aliases, old initials-only feeds |
| CGUE | 8 | low-structure opinions and organization-heavy text |
| Consiglio di Stato | 16 | administrative headings, party and counsel lists |
| TAR | 21 | mass appeals listing many applicants, counter-interested parties, older judge titles |
| Corte dei conti | 15 | accounting/pension decisions and irregular panels |
| Merito civile | 16 | PDF extraction, mixed layouts and masked initials |

## Fixture pair

Each `name.txt` has a `name.gold.json` beside it:

```json
{
  "source": "archive reference (identities replaced)",
  "note": "why this shape is useful",
  "config": {},
  "must_remove": ["MALASPINA FERRUCCIO", "Ferruccio Malaspina", "Malaspina"],
  "must_keep": ["ROSSI MARIO", "n. 274/2023"]
}
```

`must_remove` lists surface assertions. `evaluation.metrics` groups aliases into an
identity; all listed spellings and repeated occurrences must disappear for that entity
to pass. New hand-authored fixtures may instead use explicit groups:

```json
{
  "must_remove_entities": [
    {"kind": "name", "values": ["Mario Rossi", "Rossi"]}
  ],
  "must_keep": []
}
```

If both formats occur, legacy values not covered by an explicit group are scored as
additional singleton entities rather than silently disappearing from entity recall.

Gold follows the runtime policy:

- explicit judges and public prosecutors are kept;
- private people and counsel are removed;
- a complete identity with both judicial and strong private-role evidence is removed;
- public institutions, places and procedural identifiers may be keep sentinels.

There are no implementation-derived “known gap” exemptions. Every annotated residual
is printed as a leak by the scorer.

## Safety of committed fixtures

The builder uses two passes:

1. publisher placeholders/initial runs are filled with identities from a fixed invented
   name bank, and so are two shapes the second pass loses track of: the list of
   applicants of a mass appeal, and every codice fiscale or personal e-mail address;
2. remaining person clusters are de-identified while their capitalization, order and
   bare-surname variants are preserved.

`check_fixtures.py` rejects a generated document when a person-shaped value, codice
fiscale or personal e-mail address outside the invented bank remains, and the builder
drops that document rather than commit a possible real identity. The check shares the
de-identifier's heuristics and so its blind spots — a name made only of common words, a
witness called by bare surname — so after adding fixtures also run `ner_audit.py`,
which asks an Italian NER model for every person outside the bank. Read its list and
the new text before committing.

Do not replace these files with raw decisions or add real names manually.

## Rebuilding

Normal scoring uses the committed files and needs no private data. Rebuilding requires
one or more archive roots, provided only through environment variables:

```text
PSEUDONIMIZZATORE_LEGALE_CASSAZIONE_ROOT
PSEUDONIMIZZATORE_LEGALE_BDGT_ROOT
PSEUDONIMIZZATORE_LEGALE_GIUSTIZIA_AMMINISTRATIVA_ROOT
PSEUDONIMIZZATORE_LEGALE_TAR_TXT_ROOT      TAR decisions as plain text, <year>/<name>.txt
PSEUDONIMIZZATORE_LEGALE_CGUE_ROOT
PSEUDONIMIZZATORE_LEGALE_CORTE_CONTI_ROOT
PSEUDONIMIZZATORE_LEGALE_MERITO_CIVILE_ROOT
```

Run:

```bash
python evaluation/build_corpus/build_fixtures.py --help
python evaluation/build_corpus/build_fixtures.py
python evaluation/build_corpus/check_fixtures.py
python evaluation/build_corpus/ner_audit.py
python evaluation/score_corpus.py
```

The scripts contain no developer-specific absolute paths. Generated output is written
back to this directory, so review the diff before committing it.
