"""The fixture builder's gold decisions for judicial shapes (evaluation/build_corpus).

The builder writes the gold of every rebuilt fixture, so a shape it misreads becomes a
gold error: in 2026-09 it had put bench members in must_remove in 17 committed golds.
Each case feeds `deidentify` a snippet and checks where the gold puts the name that
follows a marker the builder leaves alone (a role word or a title).

The names are plain invented ones, not the namebank's: the builder's replacement picker
skips surnames already in the text, so namebank input makes two judges share one
identity. Cases marked `gap` are known failures, strict xfails as in
test_decision_shapes.py.
"""
import sys
from pathlib import Path

import pytest
import regex as re

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evaluation" / "build_corpus"))
from deidentify import deidentify  # noqa: E402

NAME = r"[\p{Lu}][\p{L}'’]+(?:[^\S\n][\p{Lu}][\p{L}'’]+)+"


def gold_for_name_after(marker, snippet):
    """'keep', 'remove' or 'unannotated': the builder's gold for the name after `marker`."""
    text, must_remove, must_keep = deidentify(snippet)
    found = re.search(rf"{re.escape(marker)}[^\S\n]*({NAME})", text)
    assert found, f"no name after {marker!r} in {text!r}"
    name = found.group(1)
    return "keep" if name in must_keep else "remove" if name in must_remove else "unannotated"


def gap(reason):
    return pytest.mark.xfail(strict=True, reason=reason)


CASES = [
    pytest.param(
        "relatore",
        "Uditi, all'udienza pubblica del 12 luglio 2018, il consigliere\nrelatore "
        "Liana Tacchi e l'avv. Carla Fenzi in rappresentanza.",
        "keep", id="corte_conti/21-lowercase-consigliere-relatore"),
    pytest.param(
        "il cons.",
        "Relatore nell'udienza pubblica del giorno 03/07/2008 il cons. Liana Tacchi "
        "e uditi per le parti i difensori;",
        "keep", id="tar/21-il-cons"),
    pytest.param(
        "dott.ssa",
        "IL GIUDICE DELLE PENSIONI\nPrimo referendario dott.ssa Liana Tacchi\n"
        "ha pronunciato la seguente\nSENTENZA",
        "keep", id="corte_conti/14-primo-referendario"),
    pytest.param(
        "Relatore:",
        "Presidente: Ottavio Brambati\nRelatore: Liana Tacchi\nSENTENZA\nsul ricorso "
        "proposto da Remo Fabbrini, difeso dall'avv. Carla Fenzi;\nUdito nella camera di "
        "consiglio il dott. Liana Tacchi e uditi i difensori.",
        "keep", id="consiglio_stato-judge-later-titled-dott"),
    pytest.param(
        "Referendario (relatore)\ndott.",
        "composta dai magistrati:\ndott. Ottavio Brambati\n\nPresidente\n"
        "dott. Nives Cattarin\n\n\n\nConsigliere\ndott. Ada Scotti\n\n\n\nConsigliere\n"
        "dott. Ugo Paterno\n\n\nReferendario (relatore)\ndott. Liana Tacchi\n\n\n\n"
        "Referendario\n\nnella adunanza pubblica del 13 ottobre 2010",
        "keep", id="corte_conti/15-bench-listed-after-dott"),
    pytest.param(
        "2) Dott.ssa",
        "composta dai seguenti Magistrati: 1) Dott. Ottavio Brambati -Presidente "
        "2) Dott.ssa Liana Tacchi -Consigliere rel.\nrappresentati e difesi dall'avv. "
        "Carla Fenzi, domiciliati in Bari (c/o avv. Liana Tacchi)",
        "remove", id="merito_civile/01_2023-judge-also-domiciliary-counsel"),
    pytest.param(
        "2) Dott.",
        "composta dai seguenti Magistrati: 1) Dott. Ottavio Brambati -Presidente "
        "2) Dott. Liana Tacchi -Consigliere\nAPPELLANTE CONTRO\nRemo Fabbrini, "
        "Liana Tacchi, Ada Scotti, ciascuno in qualità di coerede, rappresentati e difesi "
        "dall'avv. Carla Fenzi",
        "remove", id="merito_civile/01_2023-judge-also-in-party-list"),
    pytest.param(
        "Consigliere\nDott.",
        "composta da: Dott. Ottavio Brambati      Presidente relatrice Dott.  "
        "Nives Cattarin      Consigliere\nDott. Liana Tacchi      Consigliere ha "
        "pronunciato la seguente\nSENTENZA",
        "keep",
        marks=gap("a run of spaces lets the name swallow the role after it, so no judge "
                  "cue is seen, and the name is half replaced and left unannotated"),
        id="merito_civile/03_2020-role-after-tabular-gap"),
]


@pytest.mark.parametrize("marker, snippet, expected", CASES)
def test_gold_decision(marker, snippet, expected):
    assert gold_for_name_after(marker, snippet) == expected


@gap("a capitalised role run in a bench ('Primo Referendario') is read as a judge's "
     "name and rewritten; corte_conti/15 shows 'Trevisanato (relatore)'")
def test_role_words_are_not_rewritten_as_names():
    text, _, _ = deidentify("composta dai magistrati:\ndott. Ottavio Brambati\n\nPresidente\n"
                            "dott. Nives Cattarin\n\n\nPrimo Referendario\n\n"
                            "nella adunanza pubblica")
    assert "Primo Referendario" in text
