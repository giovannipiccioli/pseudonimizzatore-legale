# Document benchmark

> Recall of `pseudonimizzatore_legale` on documents professionals pseudonymize
> themselves (briefs, contracts, letters, minutes, expert reports, e-mails, powers of
> attorney, requests to the Agenzia delle Entrate), measured on 2026-10-20 on
> [`corpus_documents/`](corpus_documents/README.md) with the engine of the commit that
> adds this file. Read §6 before quoting any number.

## 1. Results

31 legal documents, 394 identities (153 names, 139 identifiers, 59 addresses, 43 birth
data), 177 protected values. `narrativa` (4 public-domain excerpts, 31 identities) is
reported apart.

| Configuration | Complete entities | Names | Identifiers/other | Surface recall | Span precision LB | Char. precision LB | Protected kept | Complete docs | Time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `first_names=False` | 290/394 (73.6%) | 126/153 (82.4%) | 164/241 (68.0%) | 382/496 (77.0%) | 473/527 (89.8%) | 89.5% | 171/177 | 1/31 | 0.2 s |
| default | 306/394 (77.7%) | 136/153 (88.9%) | 170/241 (70.5%) | 403/496 (81.2%) | 504/565 (89.2%) | 89.0% | 169/177 | 2/31 | 0.3 s |
| default + NER XXL, t=0.3, CPU | 315/394 (79.9%) | 145/153 (94.8%) | 170/241 (70.5%) | 415/496 (83.7%) | 517/586 (88.2%) | 86.2% | 168/177 | 3/31 | 8.4 s |

By kind, default: names 136/153, identifiers 122/139, **addresses 26/59, birth data
22/43**. NER changes only the name count (to 145).

Complete-entity recall by family:

| Family | `first_names=False` | default | + NER |
|---|---:|---:|---:|
| contratto | 79.0% | 83.9% | 83.9% |
| diffida | 77.8% | 77.8% | 77.8% |
| email | 60.4% | 68.8% | 79.2% |
| istanza | 73.5% | 73.5% | 73.5% |
| memoria | 74.2% | 87.1% | 90.3% |
| perizia | 76.9% | 76.9% | 76.9% |
| procura | 67.6% | 70.3% | 70.3% |
| ricorso | 77.8% | 82.5% | 82.5% |
| verbale | 71.4% | 74.3% | 82.9% |
| *narrativa* | *9.7%* | *16.1%* | *77.4%* |

**Against the 124 decisions** (re-measured the same day on the same tree): default 472/488
complete entities (96.7%), names 357/373 (95.7%), identifiers/other 115/115, 111/124
complete documents, 720/726 kept; `first_names=False` 448/488 and 97/124.

Much of that gap is policy, because this gold also counts studio addresses, birth data,
ID documents and register numbers. Restricted to what the decision gold annotates
(names plus CF, P.IVA, e-mail, PEC, phone and IBAN), the documents score 251/273
(91.9%) with 19/31 complete documents (61%), against 96.7% and 89.5% on decisions. With
NER, 260/273 (95.2%) and 22/31. Names alone: 88.9% against 95.7%.

The review flag fires on 29/31 documents (TP/FN/FP/TN 27/2/2/0), so here too it carries
no signal. The two leaky documents it passes are a minor's first name (06) and a studio
address (26).

## 2. Leaks by shape (default, legal documents)

Status against the 2026-10-16 known-gap list: **closed** means no leak on this corpus,
**open** means it still leaks, **new** means the shape is not on the list.

