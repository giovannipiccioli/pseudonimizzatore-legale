"""Shapes from the Corte dei conti, merito civile and TAR fixtures, and two whole decisions.

Each snippet is a shape a fixture showed, its names swapped for invented namebank
identities. Judges stay in clear. Private people and counsel go, and so does an identity
the text makes both a judge and counsel or a party (the privacy-first conflict rule).

Cases marked `gap` are known failures: this module is a benchmark as well as a
regression suite. They are strict xfails, so the run fails the day one starts passing,
and the marker should then come off to make it an ordinary regression case.
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
    # judges kept
    pytest.param(
        "Uditi, all'udienza pubblica del 12 luglio 2018, il consigliere\n"
        "relatore Arcangelo Monteleone e l'avv. Perpetua Lo Strano in rappresentanza\n"
        "dell'ente previdenziale.",
        ["Arcangelo Monteleone"], ["Perpetua Lo Strano"],
        id="corte_conti/21-lowercase-consigliere-relatore"),
    pytest.param(
        "Relatore nell'udienza pubblica del giorno 03/07/2008 il cons. Ornella Trevisanato "
        "e uditi per le parti i difensori come specificato nel verbale;",
        ["Ornella Trevisanato"], [],
        id="tar/21-il-cons"),
    pytest.param(
        "IL GIUDICE DELLE PENSIONI\n"
        "Primo referendario dott.ssa Gualtiero Piccinini\n"
        "ha pronunciato la seguente\nSENTENZA n. 1095/2003\n"
        "Uditi alla pubblica udienza del 21 ottobre 2003 il relatore primo referendario\n"
        "Gualtiero Piccinini, l'avv. Anastasia Belloccio ed il rappresentante "
        "dell'Amministrazione;",
        ["Gualtiero Piccinini"], ["Anastasia Belloccio"],
        id="corte_conti/14-primo-referendario"),
    pytest.param(
        "composta dai magistrati:\n"
        "dott. Clotilde Pontremoli\n\nPresidente\n"
        "dott. Augusto Corbellini\n\n\n\nConsigliere\n"
        "dott. Severino Ranieri Grimaldi\n\n\nReferendario (relatore)\n"
        "dott. Adelasia Scaramuzza\n\n\n\nReferendario\n"
        "dott. Ermenegildo Trentacoste\n\n\n\nReferendario\n\n"
        "nella adunanza pubblica del 13 ottobre 2010",
        ["Clotilde Pontremoli", "Severino Ranieri Grimaldi", "Adelasia Scaramuzza",
         "Ermenegildo Trentacoste"], [],
        id="corte_conti/15-vertical-panel"),
    pytest.param(
        "composta da: Dott. Celeste Bonaventura                           Presidente "
        "relatrice Dott.  Arcangelo Pizzigoni                 Consigliere\n"
        "Dott. Isotta Malinverni               Consigliere ha pronunciato la seguente\n"
        "SENTENZA",
        ["Celeste Bonaventura", "Arcangelo Pizzigoni", "Isotta Malinverni"], [],
        id="merito_civile/03_2020-tabular-bench"),
    pytest.param(
        "composta dai sigg.ri magistrati: dott.  Severino Ranieri Grimaldi\n"
        "PRESIDENTE dott.  Teodoro Scaramuzza   CONSIGLIERE REL. dott.  "
        "Ermenegildo Trentacoste    CONSIGLIERE ha\npronunciato la seguente sentenza",
        ["Severino Ranieri Grimaldi", "Teodoro Scaramuzza", "Ermenegildo Trentacoste"], [],
        id="merito_civile/04_2022-uppercase-roles"),
    pytest.param(
        "in persona dei Magistrati: dott.ssa Adelasia Scaramuzza\n"
        "                    Presidente dott. Clotilde Pontremoli"
        "                                         Consigliere dott.ssa "
        "Mirandolina Zangheratti\n                 Consigliere Relatore ha pronunciato "
        "la seguente\nSENTENZA",
        ["Adelasia Scaramuzza", "Clotilde Pontremoli", "Mirandolina Zangheratti"], [],
        id="merito_civile/04_2023-in-persona-dei-magistrati"),
    pytest.param(
        "con l'intervento dei sigg.\nmagistrati Dott. Augusto Corbellini Presidente Rel.\n"
        "Dott. Vittorina Mastrogiacomo Consigliere Dott.  Gualtiero Piccinini ha "
        "pronunciato la seguente\nSENTENZA",
        ["Gualtiero Piccinini"], [],
        id="merito_civile/01_2019-member-without-role"),
    pytest.param(
        "composta dai Magistrati:      1)\n"
        "Dott.ssa Federico Maria Sbaraglia ----------------------------------- Presidente"
        "           2) Dott. Teodoro Ventimiglia\n"
        "--------------------------------------- Consigliere",
        ["Federico Maria Sbaraglia", "Teodoro Ventimiglia"], [],
        id="merito_civile/02_2020-numbered-dashed-bench"),
    pytest.param(
        "riformare la sentenza n. 166/2019 resa dal Tribunale di Catanzaro - Giudice "
        "Dott.ssa Arcangelo Monteleone in data 1 febbraio 2019.",
        ["Arcangelo Monteleone"], [],
        id="merito_civile/04_2022-first-instance-judge"),
    # a judge who is also counsel or a party is removed
    pytest.param(
        "composta dai magistrati dr. Clotilde Pontremoli          Presidente "
        "dr. Augusto Corbellini            Consigliere rel.\n"
        "nella causa promossa da La Rotonda S.p.A.           appellante\n"
        "Prof. Avv. Clotilde Pontremoli contro: Banca Popolare\nappellata",
        ["Augusto Corbellini"], ["Clotilde Pontremoli"],
        id="merito_civile/05_2022-judge-also-counsel-prof-avv"),
    pytest.param(
        "composta dai seguenti Magistrati: 1) Dott. Vittorina Mastrogiacomo -Presidente "
        "2) Dott.ssa Ornella Trevisanato -Consigliere rel. ha emesso la seguente Sentenza\n"
        "rappresentati e difesi dall'avv. Amedeo Della Rovere, elettivamente domiciliati "
        "in Bari, via Roma n. 195 (c/o avv. Ornella Trevisanato)",
        ["Vittorina Mastrogiacomo"], ["Ornella Trevisanato", "Amedeo Della Rovere"],
        id="merito_civile/01_2023-judge-also-domiciliary-counsel"),
    pytest.param(
        "in persona dei Magistrati: dott.ssa Adelasia Scaramuzza Presidente dott. "
        "Ermenegildo Trentacoste Consigliere dott.ssa Mirandolina Zangheratti Consigliere "
        "Relatore ha pronunciato la seguente\nSENTENZA\n"
        "Il Comune di Reggello nulla deve nei confronti del Sig. Ermenegildo Trentacoste "
        "a qualsivoglia titolo.",
        ["Adelasia Scaramuzza", "Mirandolina Zangheratti"], ["Ermenegildo Trentacoste"],
        id="merito_civile/04_2023-judge-also-party"),
    pytest.param(
        "composta dai Sigg.: Dott. Celeste Bonaventura Presidente Dott. Augusto Corbellini "
        "Consigliere\nnella causa promossa da ATS Bergamo, rappresentata e difesa "
        "dall'Avv.to Celeste Bonaventura, domiciliatario giusta delega in atti.",
        ["Augusto Corbellini"], ["Celeste Bonaventura"],
        id="merito_civile/03_2022-judge-also-counsel"),
    # known gaps
    pytest.param(
        "Sezione per le controversie in materia di lavoro - composta dai Magistrati:      1)\n"
        "Dott.ssa Federico Maria Sbaraglia ----------------------------------- Presidente"
        "           2) Dott. Teodoro Ventimiglia\n"
        "--------------------------------------- Consigliere       3) Avv. Arcangelo "
        "Monteleone ----------------------------------------- G.A.\n"
        "relatore      ha emesso la seguente S E N T E N Z A",
        ["Arcangelo Monteleone"], [],
        marks=gap("a giudice ausiliario titled 'Avv.' is read as counsel; 'G.A. relatore' "
                  "is not a judicial role"),
        id="merito_civile/02_2020-giudice-ausiliario"),
    pytest.param(
        "APPELLANTE CONTRO\nIldegarda Quarantotto, Amedeo Della Rovere, ciascuno in "
        "qualità di coerede, tutti rappresentati e difesi dall'avv. Osvaldo Di Benedetto",
        [], ["Ildegarda Quarantotto", "Amedeo Della Rovere", "Osvaldo Di Benedetto"],
        marks=gap("respondents listed after 'CONTRO' are not read as a party list"),
        id="merito_civile/01_2023-respondents-after-contro"),
    pytest.param(
        "sul ricorso proposto da Ferruccio Malaspina, rappresentato e difeso dall'avv. "
        "Anastasia Belloccio,\ncontro\nOrtensia Vimercati, rappresentata e difesa "
        "dall'avv. Gervasio Spadaccini,\nper la riforma della sentenza",
        [], ["Ferruccio Malaspina", "Ortensia Vimercati"],
        marks=gap("a respondent after 'contro' is found in capitals or beside a codice "
                  "fiscale, not in mixed case"),
        id="respondent-after-contro-mixed-case"),
    pytest.param(
        "TRA\nRosalinda Pizzigoni, nata a Trani il 14.6.1951, rappresentata e difesa "
        "dagli avv.ti Ermenegildo Trentacoste e Isotta Malinverni;\n-Appellante-\nE\n"
        "Ortensia Vimercati, rappresentata e difesa dall'avv. Gervasio Spadaccini;\n"
        "-Appellata-",
        [], ["Rosalinda Pizzigoni", "Ortensia Vimercati"],
        marks=gap("the second party of a civil 'TRA … E …' heading is left in clear"),
        id="civil-heading-second-party"),
]


@pytest.mark.parametrize("text, keep, remove", CASES)
def test_judges_stay_and_private_people_go(text, keep, remove):
    out, _ = anonymize(text)
    assert [v for v in keep if not present(v, out)] == [], "judge removed"
    assert [v for v in remove if present(v, out)] == [], "private person left in clear"


# Whole decisions. A snippet checks one cue; a document checks how the mentions of one
# decision play together: the judge who is relatore in the heading and "dott.ssa X" in
# the signature, the party named with a birth date and later by bare surname. Both are
# invented from the fixture shapes, with namebank names, and annotated the way
# evaluation/corpus/README.md describes: must_remove lists every spelling that has to
# go, must_keep the judges and procedural values that must stay.

CORTE_DEI_CONTI_PENSIONI = """\
REPUBBLICA ITALIANA
IN NOME DEL POPOLO ITALIANO
LA CORTE DEI CONTI
SEZIONE GIURISDIZIONALE PER LA REGIONE CALABRIA
IL GIUDICE DELLE PENSIONI
Primo referendario dott.ssa Clotilde Pontremoli
ha pronunciato la seguente
SENTENZA n. 1095/2003
sul ricorso in materia di pensioni militari iscritto al n. 9321 del registro di segreteria,
proposto il 21.1.2003 da Ferruccio Malaspina, nato a Cosenza il 12.3.1951,
rappresentato e difeso dagli avv.ti Anastasia Belloccio e Gervasio Spadaccini, presso il cui
studio in Potenza è elettivamente domiciliato,
avverso il decreto di diniego del Ministero della Difesa.
Visti gli atti e i documenti di causa;
Uditi alla pubblica udienza del 21 ottobre 2003 il relatore primo referendario
Clotilde Pontremoli, l'avv. Anastasia Belloccio ed il rappresentante dell'Amministrazione
resistente dott. Ildegarda Quarantotto;
Ritenuto in
FATTO
Con il presente gravame il ricorrente, ex militare di leva, ha lamentato la mancata
corresponsione dell'equo indennizzo. Il Malaspina sostiene che l'infermità dipende da
causa di servizio.
DIRITTO
Il ricorso è fondato.
P.Q.M.
La Corte dei conti accoglie il ricorso.
Così deciso in Catanzaro il 21 ottobre 2003.
IL GIUDICE
f.to dott.ssa Clotilde Pontremoli
"""

MERITO_APPELLO_LAVORO = """\
Corte d'Appello di Bari - 1988/2020
REPUBBLICA ITALIANA IN NOME DEL POPOLO ITALIANO
La Corte d'Appello di Bari - Sezione Lavoro - composta dai Magistrati:
Dott.ssa Vittorina Mastrogiacomo        Presidente
Dott. Teodoro Ventimiglia                Consigliere
Dott. Augusto Corbellini                 Consigliere relatore
ha emesso la seguente
SENTENZA
nella controversia iscritta al n. 1833/2017 R.G.
TRA
Rosalinda Pizzigoni, nata a Trani il 14.6.1951, rappresentata e difesa dagli avv.ti
Ermenegildo Trentacoste e Isotta Malinverni, elettivamente domiciliata in Trinitapoli
presso lo studio dei difensori;
-Appellante-
E
Vetreria Sanmartino S.r.l., in persona del curatore fallimentare dott. Baldassarre Rocchetti,
rappresentata e difesa dall'avv. Gervasio Spadaccini;
-Appellata-
Con ricorso depositato il 18 novembre 2009 Rosalinda Pizzigoni adiva il Tribunale di Foggia,
in funzione di giudice del lavoro, deducendo di aver lavorato alle dipendenze della società.
Con sentenza n. 1432/2016 il Tribunale di Foggia, Giudice dott.ssa Clotilde Pontremoli,
rigettava la domanda. La Pizzigoni ha proposto appello.
MOTIVI DELLA DECISIONE
L'appello è infondato.
P.Q.M.
La Corte rigetta l'appello.
Bari, 9 dicembre 2020
Il Consigliere estensore                     Il Presidente
dott. Augusto Corbellini                     dott.ssa Vittorina Mastrogiacomo
"""

DOCUMENTS = [
    pytest.param(CORTE_DEI_CONTI_PENSIONI, {
        "must_remove": ["Anastasia Belloccio", "Ferruccio Malaspina", "Gervasio Spadaccini",
                        "Ildegarda Quarantotto", "Malaspina"],
        "must_keep": ["Clotilde Pontremoli", "LA CORTE DEI CONTI", "Ministero della Difesa",
                      "n. 1095/2003"],
    }, id="corte_conti-giudice-delle-pensioni"),
    pytest.param(MERITO_APPELLO_LAVORO, {
        "must_remove": ["Baldassarre Rocchetti", "Ermenegildo Trentacoste", "Gervasio Spadaccini",
                        "Isotta Malinverni", "Pizzigoni", "Rosalinda Pizzigoni"],
        "must_keep": ["Augusto Corbellini", "Clotilde Pontremoli", "Teodoro Ventimiglia",
                      "Vetreria Sanmartino S.r.l.", "Vittorina Mastrogiacomo", "n. 1432/2016",
                      "n. 1833/2017"],
    }, id="merito_civile-appello-lavoro"),
]


@pytest.mark.parametrize("text, gold", DOCUMENTS)
def test_annotated_document(text, gold):
    assert all(present(v, text) for v in gold["must_remove"] + gold["must_keep"])
    out, _ = anonymize(text)
    assert [v for v in gold["must_remove"] if present(v, out)] == [], "left in clear"
    assert [v for v in gold["must_keep"] if not present(v, out)] == [], "wrongly removed"
