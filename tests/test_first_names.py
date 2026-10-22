"""The bundled first-name list is a weak seed, never a substitution dictionary."""

import json
from importlib.resources import files

import pytest

from pseudonimizzatore_legale import Config, anonymize
from pseudonimizzatore_legale.seeds import first_names


def test_resource_is_normalized_unique_and_attributed():
    raw = files("pseudonimizzatore_legale").joinpath(
        "resources/first_names.json"
    ).read_text("utf-8")
    data = json.loads(raw)
    names = data["names"]

    assert data["_meta"]["license"] == "CC BY 4.0"
    assert "figshare.3839580" in data["_meta"]["source"]
    assert len(names) > 6_000
    assert names == sorted(set(names))
    assert all(name == name.casefold() and name.isalpha() for name in names)
    assert {"alberto", "anna", "mario"} <= set(names)


@pytest.mark.parametrize(
    "text,name",
    [
        ("Ferruccio Malaspina contestò la decisione.", "Ferruccio Malaspina"),
        ("MALASPINA FERRUCCIO contestò la decisione.", "MALASPINA FERRUCCIO"),
        ("Amedeo Della Rovere presentò ricorso.", "Amedeo Della Rovere"),
        ("DELLA ROVERE AMEDEO presentò ricorso.", "DELLA ROVERE AMEDEO"),
        ("Mario Rossi arrivò in ritardo.", "Mario Rossi"),
        ("Federico Maria Sbaraglia firmò l'atto.", "Federico Maria Sbaraglia"),
        ("SBARAGLIA FEDERICO MARIA firmò l'atto.", "SBARAGLIA FEDERICO MARIA"),
    ],
)
def test_uncued_full_names_are_seeded(text, name):
    output, report = anonymize(text)

    assert name not in output
    assert any("lexicon:first_name" in decision.source for decision in report.decisions)


def test_a_lexical_seed_propagates_a_distinctive_surname():
    text = "Ferruccio Malaspina contestò la decisione. Malaspina insistette."
    output, report = anonymize(text)

    assert "Malaspina" not in output
    assert len(set(report.mapping.values())) == 1


def test_a_first_name_is_never_removed_on_its_own():
    text = "Ferruccio arrivò in ritardo."
    assert anonymize(text)[0] == text


def test_the_detector_can_be_disabled():
    text = "Ferruccio Malaspina contestò la decisione."
    assert anonymize(text, Config(first_names=False))[0] == text


def test_lexicon_only_judge_identity_is_neutral():
    text = (
        "Presidente: MALASPINA FERRUCCIO\n"
        "Ferruccio Malaspina firmò la decisione."
    )
    output, report = anonymize(text)

    assert output == text
    assert "MALASPINA FERRUCCIO" in report.protected


def test_lexicon_only_multi_given_name_judge_is_neutral():
    text = (
        "Presidente: SBARAGLIA FEDERICO MARIA\n"
        "Federico Maria Sbaraglia firmò la decisione."
    )
    output, _ = anonymize(text)

    assert output == text


@pytest.mark.parametrize(
    "text",
    [
        "Ieri Ferruccio Malaspina arrivò in città.",
        "La sede si trova a Reggio Emilia.",
        "Il Catasto Urbano conserva gli atti.",
        "Il Santo Padre ricevette il Consiglio nazionale.",
        "La Rosa dei Venti è un simbolo cartografico.",
        "Marino Blu è il nome commerciale del prodotto.",
    ],
)
def test_ordinary_capitalized_words_around_names_survive(text):
    output, _ = anonymize(text)

    # A real full name inside the sentence may be removed, but the surrounding phrase
    # must not be swallowed into that identity.
    for protected in (
        "Ieri",
        "Reggio Emilia",
        "Catasto Urbano",
        "Santo Padre",
        "Rosa dei Venti",
        "Marino Blu",
    ):
        if protected in text:
            assert protected in output


def test_loaded_resource_is_cached():
    assert first_names() is first_names()


@pytest.mark.parametrize(
    "text",
    [
        "La sede è in Viale Pietro Pietramellara 11.",
        "ROMA, PRESSO VIA CESARE BECCARIA",
        "Ricoverato all'Ospedale di Vittorio Veneto.",
        "La parrocchia di San Giorgio Martire.",
    ],
)
def test_streets_saints_and_towns_are_not_people(text):
    assert seeds_candidates(text) == []
    assert anonymize(text)[0] == text


def test_a_first_name_alone_follows_its_person_or_a_cue():
    text = ("Egr. Avv. Paolo Gennari\n\nCaro Paolo,\nti scrivo. Ferruccio arrivò in "
            "ritardo; il figlio minore Tommaso no.")
    output, report = anonymize(text)

    assert "Paolo" not in output and "Tommaso" not in output
    assert "Ferruccio arrivò" in output
    assert output.count("Nominativo_1") == 2       # "Caro Paolo" is the counsel


def seeds_candidates(text):
    from pseudonimizzatore_legale.seeds import _first_name_candidates
    return _first_name_candidates(text)
