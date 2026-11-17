"""The name a European case is cited by stays in clear, like its number."""
import pytest

from pseudonimizzatore_legale import Config, anonymize
from pseudonimizzatore_legale import patterns as P


def names(text):
    return [m.group(1) for pattern in P.CASE_NAMES for m in pattern.finditer(text)]


@pytest.mark.parametrize("text, expected", [
    ("Corte EDU, 12 agosto 2020, Mihai Toma c. Romania", ["Mihai Toma"]),
    ("sentenza 21 novembre 2011, Fogarty contro Regno Unito;", ["Fogarty"]),
    ("Grande Camera, sentenza Del Río Prada c. Spagna", ["Del Río Prada"]),
    ("sentenza 7 gennaio 2014, Cusan e Fazzo contro Italia", ["Cusan e Fazzo"]),
    ("Grande Stevens e altri contro Italia, del 4 marzo 2014", ["Grande Stevens"]),
    ("S.H. e altri c. Austria", ["S.H."]),
    ("Varvara c. Italia del 29 ottobre 2013", ["Varvara"]),
    ("causa C-348/16, Moussa Sacko contro Commissione Territoriale", ["Moussa Sacko contro Commissione Territoriale"]),
    ("cause riunite C-338/04, C-359/04 e C-360/04, Placanica, punto 46", ["Placanica"]),
    ("sentenza 11 ottobre 2007, C-443/06, Hollmann).", ["Hollmann"]),
])
def test_citations(text, expected):
    assert names(text) == expected


@pytest.mark.parametrize("text", [
    "ha proposto ricorso contro Italia Trasporti S.r.l.",   # a company, not the State
    "ai sensi dell'art. 3, c. 2, della legge n. 241 del 1990",
    "la sentenza C-617/10, punto 19, della Corte di giustizia",
    "Mario Rossi ha proposto ricorso contro l'Italia",
])
def test_not_citations(text):
    assert names(text) == []


def test_lexicon_name_in_a_citation_stays():
    text = ("La Corte EDU (sentenza 12 agosto 2020, Mihai Toma c. Romania) e la Corte di "
            "giustizia (causa C-348/16, Moussa Sacko) richiedono il contraddittorio. "
            "Il ricorso è proposto da Mario Bianchi.")
    out, _ = anonymize(text)
    assert "Mihai Toma c. Romania" in out
    assert "C-348/16, Moussa Sacko" in out
    assert "Mario Bianchi" not in out


def test_a_party_with_the_name_of_a_case_is_replaced_outside_the_citation():
    text = ("Il ricorso è proposto da Mihai Toma, nato a Roma. Si veda Corte EDU, "
            "Mihai Toma c. Romania.")
    out, _ = anonymize(text)
    assert out.count("Mihai Toma") == 1 and "Mihai Toma c. Romania" in out


def test_case_names_follow_keep_case_numbers():
    text = "Corte EDU, 12 agosto 2020, Mihai Toma c. Romania."
    out, _ = anonymize(text, Config(keep_case_numbers=False))
    assert "Mihai Toma" not in out