| Shape | Leaked | Status | Examples (document) |
|---|---:|---|---|
| studio, letterhead or signature address | 20/23 | new | `Via Santo Stefano 38 – 40125 Bologna` letterhead (01), `con studio in Torino, Via Principe Amedeo 21` (30), `Via Toledo 256, 80134 Napoli` signature (23) |
| birth date | 14/25 | new | `nato a Lugo (RA) il 12/05/1968` (01; the province in brackets breaks the cue), `nato a Roma l'11/01/1966` (08), form field `Nato/a a TREVISO Prov. TV il 15/05/1955` (28) |
| birth date as text or in words | 4/5 | new | `il giorno 3 giugno 1968`, `quindici marzo millenovecentoquaranta` (27) |
| address without CAP | 4/23 | open (mostly closed) | `Parco Comola Ricci 98` (29), `Strada Revigliasco n. 154/7` (30), `abitazione sita in Verona, Via …` (07), `appartamento sito in Parma, Via Farini 17` (04) |
| leased or sold property, sole-trader seat | 5/7 | new | `Via Duca d'Aosta n. 7` (09), `Corso della Vittoria 33` (05) |
| addressee block, CAP on the next line | 2/2 | new | `Via Lorenteggio, 157⏎20146 MILANO` (12) |
| foreign address | 2/3 | new | `Sendlinger Straße 15` (09), `14 rue des Martyrs` (31) |
| first name alone, minor, lowercase | 10/15 | new | `Caro Paolo,`, signature `Luca` (13), `suo marito Jacopo` (22), `il figlio minore Tommaso` (06), `mio figlio gabriele` (23) |
| professional register number | 5/5 | new | `iscritto … al n. 412/A` (03), `Registro dei Revisori Legali al n. 158243` (16) |
| phone without a `tel.` cue | 4/24 | new | `anche telefonico (348 9102774)` (13), `+49 89 2180 4471` (25) |
| passport, driving licence, paper ID card | 5/5 | new (sibling of CIE) | `passaporto tedesco n. C7HN4R2T9` (09), `patente di guida n. RM5123456K` (18), `C.I. n. AY 4571203` (29) |
| CIE, also spaced | 0/4 | closed | |
| CF omocodic, spaced, lowercase | 0/4 | closed | `P V N L C N 5 5 E 5 5 L 4 0 7 Z` (28) and `grnfnc79r62f839q` (23) removed |
| foreign IBAN | 0/3 | closed | DE and FR grouped |
| Italian IBAN with irregular spacing, account number | 2/2 | new | `IT 77 A 01030 03400 000063241578` (23), `conto corrente n. 000012345678` (27) |
| title + bare surname, incl. `il sig. <Cognome>` | 1/41 | closed for `sig.` | `dott.ssa Amodio` (23) still leaks: the known `dott.` xfail |
| `ditta individuale di X` | 1/7 | closed when cued | uncued `Carrozzeria Pavan Sergio` (14) leaks |
| `studio legale <Nome>` | 1/4 | closed for the first name | second partner `Studio Legale Furlan & Bortoluzzi` (24) |
| birthplace | 4/14 | open for foreign towns and forms | `Wenzhou`, `Monaco di Baviera`, form fields `TREVISO`, `CONEGLIANO`; common-word towns `Nove`, `Paese` removed |
| other names | 8 | new | `Hu Weiming`, `Zhang Li`, `Hu` in a condominium table (15), `Eredi Lunardi` (15), `Corradini Elena` bullet (16), `la sig.ra Esposito` for `Esposito Abate` (18), `Mittente: Giorgia Esposito` (23) |
| website carrying the surname | 1/1 | new | `www.studioferretti.it` (22) |

Full names after a cue (75), counsel, notaries, officials, common-word surnames (Porta,
Gallo, Leone, Greco), apostrophe surnames, presidents of private meetings, heirs' lists
and hyphen- or slash-joined surnames (`Dalmonte-Siboni`, `Coppola/Tagliaferri`) were
all removed.

On `narrativa` the default removes 5/31 identities. Every first name, nickname and
`l'Olivi` survives. NER raises that to 24/31. The seven left even with NER are
frequently repeated first names (`Lorenzo`, `Michele`, `Guido`, `Ada`, `Maria`, `Luca`,
`Lia`), where one missed occurrence out of many fails the whole identity.

## 3. Collateral damage

Default: 8 protected values lost on legal documents (6 of them also with
`first_names=False`), plus `Madonna Santissima` in `narrativa`.

- **Agency PEC addresses** are replaced like any e-mail: `dp.treviso@pce.agenziaentrate.it`
  (24), plus the Naples and Turin ones (29, 30). An Agency address is not personal data,
  and removing it makes the request unusable.
- **Judges outside the panel layout**: `G.I. dott.ssa Maria Luisa Cavazzuti` (07),
  `(Pres. ed Est. dott. Aurelio Bortolami)` (02), `Giudice: avv. Biagio Stomeo` (17).
- **Span bug** (17): `Giudice: avv. Biagio Stomeo⏎Segretario: …` is detected as one
  person `'Biagio Stomeo\nSegretario'`. The output reads `Giudice: avv. Nominativo_1:
  sig.ra Nominativo_2`, so a line break and a label are deleted. This is wrong output,
  not just over-removal.
