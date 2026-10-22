"""Shapes from the documents benchmark (evaluation/DOCUMENTS_BENCHMARK.md), end to end.

Each probe is a short text in the shape a brief, a letter, a contract, an e-mail, a
minute or a form writes it, with invented names. `remove` is what must go, `keep` the
nearby text the same rule must leave alone: public bodies, judges, streets named after
people, procedural numbers.

Cases marked `gap` are known failures, strict xfails as in test_recall_shapes.py: the
run fails the day one starts passing, and the marker should then come off.
"""
import pytest
import regex as re

from pseudonimizzatore_legale import anonymize


def present(value, text):
    """Word-boundary containment, the corpus scorer's test."""
    return bool(re.search(rf"(?<![\p{{L}}\p{{N}}]){re.escape(value)}(?![\p{{L}}\p{{N}}])",
                          text))


def gap(reason):
    return pytest.mark.xfail(strict=True, reason=reason)


CASES = [
    # ── output damage: names that cross a line break ─────────────────────────────
    pytest.param(
        "Giudice: avv. Biagio Stomeo\nSegretario: sig.ra Anna Rita Perrone\n",
        ["Biagio Stomeo", "Segretario"], ["Anna Rita Perrone"],
        id="17-label-after-a-wrapped-name"),
    pytest.param(
        "rappresentato e difeso dagli avv. Gervasio Spadaccini ed Anastasia\n"
        "Belloccio, ed elettivamente domiciliato in Roma",
        [], ["Gervasio Spadaccini", "Belloccio"], id="counsel-name-wrapped-on-two-lines"),

    # ── output damage: public mailboxes ──────────────────────────────────────────
    pytest.param(
        "Istanza trasmessa via PEC a dp.treviso@pce.agenziaentrate.it e, per conoscenza, "
        "a protocollo@pec.comune.verona.it.",
        ["dp.treviso@pce.agenziaentrate.it", "protocollo@pec.comune.verona.it"], [],
        id="24-agency-pec-stays"),
    pytest.param(
        "Scrivere al funzionario mario.rossi@agenziaentrate.it oppure al difensore "
        "avv.giada.furlan@pec.ordineavvocatitreviso.it.",
        [], ["mario.rossi@agenziaentrate.it", "avv.giada.furlan@pec.ordineavvocatitreviso.it"],
        id="personal-mailbox-at-a-public-or-bar-domain-goes"),

    # ── output damage: judges outside the panel layout ───────────────────────────
    pytest.param(
        "TRIBUNALE ORDINARIO DI VERONA\nR.G. n. 4512/2025 – G.I. dott.ssa Maria Luisa "
        "Cavazzuti\n\nPRIMA MEMORIA INTEGRATIVA",
        ["Maria Luisa Cavazzuti", "4512/2025"], [], id="07-giudice-istruttore"),
    pytest.param(
        "AVVERSO la sentenza n. 412/2025 della Corte di giustizia tributaria di primo grado "
        "di Venezia, Sez. 3 (Pres. ed Est. dott. Aurelio Bortolami), pronunciata",
        ["Aurelio Bortolami"], [], id="02-pres-ed-est"),
    pytest.param(
        "Composizione del collegio:\nPresidente: dott. Ettore Mangialardo\n"
        "Giudice relatore: dott.ssa Giuseppina Calò\nGiudice: avv. Biagio Stomeo\n",
        ["Ettore Mangialardo", "Giuseppina Calò", "Biagio Stomeo"], [],
        id="17-lay-judge-titled-avv"),
    pytest.param(
        "Il G.I. ha poi sentito l'avv. Ferruccio Malaspina, difensore dell'attrice.",
        [], ["Ferruccio Malaspina"], id="counsel-after-a-g-i-sentence-goes"),

    # ── output damage: first names inside street and place names ─────────────────
    pytest.param(
        "AGENZIA DELLE ENTRATE – DIREZIONE PROVINCIALE DI BOLOGNA, con sede in Bologna, "
        "Viale Pietro Pietramellara 11\nIl sig. Pietro Malaspina ricorre.",
        ["Viale Pietro Pietramellara 11"], ["Pietro Malaspina"], id="01-street-named-after-a-person"),
    pytest.param(
        "Ricoverato presso l'Ospedale di Vittorio Veneto, poi a San Giorgio Canavese.",
        ["Ospedale di Vittorio Veneto", "San Giorgio Canavese"], [],
        id="21-town-and-saint-named-after-people"),

    # ── recall 1: addresses with no residence cue ────────────────────────────────
    pytest.param(
        "STUDIO LEGALE SCARDAMAGLIA\nVia Santo Stefano 38 – 40125 Bologna\n"
        "tel. 051 2961847",
        ["40125 Bologna"], ["Via Santo Stefano 38"], id="01-letterhead"),
    pytest.param(
        "Cordiali saluti\n\nAvv. Marco Ferretti\nSTUDIO LEGALE FERRETTI\n"
        "Via Altinate 64 - 35121 Padova\nTel. 049 660 2231",
        [], ["Via Altinate 64"], id="22-signature-block"),
    pytest.param(
        "Spett.le\nSig. Remo Tagliaferri\nVia Lorenteggio, 157\n20146 MILANO\n\nOGGETTO:",
        ["20146 MILANO"], ["Via Lorenteggio, 157"], id="12-addressee-block-cap-next-line"),
    pytest.param(
        "Kretschmer Sabine\nLeopoldstraße 112\n80802 München",
        [], ["Leopoldstraße 112"], id="25-foreign-address-line"),
    pytest.param(
        "il dott. Federico Ravera, con studio in Torino, Corso Vittorio Emanuele II n. 68, "
        "tel. 011 562 3381",
        [], ["Corso Vittorio Emanuele II n. 68"], id="30-con-studio-in"),
    pytest.param(
        "elettivamente domiciliata presso il suo studio in Verona, Stradone San Fermo 11\n"
        "– attrice –",
        [], ["Stradone San Fermo 11"], id="07-stradone"),
    pytest.param(
        "residente in Moncalieri (TO), Strada Revigliasco n. 154/7; residente in Napoli, "
        "Parco Comola Ricci 98, scala B",
        [], ["Strada Revigliasco n. 154/7", "Parco Comola Ricci 98"],
        id="30-29-house-number-and-parco"),
    pytest.param(
        "l'unità immobiliare sita in Roma, Via Gregorio VII n. 186, interno 9, e "
        "l'appartamento sito in Parma, Via Farini 17, int. 3",
        [], ["Via Gregorio VII n. 186", "Via Farini 17"], id="08-04-leased-property"),
    pytest.param(
        "L'anno duemilaventisei, il giorno sei del mese di febbraio,\n"
        "in Treviso, Via Indipendenza n. 7, nel mio studio.",
        ["il giorno sei del mese di febbraio"], ["Via Indipendenza n. 7"],
        id="27-notarial-studio"),
    pytest.param(
        "residente in Sendlinger Straße 15, 80331 München (Germania), e il fratello "
        "residente in Francia, 14 rue des Martyrs, 75009 Paris",
        ["Francia"], ["Sendlinger Straße 15", "14 rue des Martyrs"], id="09-31-foreign-street"),
    pytest.param(
        "Spett.le\nAgenzia delle Entrate\nDirezione Provinciale di Torino\nUfficio Controlli\n"
        "Corso Bolzano 30, 10121 Torino\n\nOggetto: istanza",
        ["Corso Bolzano 30"], [], id="30-agency-letterhead-stays"),
    pytest.param(
        "EDILFUTURA S.R.L.\nVia dell'Industria 12 – 37100 Verona",
        ["Via dell'Industria 12"], [], id="company-letterhead-stays"),
    pytest.param(
        "il Tribunale di Roma, sito in Viale Giulio Cesare 54, ha fissato l'udienza",
        ["Viale Giulio Cesare 54"], [], id="court-seat-after-property-cue-stays"),
    pytest.param(
        "rappresentati e difesi dall'avv. Ermenegildo Trentacoste, domiciliati ex art. 25 "
        "c.p.a. presso la Segreteria del Tar Lazio in Roma, via Flaminia, 189;",
        ["via Flaminia, 189"], ["Ermenegildo Trentacoste"], id="statutory-domicile-at-the-court-stays"),
    pytest.param(
        "Mario Malaspina, residente in Roma.\n\nAgenzia delle Entrate\nVia Giorgione n. 106",
        ["Via Giorgione n. 106"], ["Mario Malaspina"], id="cue-does-not-cross-a-blank-line"),

    # ── recall 2: birth dates and birthplaces ────────────────────────────────────
    pytest.param(
        "il sig. Ottavio Brocchi, nato a Lugo (RA) il 12/05/1968, e il sig. Settimio "
        "Carlucci, nato a Roma l'11/01/1966",
        [], ["12/05/1968", "11/01/1966"], id="01-08-province-and-l-apostrophe"),
    pytest.param(
        "Nato/a a   TREVISO          Prov.   TV       il   15/05/1955\n"
        "Residente a   SPRESIANO     Prov.   TV",
        [], ["TREVISO", "15/05/1955"], id="28-agency-form-fields"),
    pytest.param(
        "Fabio Lunardon, nato a Treviso il giorno 3 giugno 1968, e Primo Lunardon, nato a "
        "Treviso il giorno quindici marzo millenovecentoquaranta (15 marzo 1940), residente",
        [], ["3 giugno 1968", "quindici marzo millenovecentoquaranta", "15 marzo 1940"],
        id="27-il-giorno-and-date-in-words"),
    pytest.param(
        "il sig. Klaus Hoffmann, nato a Monaco di Baviera (Germania) il 12/12/1965, e il "
        "sig. Chen Jialin, nato a Wenzhou (Repubblica Popolare Cinese) il 08/09/1984",
        ["Germania", "Repubblica Popolare Cinese"],
        ["Monaco di Baviera", "12/12/1965", "Wenzhou", "08/09/1984"],
        id="09-03-foreign-birthplace"),
    pytest.param(
        "Il Presidente\nOrnella Trevisanato 2 ottobre 2019\nVISTO l'art. 100",
        ["2 ottobre 2019"], [], id="signature-date-after-a-surname-ending-in-nato"),
    pytest.param(
        "L'anno duemilaventisei, il giorno sei del mese di febbraio, in Treviso",
        ["il giorno sei del mese di febbraio"], [], id="deed-date-in-words-stays"),

    # ── recall 3: first names alone ──────────────────────────────────────────────
    pytest.param(
        "Egr. Avv. Paolo Gennari\nVia Roma 9\n37045 Legnago (VR)\n\nCaro Paolo,\n\nti scrivo"
        " in merito.\n\nUn caro saluto,\nLuca\n\nAvv. Luca Veronesi",
        ["Legnago"], ["Paolo", "Luca"], id="13-salutation-and-signature"),
    pytest.param(
        "Il ricorrente vive con la moglie e il figlio minore Tommaso. Allega gli estratti "
        "del conto cointestato con suo marito Jacopo; my brother Jens and I inherited.",
        [], ["Tommaso", "Jacopo", "Jens"], id="06-22-25-kinship"),
    pytest.param(
        "From: francesca granfione <f_granfione@libero.it>\n\nil codice fiscale di mio "
        "figlio gabriele (a carico al 100%) è questo.\n\ngrazie, francesca",
        [], ["francesca", "granfione", "gabriele"], id="23-lower-case-e-mail-thread"),
    pytest.param(
        "Mittente: Giorgia Esposito <g.esposito@studiorinaldi.it>\n\nIl CF l'ho inserito."
        "\n\nGiorgia\n\nGiorgia Esposito\nSegreteria – Studio Rinaldi Commercialisti",
        ["Studio Rinaldi Commercialisti"], ["Giorgia Esposito", "Giorgia"],
        id="23-display-name-and-signature"),
    pytest.param(
        "1) ZINANNI MARCELLO, nato a Parma il 02/04/1973;\nle quote spettano per un terzo "
        "ciascuno a Rosalba e Marcello e per un terzo alla vedova.",
        [], ["ZINANNI MARCELLO", "Marcello"], id="04-first-name-of-a-party"),
    pytest.param(
        "Egr. Avv. Paolo Gennari, presso la chiesa di San Paolo, ha incontrato "
        "Paolo Esposito.",
        ["San Paolo", "Paolo Esposito"], ["Paolo Gennari"],
        id="first-name-in-a-saint-or-another-name-stays"),
    pytest.param(
        "La sig.ra Rosa Malaspina indossava una camicia rosa. Il figlio del ricorrente "
        "era assente. Caro collega, ti scrivo.",
        ["rosa", "del ricorrente", "Caro collega"], ["Rosa Malaspina"],
        id="common-word-first-name-in-lower-case-stays"),

    # ── recall 4: identity documents and accounts ────────────────────────────────
    pytest.param(
        "identificato mediante passaporto tedesco n. C7HN4R2T9; please find attached my "
        "passport (n. C2T9L4M8R)",
        [], ["C7HN4R2T9", "C2T9L4M8R"], id="09-25-passport"),
    pytest.param(
        "Documento di riconoscimento   PATENTE DI GUIDA   n.   TV5338124P\nidentificata "
        "mediante patente di guida n. RM5123456K rilasciata da MIT-UCO",
        ["MIT-UCO"], ["TV5338124P", "RM5123456K"], id="28-18-driving-licence"),
    pytest.param(
        "copia del documento d'identità della sottoscritta (C.I. n. AY 4571203 rilasciata "
        "dal Comune di Napoli)",
        ["Comune di Napoli"], ["AY 4571203"], id="29-paper-identity-card"),
    pytest.param(
        "compiere ogni operazione sul conto corrente n. 000012345678; l'iban è "
        "IT 77 A 01030 03400 000063241578",
        [], ["000012345678", "IT 77 A 01030 03400 000063241578"],
        id="27-23-account-and-irregular-iban"),
    pytest.param(
        "patente di guida categoria B; conto corrente dedicato ai sensi della L. "
        "136/2010; codice IT 78 A 01030 03400 000063241578",
        ["136/2010", "IT 78 A 01030 03400 000063241578"], [],
        id="no-number-or-failed-check-stays"),

    # ── recall 5: professional register numbers ──────────────────────────────────
    pytest.param(
        "iscritto all'Albo dei Dottori Commercialisti e degli Esperti Contabili di Prato "
        "al n. 412/A; Ordine degli Ingegneri della Provincia di Padova n. 3471; iscritto "
        "al Registro dei Revisori Legali al n. 158243; iscritta al REA della CCIAA della "
        "Romagna al n. FO-312456",
        ["Prato", "Padova"], ["412/A", "3471", "158243", "FO-312456"],
        id="03-19-16-09-register-numbers"),
    pytest.param(
        "Il Consiglio dell'Ordine degli Avvocati di Roma, delibera n. 12 del 2024; "
        "iscritto all'Ordine degli Avvocati di Roma, ricorso n. 1234/2023; punto n. 3 "
        "dell'ordine del giorno; pubblicato all'albo pretorio al n. 345",
        ["12", "1234/2023", "3", "345"], [], id="act-and-case-numbers-stay"),

    # ── still open ───────────────────────────────────────────────────────────────
    pytest.param(
        "Resto in attesa di un tuo riscontro, anche telefonico (348 9102774), o al "
        "numero 347 1189023.",
        [], ["348 9102774", "347 1189023"], id="13-14-phone-without-a-cue",
        marks=gap("a phone needs its cue; a bare mobile number is not read")),
    pytest.param(
        "Tel. +49 89 2180 4471 – Per ogni comunicazione: +33 6 12 47 88 03.",
        [], ["+49 89 2180 4471", "+33 6 12 47 88 03"], id="25-31-foreign-phone",
        marks=gap("only the +39 prefix is read, with or without a cue")),
    pytest.param(
        "ditta individuale \"EMPORIO ORIENTE di Chen Jialin\", con sede in Prato, Via "
        "Pistoiese 288, e il titolare esercente l'attività di bar-tabacchi in Legnago "
        "(VR), Corso della Vittoria 33",
        [], ["Via Pistoiese 288", "Corso della Vittoria 33"], id="03-05-sole-trader-seat",
        marks=gap("'con sede' is a company's registered office and stays; a sole "
                  "trader's seat is a person's address but reads the same")),
    pytest.param(
        "danni al veicolo, come da preventivo della Carrozzeria Pavan Sergio: euro 4.380",
        [], ["Pavan Sergio"], id="14-uncued-sole-trader",
        marks=gap("a sole trader named without 'ditta individuale' has no cue")),
    pytest.param(
        "avv. Giada Furlan\nStudio Legale Furlan & Bortoluzzi\nwww.studioferretti.it",
        [], ["Bortoluzzi", "www.studioferretti.it"], id="24-22-second-partner-and-website",
        marks=gap("only the first name after 'studio legale' is read, and websites "
                  "are not read at all")),
    pytest.param(
        "Condomino                     Unità   Millesimi   Presenza\n"
        "Hu Weiming e Zhang Li          A/3     47,80       presente\n"
        "Eredi Lunardi                  B/2     55,00       assente\n",
        [], ["Hu Weiming", "Zhang Li", "Lunardi"], id="15-table-rows",
        marks=gap("names in a table have no cue, and 'Eredi' needs a full name")),
    pytest.param(
        "Sono presenti i soci:\n  • Corradini Elena, titolare di una quota pari al 35%",
        [], ["Corradini Elena"], id="16-surname-first-bullet",
        marks=gap("surname-first is read only in ALL CAPS")),
    pytest.param(
        "la sig.ra Maria Esposito Abate, C.F. SPSMRA70A41F839X, chiede. La sig.ra "
        "Esposito ha percepito il canone.",
        [], ["Esposito"], id="18-common-word-part-of-a-double-surname",
        marks=gap("a common-word token never propagates alone, even after a title")),
    pytest.param(
        "Egr. Avv. Paolo Gennari e Avv. Paolo Righetti,\n\nCaro Paolo,\n\nti scrivo.",
        [], ["Caro Paolo"], id="first-name-of-two-people",
        marks=gap("a first name two detected people share is not attributed to either")),
]


