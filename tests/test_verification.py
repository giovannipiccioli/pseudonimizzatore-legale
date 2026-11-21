"""The name-shape scan of the review step.

`verify` reports every run of two to four capitalised words left in the output, because
it cannot tell a name from a heading. These cases pin what it may drop and, as important,
what it must go on reporting: a phrase is dropped only when, as a whole, it cannot be a
person, never because of the words around it. Names are invented.
"""
import pytest

from pseudonimizzatore_legale.verification import verify


def reported(text: str) -> list[str]:
    return [item.text for item in verify(text).residuals
            if item.source == "verification:name-shape"]


@pytest.mark.parametrize("text", [
    # articles, titles, roles and the words of a heading
    "Il Presidente",
    "Il Segretario",
    "Sezione Terza",
    "Sezioni Riunite",
    "Data Udienza",
    "Consigliere Dott. ",
    "IN NOME DEL POPOLO ITALIANO",
    "CORTE DI GIUSTIZIA TRIBUTARIA DI PRIMO GRADO DI BOLOGNA",
    "SEZIONE GIURISDIZIONALE PER LA REGIONE",
    # a comune, with or without its province
    "Reggio Calabria",
    "Gualdo Tadino",
    "Alessandria AL",
    # a company, which stays by default, with its legal form after it
    "la società Orsetti Valdambra S.a.s. di",
    "contro Ginevra Boldrocchi S.r.l., in persona del",
])
def test_phrases_that_cannot_be_a_person_are_not_reported(text):
    assert reported(text) == []


@pytest.mark.parametrize("text, expected", [
    # a surname that is also a word of the layout: the particle makes it a surname
    ("Il ricorso di Del Giudice", ["Del Giudice"]),
    ("sentito Lo Giudice", ["Lo Giudice"]),
    ("Giudice Primo", ["Giudice Primo"]),
    ("Gentile Marta", ["Gentile Marta"]),
    # an article before a surname
    ("Il Malaspina insiste", ["Il Malaspina"]),
    # a comune that opens with a first name may be a person
    ("la sig.ra Alice Castello", ["Alice Castello"]),
    # a name next to a role or a heading is still a name
    ("Il Presidente Verdi firma", ["Il Presidente Verdi"]),
    ("Mario Verdi Presidente", ["Mario Verdi Presidente"]),
    ("Sezione Terza Luigi Verdi", ["Sezione Terza Luigi Verdi"]),
    # no legal form: nothing says it is a company
    ("la Nautica Brancaleone", ["Nautica Brancaleone"]),
])
def test_names_and_possible_names_are_still_reported(text, expected):
    assert reported(text) == expected


def test_a_two_part_tag_is_not_read_as_a_name():
    assert reported("Ecco La Numero_carta_1.") == []


def titled(text: str, protected=()) -> list[str]:
    return [item.text for item in verify(text, protected_spans=protected).residuals
            if item.source == "verification:title-name"]


@pytest.mark.parametrize("text, expected", [
    # a surname the replacing patterns refuse (a common word) or never read
    ("l'avv. Casa si dichiarava difensore", ["Casa"]),
    ("la sig.ra Esposito ha percepito", ["Esposito"]),
    ("il geometra Brambillasca firma", ["Brambillasca"]),
    ("il notaio Strano ha rogato", ["Strano"]),
    # the doctor is a person, whoever else carries the title
    ("il consulente dott. Verdi firma", ["Verdi"]),
    ("la prof.ssa Bianchi insegna", ["Bianchi"]),
    # a first name alone is a name too
    ("l'avv. Sergio e l'avv. Piero", ["Sergio", "Piero"]),
])
def test_a_word_after_a_title_is_reported(text, expected):
    assert titled(text) == expected


@pytest.mark.parametrize("text", [
    # a judicial role before the title, after the name, or alone on the line above or below
    "il Presidente dott. Verdi firma",
    "Giudice dr.ssa Bianchi",
    "dott. Verdi   Presidente",
    "dr. Verdi, Giudice",
    "Il Presidente\ndott. Verdi\nsegue",
    "dott.ssa Bianchi\nIl Giudice\nsegue",
    # an adjective of a role, a tag, our own initials
    "l'Avvocato Generale ha concluso",
    "il perito Unico",
    "il notaio Nominativo_1 ha rogato",
    "il dott. M.R. ha firmato",
])
def test_a_word_after_a_title_is_left_when_it_cannot_be_a_person_or_is_a_judge(text):
    assert titled(text) == []


def test_a_surname_of_a_kept_judge_is_left_after_the_titles_judges_carry():
    text = "Il Collegio: Anita Verdi. Come ha scritto il dott. Verdi nella sentenza"
    start = text.index("Anita")
    judge = [(start, start + len("Anita Verdi"))]
    assert titled(text, judge) == []
    # …but not after a trade, and not when nobody was kept
    assert titled(text.replace("dott.", "geom."), judge) == ["Verdi"]
    assert titled(text) == ["Verdi"]


def test_a_name_already_reported_as_a_name_keeps_that_report():
    assert reported("la sig.ra Alice Castello") == ["Alice Castello"]
    assert titled("la sig.ra Alice Castello") == []
