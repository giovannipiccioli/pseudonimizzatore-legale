"""Fixes that no other test pinned down.

A mutation audit (November 2026) undid each hunk of the past fixes in turn and ran the
suite: the hunks below left every test green, so a later edit could have dropped them
unnoticed. Each case is the smallest text where the fix, and nothing else, makes the
difference.

Cases marked `gap` are known failures, strict xfails as in test_recall_shapes.py: the run
fails the day one starts passing, and the marker should then come off.
"""
import pytest
import regex as re

from pseudonimizzatore_legale import Config, anonymize
from pseudonimizzatore_legale import patterns as P

CORPUS = Config(companies="person_named", roles=True, keep_roles=("giudice",))


def present(value, text):
    return bool(re.search(rf"(?<![\p{{L}}\p{{N}}]){re.escape(value)}(?![\p{{L}}\p{{N}}])", text))


def gap(reason):
    return pytest.mark.xfail(strict=True, reason=reason)


CASES = [
    # ORG_HEAD: an office or a firm is not a person, whatever its name looks like
    pytest.param(
        "Il ricorso è proposto da Studio Rinaldi Commercialisti, con sede in Roma, in persona "
        "del legale rappresentante.",
        ["Studio Rinaldi Commercialisti"], [], id="studio-is-not-a-person"),
    pytest.param(
        "proposto da Segreteria Generale Bellandi Chiara, con sede in Roma.",
        ["Segreteria Generale Bellandi Chiara"], [], id="segreteria-is-not-a-person"),
    pytest.param(
        "nei confronti di Azienda Unità Sanitaria Locale Caserta, in persona del legale "
        "rappresentante",
        ["Azienda Unità Sanitaria Locale Caserta"], [], id="azienda-unita-sanitaria"),
    # a name read across a line break does not swallow the role word that follows it
    pytest.param(
        "proposto da Mario Rossi Segretario comunale, residente in Roma.",
        ["Segretario comunale"], ["Mario Rossi"], id="segretario-ends-a-name"),
    # a list of parties ends at a blank line: the salutation below it is not another party
    pytest.param("proposto da Giulia Balestri,\n\nCaro Paolo, ti scrivo.", ["Caro"],
                 ["Giulia Balestri", "Paolo"], id="party-list-ends-at-a-blank-line"),
    # a first name alone, once a salutation or a kinship cue has said it is a person
    pytest.param("Caro Paolo,\n\nti scrivo in merito alla pratica.", [], ["Paolo"],
                 id="salutation-paolo"),
    pytest.param("Un caro saluto,\nLuca", [], ["Luca"], id="closing-luca"),
    pytest.param("Cari saluti,\nMarcello", [], ["Marcello"], id="closing-marcello"),
    # an e-mail's display name is a person even when every word of it is a common one
    pytest.param("Mittente: Giovanni Esposito <giovanni.esposito@gmail.com>\n\nIn allegato la "
                 "pratica.", [], ["Giovanni Esposito", "giovanni.esposito@gmail.com"],
                 id="email-display-name"),
    pytest.param("From: Antonio De Luca <a.deluca@libero.it>\nSubject: avviso", [],
                 ["Antonio De Luca"], id="email-display-name-particle"),
    # a name that is both on the bench and a party's: the party wins, the other judge stays
    pytest.param(
        "Relatore: Rossi Mario\nPresidente: Verdi Luigi\nnei confronti di Rossi Mario, "
        "ricorrente.",
        ["Verdi Luigi"], ["Rossi Mario"], id="homonym-of-a-party-is-not-a-judge"),
    # the surname alone, after an article, when the surname is also a dictionary word
    pytest.param(
        "Salvatore Fiore ha proposto ricorso. Il Fiore lamenta che la sentenza del Fiore "
        "sia errata.",
        [], ["Fiore"],
        id="common-word-surname-after-article",
        marks=gap("a seeded person's surname is not propagated when it is a common word")),
    # a surname with a particle whose last word is a common one
    pytest.param(
        "Ottavio De Rosa ha proposto ricorso. Il danno al rapporto di lavoro del De Rosa con la "
        "società è provato.",
        [], ["De Rosa"],
        id="particle-surname-with-common-last-word",
        marks=gap("'Rosa' is a common word, so 'De Rosa' alone is never hunted")),
]


@pytest.mark.parametrize("text, keep, remove", CASES)
def test_probe(text, keep, remove):
    assert all(present(v, text) for v in keep + remove)
    out, _ = anonymize(text, CORPUS)
    assert [v for v in remove if present(v, out)] == [], "left in clear"
    assert [v for v in keep if not present(v, out)] == [], "wrongly removed"


# Every tag the pipeline writes: those of the structured detectors, and the people and places.
EMITTED = [label for label, *_ in P.STRUCTURED] + [
    "Nominativo", "Ricorrente", "Resistente", "Difensore", "Società", "Luogo", "Indirizzo"]
LABELS = [pytest.param(label, marks=gap("the underscore splits it: 'Luigi Data' is read as a name"))
          if label == "Data_nascita" else label for label in EMITTED]


@pytest.mark.parametrize("label", LABELS)
def test_a_second_pass_leaves_every_tag_alone(label):
    # Batches are resumed and re-run after a rule change: a tag must never be read back as
    # part of a person's name ("Albo_1" -> "Nominativo_1_1").
    text = f"Il signor Luigi {label}_1 compare come tag."
    out, _ = anonymize(text, CORPUS)
    assert out == text


def test_a_public_mailbox_left_in_clear_is_not_a_finding():
    # The kept address must not make the verification ask for a review.
    text = "La notifica va fatta alla PEC protocollo@pec.agenziaentrate.it dell'Ufficio."
    out, report = anonymize(text)
    assert "protocollo@pec.agenziaentrate.it" in out
    assert report.status == "passed_checks"
