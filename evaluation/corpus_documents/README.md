# Document corpus

> Non-decision documents a professional pseudonymizes before sharing them: 31 hand-written
> legal documents in nine families, plus four public-domain literary excerpts. Scored by
> [`../score_documents.py`](../score_documents.py); results and analysis are in
> [`../DOCUMENTS_BENCHMARK.md`](../DOCUMENTS_BENCHMARK.md).

## 1. Families

```
corpus_documents/
├── ricorso/     4  ricorso CGT, atto di appello, sole trader, heirs
├── memoria/     3  memoria illustrativa, Agency controdeduzioni, civil 171-ter memoria
├── contratto/   4  residential lease, preliminare, lawyer engagement letter, commercial lease
├── diffida/     3  diffida, riservata between lawyers, claim letter to an insurer
├── verbale/     4  condominium, S.r.l. shareholders, CGT conciliation, Agency contraddittorio
├── perizia/     3  CTU, sworn valuation, medico-legal report
├── email/       4  client–lawyer thread, accountant thread, PEC receipt, English/Italian thread
├── procura/     3  procura alle liti, notarial procura speciale, Agency delega form
├── istanza/     3  autotutela, accertamento con adesione, AIRE refund
└── narrativa/   4  Pirandello, Verga, Foscolo, Svevo — uncued-name stress test, outside TOTAL
```

## 2. Fixture pair

The format is [`../corpus/README.md`](../corpus/README.md)'s: `name.txt` plus
`name.gold.json` with `source`, `note`, `config`, `must_remove`, `must_keep`. Each file
also carries:

- `must_remove_entities` — explicit identity groups (`kind`, `role`, `values`), needed
  because family members share surnames. `must_remove` is the flat list of the same values.
- `kind` — `name`, `identifier`, `address` or `birth`. `metrics.score_output` counts
  anything other than `name` as "identifiers/other"; the scorer also reports each kind.
- `shapes` — one tag per surface (`address-studio`, `cf-spaced`, `first-name-only`, …),
  which the scorer uses to group leaks.

Surfaces are written as the scorer sees them: after `sanitize` and `normalize_quotes`, so
with straight apostrophes even where the text has curly ones.

## 3. Annotation policy

Privacy-first, wider than the decision gold, and tagged so a reader can leave out a
debatable shape:

- **removed**: private people in any role, including counsel, experts, notaries,
  witnesses, minors, people known only by a first name or nickname, and named Agency
  officials (`public-official`). Also personal identifiers (CF, P.IVA of individuals and
  sole traders, IBAN and account numbers, ID documents, plates, phones, e-mails, a website
  carrying a surname, professional register numbers), residential, studio, sole-trader
  and leased-property addresses, birth dates, and birthplaces when the town does not
  appear elsewhere in the document;
- **kept**: courts and named judges (including a lay judge titled `avv.`), public bodies
  with their addresses and PEC, norms, case numbers, Agency act and protocol numbers;
- **neither**: companies (the default `companies=False` keeps them, so a surname inside
  a company name is not annotated), towns of residence, court clerks, cadastral data,
  policy numbers, death dates and health data. These remain quasi-identifiers the review
  step has to judge.

## 4. Sources and bias

Documents 01–31 were written on 2026-10-20 by a language model that had read the
engine's known-gap probes (`tests/test_recall_shapes.py`) beforehand. Every person,
company and identifier is invented. CF, IBAN and P.IVA values have valid check
characters, so a miss is never caused by a malformed fake. The text is cleaner than
real uploads: no OCR noise, no repeated page headers, no scanned forms. The shape mix
follows the author's choices: almost every document has a letterhead, for example.
Treat the numbers as a lower bound on how much is missing, not as an estimate of
recall on real documents.

Documents 32–35 are verbatim excerpts of public-domain works, taken from it.wikisource.org
transcriptions (CC BY-SA 3.0) with the page markers removed. The work and page for each
are in the `source` field. Only the annotation is by the same author.
