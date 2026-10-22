"""Recall shapes from the October 2026 probes, end to end.

Each probe is a short text in the shape an uploaded act or a decision writes it: a
codice fiscale in a looser form, an address without a CAP, a party known only by
surname, a sole trader, a birthplace, a foreign IBAN. The `keep` values are the
precision half: the nearby text the same rule must leave alone.

Cases marked `gap` are known failures, strict xfails as in test_decision_shapes.py:
the run fails the day one starts passing, and the marker should then come off.
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
    # codice fiscale, identity documents, IBAN
    pytest.param(
        "Il ricorrente, c.f. RSSMRA80A01H50MV, impugna l'avviso.",
        [], ["RSSMRA80A01H50MV"], id="cf-omocodia"),
    pytest.param(
        "Il contribuente (codice fiscale R S S M R A 8 0 A 0 1 H 5 0 1 U) ricorre.",
        [], ["R S S M R A 8 0 A 0 1 H 5 0 1 U"], id="cf-spaced"),
    pytest.param(
        "Inviare a rssmra80a01h501u@pec.it oppure c.f. rssmra80a01h501u.",
        [], ["rssmra80a01h501u"], id="cf-lowercase"),
    pytest.param(
        "Identificato con carta d'identità n. CA12345AB rilasciata dal Comune.",
        ["Comune"], ["CA12345AB"], id="cie"),
    pytest.param(
        "Bonifico su IBAN SM86U0322509800000000270100 e su DE89370400440532013000.",
        [], ["SM86U0322509800000000270100", "DE89370400440532013000"], id="iban-foreign"),
    pytest.param(
        "IBAN DE89 3704 0044 0532 0130 00 BIC COBADEFFXXX",
        ["BIC COBADEFFXXX"], ["DE89 3704 0044 0532 0130 00"], id="iban-foreign-grouped"),
    pytest.param(
        "Impugna l'avviso di accertamento n. TD7030604428 IRAP 2013.",
        ["TD7030604428 IRAP 2013"], [], id="act-number-is-not-an-iban"),
    pytest.param(
        "CIE n. CA 12345 AB", [], ["AB"], id="cie-spaced",
        marks=gap("the CIE is printed unbroken; spaced letters would also take a "
                  "following ALL-CAPS word")),
    pytest.param(
        "IBAN ES91 2100 0418 4502 0005 1332 BANK", ["BANK"], ["1332"],
        id="iban-grouped-before-four-letter-word",
        marks=gap("a last full group of four runs on into a following four-letter "
                  "word, and the check then fails")),

    # addresses without a CAP
    pytest.param(
        "Mario Malaspina, residente in Roma, Via Cola di Rienzo 12, ricorre.",
        [], ["Via Cola di Rienzo 12"], id="address-town-comma-street"),
    pytest.param(
        "Mario Malaspina, residente a Roma in Via Cola di Rienzo n. 12, ricorre.",
        [], ["Via Cola di Rienzo n. 12"], id="address-town-in-street"),
    pytest.param(
        "Mario Malaspina, residente in Pratovecchio (AR), loc. Casalino 4, ricorre.",
        [], ["loc. Casalino 4"], id="address-province-localita"),
    pytest.param(
        "elettivamente domiciliato in Roma, Via Cola di Rienzo 12, presso lo studio "
        "dell'avv. Mario Malaspina.",
        [], ["Via Cola di Rienzo 12", "Mario Malaspina"], id="address-domicile-at-counsel"),
    pytest.param(
        "elettivamente domiciliato presso lo studio dell'avv. Mario Malaspina, Via Po 3.",
        [], ["Via Po 3", "Mario Malaspina"], id="address-after-counsel"),
    pytest.param(
        "La Alfa S.r.l., con sede in Roma, Via Cola di Rienzo 12, ricorre.",
        ["Via Cola di Rienzo 12"], [], id="registered-office-stays"),
    pytest.param(
        "AGENZIA DELLE ENTRATE, elettivamente domiciliata in ROMA VIA DEI PORTOGHESI 12, "
        "presso l'AVVOCATURA GENERALE DELLO STATO, che la rappresenta",
        ["VIA DEI PORTOGHESI 12"], [], id="avvocatura-domicile-stays"),

    # a surname alone after a title or role
    pytest.param(
        "Il sig. Malaspina ha presentato istanza. Il ricorrente Malaspina insiste.",
        [], ["Malaspina"], id="surname-after-title-and-role"),
    pytest.param(
        "Si costituisce il sig. Ferruccio Malaspina. Il sig. Malaspina insiste.",
        [], ["Ferruccio Malaspina", "Malaspina"], id="surname-folds-into-full-name"),
    pytest.param(
        "La contribuente ha delegato il dott. Malaspina, suo consulente.",
        [], ["Malaspina"], id="surname-after-dott",
        marks=gap("dott. is left out of TITOLO_SOLO: judges carry it, and a judge named "
                  "by surname alone has no anchor to protect them")),
    pytest.param(
        "la ricorrente Telecom ha impugnato l'avviso", ["Telecom"], [],
        id="brand-after-party-role",
        marks=gap("a one-word company name after a party role reads as a surname")),

    # sole traders and person-named firms
    pytest.param(
        "La ditta individuale di HU XIAOMING, con il sig. Zhang Weiqiang, ricorre contro "
        "l'Agenzia delle Entrate.",
        ["Agenzia delle Entrate"], ["HU XIAOMING", "Zhang Weiqiang"], id="ditta-individuale"),
    pytest.param(
        "elettivamente domiciliato presso lo studio legale Mirandolina Zangheratti in Ancona.",
        ["Ancona"], ["Mirandolina Zangheratti"], id="studio-legale"),
    pytest.param(
        "contro\nAg. Entrate Direzione Provinciale Roma 1\n"
        "DI BENEDETTO OSVALDO - P.IVA 02956140374\n"
        "Con ricorso la società DI BENEDETTO OSVALDO impugnava il preavviso.",
        ["Ag. Entrate Direzione Provinciale Roma 1"],
        ["DI BENEDETTO OSVALDO", "02956140374"], id="bdgt/23-sole-trader-p-iva"),

    # birthplace and residence towns
    pytest.param(
        "Mario Malaspina, nato a Stia il 03/04/1960 e residente a Pratovecchio, ricorre "
        "davanti alla Corte di giustizia tributaria di Arezzo.",
        ["Corte di giustizia tributaria di Arezzo"], ["Stia", "Pratovecchio"],
        id="birthplace-and-residence"),
    pytest.param(
        "MALASPINA FERRUCCIO nato a FORLI' il 14/04/1971\nIl Tribunale di Forlì ha deciso.",
        ["Tribunale di Forlì"], ["FORLI'"], id="birthplace-all-caps-accent"),
    pytest.param(
        "Serafina Cavalcanti, nata in Romania, residente in Italia.",
        ["Romania", "Italia"], [], id="countries-are-not-comuni"),
]


@pytest.mark.parametrize("text, keep, remove", CASES)
def test_probe(text, keep, remove):
    assert all(present(v, text) for v in keep + remove)
    out, _ = anonymize(text)
    assert [v for v in remove if present(v, out)] == [], "left in clear"
    assert [v for v in keep if not present(v, out)] == [], "wrongly removed"