@pytest.mark.parametrize("text, keep, remove", CASES)
def test_probe(text, keep, remove):
    assert all(present(v, text) for v in keep + remove)
    out, _ = anonymize(text)
    assert [v for v in remove if present(v, out)] == [], "left in clear"
    assert [v for v in keep if not present(v, out)] == [], "wrongly removed"


@pytest.mark.parametrize("text, expected", [
    # The label and its line break used to be deleted with the "name".
    ("Giudice: avv. Biagio Stomeo\nSegretario: sig.ra Anna Rita Perrone",
     "Giudice: avv. Biagio Stomeo\nSegretario: sig.ra Nominativo_1"),
    ("rappresentato e difeso dall'avv. Mario Malaspina\nIl ricorrente insiste.",
     "rappresentato e difeso dall'avv. Nominativo_1\nIl ricorrente insiste."),
    ("Contribuente\nMario Malaspina RSSMRA80A01H501U",
     "Contribuente\nNominativo_1 CF_1"),
    # "CARLO⏎Rossi" was a phantom person, which gave the party's surname a second tag.
    ("Presidente: VERDI CARLO\nRossi insiste. Il sig. Mario Rossi ricorre.",
     "Presidente: VERDI CARLO\nNominativo_1 insiste. Il sig. Nominativo_1 ricorre."),
    # A phone number stays on its line.
    ("Tel. 0422 541 337\n12 marzo 2026", "Tel. Telefono_1\n12 marzo 2026"),
])
def test_line_breaks_are_not_eaten(text, expected):
    assert anonymize(text)[0] == expected
