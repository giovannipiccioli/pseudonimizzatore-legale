"""The forms added in November 2026 for the Corte costituzionale and Cassazione corpora,
under the configurations those corpora run with.

Each was a loss or a leak measured on a real corpus: European case names replaced in their
citations ("Nominativo_4 c. Italia"), the parties of "vertente tra X e Y" and of "proposto
da X e da Y" left in clear, "Corte E.D.U." read as a person's initials. The pattern tests
pin the shapes; these pin the outcome end to end, so a change in another detector (the
first-name list, the initials, the company rules) cannot quietly undo them. Party names
are invented; case names are those of published European judgments.
"""
import dataclasses

import pytest

from pseudonimizzatore_legale import Config, anonymize

#: src/cleaning/corte_costituzionale: only what a cue marks as private.
CORTE_COST = Config(companies=False, initials=False, first_names=False, keep_judges=True,
                    keep_case_numbers=True, sanitize=False)
#: The Cassazione consolidation: first-name list on, initials behind a cue, role tags.
CASSAZIONE = Config(profile="legal", companies="person_named", keep_judges=True,
                    keep_case_numbers=True, sanitize=True, verify=True, roles=True,
                    initials=True)
#: ilforo, which writes every private name as initials.
ILFORO = dataclasses.replace(CASSAZIONE, initials="all")

configs = pytest.mark.parametrize("config", [CORTE_COST, CASSAZIONE, ILFORO],
                                  ids=["corte_cost", "cassazione", "ilforo"])


def out(text, config):
    return anonymize(text, config)[0]


# ── European case names ─────────────────────────────────────────────────────

CITATIONS = [
    ("come affermato dalla Corte EDU nella sentenza 17 settembre 2009, Scoppola c. Italia, § 108",
     "Scoppola c. Italia"),
    ("Corte EDU, Grande Camera, 21 ottobre 2013, Del Río Prada contro Spagna",
     "Del Río Prada contro Spagna"),
    ("Corte EDU, 4 marzo 2014, Grande Stevens e altri contro Italia",
     "Grande Stevens e altri contro Italia"),
    ("Corte giust., 26 luglio 2017, C-348/16, Moussa Sacko contro Commissione Territoriale",
     "C-348/16, Moussa Sacko"),
    ("sentenza 6 marzo 2007, cause riunite C-338/04, C-359/04 e C-360/04, Placanica",
     "C-360/04, Placanica"),
]


@configs
@pytest.mark.parametrize("text, kept", CITATIONS, ids=[k for _, k in CITATIONS])
def test_a_european_case_name_stays_in_its_citation(config, text, kept):
    assert kept in out(text, config)


@configs
def test_a_party_named_like_a_case_is_still_replaced_outside_the_citation(config):
    text = ("ricorso proposto da Mario Scoppola, nato a Roma il 3 marzo 1950. "
            "Il ricorrente invoca Corte EDU, 17 settembre 2009, Scoppola c. Italia.")
    output = out(text, config)
    assert "Scoppola c. Italia" in output
    assert "Mario Scoppola" not in output


# ── parties of "vertente tra" and of "e da" / "e di" ────────────────────────

PARTIES = [
    ("nel procedimento civile vertente tra Capurso Anselmo e Zaccheri Mirko, iscritta al n. 316",
     ["Capurso", "Zaccheri"]),
    ("vertente tra i signori Giuseppa Vellani e Calogero Lunardi, veniva sollevata la questione",
     ["Vellani", "Lunardi"]),
    ("ricorso proposto da Alessandro Zanetto e da Raffaello Ludovico Zanetto avverso la sentenza",
     ["Zanetto", "Raffaello", "Ludovico"]),
    ("procedimento penale nei confronti di Giuseppe Brunì e di Cristoforo Ferrandi, imputati",
     ["Brunì", "Ferrandi", "Cristoforo"]),
    ("nei confronti di Morandino Vincenzo e Di Marzio Giuseppe, imputati",
     ["Morandino", "Marzio"]),
]


@configs
@pytest.mark.parametrize("text, gone", PARTIES, ids=[g[0] for _, g in PARTIES])
def test_every_party_of_a_list_is_replaced(config, text, gone):
    output = out(text, config)
    for word in gone:
        assert word not in output, (word, output)


@configs
def test_an_institution_in_a_party_list_stays(config):
    text = ("nel procedimento civile vertente tra Fantinelli Luigi e l'Istituto nazionale "
            "della previdenza sociale; nei confronti di Lia Sabatini e di Banca Agricola "
            "Mantovana S.p.A.")
    output = out(text, config)
    assert "Istituto nazionale della previdenza sociale" in output
    assert "Banca Agricola Mantovana S.p.A." in output
    assert "Fantinelli" not in output and "Sabatini" not in output


def test_vertente_tra_gives_its_parties_no_side():
    output = out("nel procedimento vertente tra Capurso Anselmo e Zaccheri Mirko.", CASSAZIONE)
    assert "Ricorrente" not in output and "Resistente" not in output


# ── sigle under the initials readings ───────────────────────────────────────

SIGLE = ("la sentenza della Corte E.D.U. e l'art. 6 della Convenzione E.D.U.; la stima "
         "dell'U.T.E., la decisione della C.T.C. e il P.V.C. notificato al C.S.M.")


@configs
def test_the_sigle_of_tax_and_convention_practice_stay(config):
    assert out(SIGLE, config) == anonymize(SIGLE, CORTE_COST)[0]


def test_ilforo_still_replaces_a_party_s_initials_next_to_a_sigla():
    output = out("Il ricorrente A.G. invoca l'art. 6 della Convenzione E.D.U. contro S.I.", ILFORO)
    assert "E.D.U." in output
    assert "A.G." not in output and "S.I." not in output