- **First-name list, streets and places named after people**: `Viale Pietro Pietramellara 11`
  becomes `Viale Nominativo_1 11` (01, the Agency's own address), `Ospedale di Vittorio
  Veneto` becomes `Ospedale di Nominativo_1` (21), and `Via Ippolito Nievo n. 47` becomes
  `Via Nominativo_2 n. 47` in a probe. The street cases also leave half an address
  behind.

NER adds `Comune di Marostica` (20). In `narrativa` it adds the explicit judge
`il giudice D'Andrea`, `San Cristoforo`, `Plutarco`, `Licurgo` and `Timoleone`.

## 4. Does the app need NER by default?

**Yes, for names, but it is not what makes a document safe.**

- Names are the shape where client documents differ most from decisions: e-mail
  headers, salutations, signatures by first name, children, tables. NER raises complete
  names from 88.9% to 94.8% (e-mail from 68.8% to 79.2%, verbali from 74.3% to 82.9%). On
  uncued prose it is the difference between 16% and 77%. The `narrativa` result is the
  strongest evidence here, because the author of §6's bias did not write that text.
- It costs about 0.25 s per document on CPU (8.4 s for 35 documents including the model
  load, against 0.3 s), a 421 MB model, and one extra lost public body on legal
  documents. In
  prose it also removes classical names and a judge. That is acceptable for an
  interactive, one-document, review-first app, provided NER-only proposals are visibly
  marked so a keep is one click.
- NER changes nothing for addresses, birth data, ID documents or register numbers.
  Those are 71 of the 79 identities still missed with NER, and the reason only 3/31
  documents come out complete. Until §5's fixes land, the review panel has to highlight
  street-plus-number lines and dates, whatever the NER setting.

Caveat: the name gain is 9 identities on a model-written corpus (§6). Re-check it on
real uploads before treating it as settled.

## 5. Top engine fixes by expected recall gain

Gain = identities that become fully removed if every leak of the listed shapes
disappears, default configuration, 31 legal documents. Each figure is an upper bound.
Ranked by identities. The last column is complete documents with this fix and all those
above it (baseline 2/31). All five together reach 381/394 (96.7%, the decision corpus's
level) and 21/31 complete documents.

| # | Fix | Identities | Complete docs, cumulative | Main shapes |
|---|---|---:|---:|---|
| 1 | **Addresses without a residence cue**: a street-type word (also `Strada`, `Stradone`, `Parco`, `Riviera`, `Borgo`) + name + house number (`154/7`, `112/B`, `n. 42`) + optional `– CAP Città`, in letterheads, signature blocks, `con studio in X,`, addressee blocks, `sito in`; foreign `Straße 15` / `14 rue …`; tolerate `(PR)` between town and street; keep the public-body guard (`registered-office-stays`) | +33 | 8 | address-studio, -no-cap, -property, -business, -cap-next-line, -foreign |
| 2 | **Birth data**: `nato/a a <Town> (<PR or country>) il`, `l'<date>`, `il giorno <date>`, dates in words, the `Nato/a a X Prov. Y il Z` form, foreign birthplaces | +21 | 12 | birth-date, -text, -words, birthplace-* |
| 3 | **First names alone**: reuse a first name already resolved to a removed person (`Caro Paolo` after `Paolo Gennari`, signature `Luca`, `Marcello`), plus salutation (`Caro/Gentile/Ciao X,`) and kinship cues (`suo marito X`, `figlio (minore) X`, `my brother X`) | +9 (+4 with NER) | 14 | first-name-only, minor, lowercase, e-mail display name |
| 4 | **ID documents and accounts**: number after `passaporto n.`, `patente (di guida) n.`, `C.I. n.` / `carta d'identità n.` (paper format `AY 4571203`), `conto corrente n.`; Italian IBAN with irregular spacing | +7 | 17 | passport, patente, id-card-paper, bank-account, iban-it-irregular |
| 5 | **Register numbers**: `iscritto all'Albo/Ordine/Collegio/Registro … al n. X`, `REA … n.` | +5 | 21 | albo-number |

Next in line: phones in prose and international formats (+4 identities, 24 complete
documents cumulatively; `+33 6 …`, `(348 …)`); the residual name shapes in §2 (+8
together, but no single fix).

Correctness fixes to do regardless of rank, because they damage output:

- (a) the person span crossing a line break (§3);
- (b) allow-list public-administration e-mail domains (`pce.agenziaentrate.it`,
  `agenziaentrate.it`, `gov.it`, …);
- (c) judicial cues `G.I.`, `Pres. ed Est.`, `Giudice: avv.`;
- (d) no first-name seed inside a street or place name (`Via|Viale|Piazza|Corso|Ospedale
  di <First> <Word>`).

## 6. Bias and limits

- **The author knew the patterns.** The model that wrote documents 01–31 and every gold
  label had read the known-gap probes in `tests/test_recall_shapes.py` first, and
  deliberately included those shapes. The result therefore over-represents them, under
  their closed and open forms alike. It cannot contain the shapes the author did not
  think of, and real uploads will have some.
- **Text that is too clean.** There is no PDF or OCR damage, no repeated page headers, no
  scanned forms, no tables with real column alignment, no tracked changes. Names are
  unusual but well formed, and every CF, IBAN and P.IVA is valid. Real documents should
  score lower for names, not higher.
- **Shape mix.** Shapes follow the author's choices, not real frequencies: nearly every
  document has a letterhead, so the 23 studio addresses weigh more here than they may in
  practice.
- **Policy.** This gold is wider than the decision gold (§1). The per-shape tables let a
  reader drop a debatable shape: register numbers, Agency officials, studio addresses.
- **Same annotator for text and gold.** Annotation blind spots are correlated with
  writing blind spots. Quasi-identifiers deliberately left unannotated (cadastral data,
  policy numbers, death dates, building addresses, health data) are not measured at all.
- **Size.** 31 documents. One document moves the complete-document rate by 3 points.

## 7. Reproduce

```bash
python evaluation/score_documents.py              # three configurations, per-document lines
python evaluation/score_documents.py -v email     # one family, with leak context
python evaluation/score_documents.py --no-ner --quiet
```
