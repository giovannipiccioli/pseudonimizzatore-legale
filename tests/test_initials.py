"""Initials ("A.G.") written where a name belongs, and the sigle that look just like them.

Some sources shorten every private name to its initials. `Config(initials=True)` replaces
them where a cue says a person stands there; `initials="all"` replaces any that nothing
excludes, for a source known to be written that way. Sigle (P.Q.M., D.P.R., S.U.) and
references (art. 2697 C.C., D.L. n. 78) must come out untouched under both readings: a
sigla turned into a party deletes real text, which is why the `keep` half is the one that
matters.

Every text is invented, in the shape of the decisions it stands for: Cassazione civile and
penale as the ilforo archive prints them, Corte costituzionale ordinanze, tax judgments
full of sigle. The measurements behind the thresholds were taken on private archives and
are not reproducible from here; these tests are what keeps the behaviour in place.

Cases marked `gap` are known failures, strict xfails as in test_decision_shapes.py: the run
fails the day one starts passing, and the marker should then come off.
"""
import dataclasses
import json
import time

import pytest

from pseudonimizzatore_legale import Config, TextAnchor, analyze, anonymize, anonymize_batch, render
from pseudonimizzatore_legale import seeds

PRUDENT = Config(initials=True, roles=True)
EVERYWHERE = Config(initials="all", roles=True)


def gap(reason):
    return pytest.mark.xfail(strict=True, reason=reason)


def out(text, config=PRUDENT):
    return anonymize(text, config)[0]


# ── who is a person: the prudent reading ────────────────────────────────────

#: (text, initials that must disappear, text that must stay)
PERSONS = [
    pytest.param("Il ricorso proposto da A.G. è fondato.", ["A.G."], ["è fondato"],
                 id="proposto-da"),
    pytest.param("ricorso proposto da A.G., S.I. e L.S. avverso la sentenza",
                 ["A.G.", "S.I.", "L.S."], ["avverso la sentenza"], id="proposto-da-list"),
    pytest.param("Il ricorso di A.G. è inammissibile.", ["A.G."], ["è inammissibile"],
                 id="ricorso-di"),
    pytest.param("giudizio promosso da M.R. nel 1998", ["M.R."], ["nel 1998"], id="promosso-da"),
    pytest.param("Il ricorrente B.L. deduce due motivi.", ["B.L."], ["deduce due motivi"],
                 id="ricorrente"),
    pytest.param("la controricorrente T.N. resiste", ["T.N."], ["resiste"], id="controricorrente"),
    pytest.param("gli appellanti T.L. e A.P. impugnano la sentenza", ["T.L.", "A.P."],
                 ["impugnano la sentenza"], id="appellanti"),
    pytest.param("ricorso contro la sentenza, nei confronti di S.T., che resiste",
                 ["S.T."], ["che resiste"], id="nei-confronti-di"),
    pytest.param("nei confronti di S.T., L.S. e R.A., con ricorso notificato",
                 ["S.T.", "L.S.", "R.A."], ["con ricorso notificato"], id="nei-confronti-list"),
    pytest.param("ricorrenti\nnei confronti\nS.T.\nintimato", ["S.T."], ["intimato"],
                 id="nei-confronti-heading"),
    pytest.param("difeso dall'avv. B.N., con studio in Roma", ["B.N."], ["con studio in Roma"],
                 id="avv"),
    pytest.param("gli avvocati M.F. ed E.G. hanno depositato", ["M.F.", "E.G."],
                 ["hanno depositato"], id="avvocati-list"),
    pytest.param("Il sig. M.O. ha depositato memoria.", ["M.O."], ["ha depositato memoria"],
                 id="sig"),
    pytest.param("la dott.ssa V.P. ha riferito", ["V.P."], ["ha riferito"], id="dottssa"),
    pytest.param("gli eredi di C.S. e V.R. hanno resistito", ["C.S.", "V.R."],
                 ["hanno resistito"], id="eredi-di"),
    pytest.param("il curatore T.F. ha depositato", ["T.F."], ["ha depositato"], id="curatore"),
    pytest.param("la ditta individuale di R.V., con sede", ["R.V."], ["con sede"],
                 id="ditta-individuale"),
    pytest.param("L'imputato C.L. ricorre per cassazione.", ["C.L."], ["ricorre per cassazione"],
                 id="imputato"),
    pytest.param("la persona offesa A.P. ha riferito", ["A.P."], ["ha riferito"],
                 id="persona-offesa"),
    pytest.param("la parte civile N.F. chiede la condanna", ["N.F."], ["chiede la condanna"],
                 id="parte-civile"),
    pytest.param("il teste T.R. ha confermato", ["T.R."], ["ha confermato"], id="teste"),
    pytest.param("M.R., nato a Torino il 12 marzo 1970, ricorre.", ["M.R."], ["ricorre"],
                 id="biographic-nato"),
    pytest.param("T.S., residente in Roma, deduce", ["T.S."], ["deduce"], id="biographic-residente"),
    pytest.param("D.F.C., domiciliato in Napoli, deduce", ["D.F.C."], ["deduce"],
                 id="three-letters"),
    pytest.param("nei confronti di A. G. e S. T., resistenti", ["A. G.", "S. T."],
                 ["resistenti"], id="spaced"),
    pytest.param("ricorso proposto da À.B. avverso", ["À.B."], ["avverso"], id="accented"),
    pytest.param("proposto da A.G.; A.G. insiste e nulla è dovuto ad A.G.",
                 ["A.G."], ["insiste", "nulla è dovuto"], id="same-letters-recur"),
]


@pytest.mark.parametrize("text, removed, kept", PERSONS)
def test_prudent_reading_takes_cued_initials(text, removed, kept):
    result = out(text)
    for value in removed:
        assert value not in result, f"{value!r} survived in {result!r}"
    for value in kept:
        assert value in result, f"{value!r} was damaged in {result!r}"
    assert out(text, EVERYWHERE) == result, "the everywhere reading must agree on a cued text"


#: Initials with nothing around them that says a person: only the everywhere reading takes them.
UNCUED = [
    pytest.param("Il Tribunale dichiarava D.C. colpevole del reato.", ["D.C."], id="dichiarava"),
    pytest.param("Svolgimento del processo A.G. propose opposizione.", ["A.G."], id="heading"),
    pytest.param("1. B.S. ricorre per mezzo del difensore.", ["B.S."], id="numbered-item"),
    pytest.param("tra G.M. e P.L. fu stipulato il contratto", ["G.M.", "P.L."], id="between"),
    pytest.param("la condotta di D.M.G. fu accertata", ["D.M.G."], id="three-letters"),
    pytest.param("nei fatti intervenne <R. U.>, odierno ricorrente", ["R. U."], id="angle-brackets"),
    pytest.param("un coimputato (G.G.) che collaborava", ["G.G."], id="parentheses"),
    pytest.param("le dichiarazioni dei testi B.V. e M.A. sono concordi", ["B.V.", "M.A."],
                 id="witnesses-without-the-cue-word"),
]


@pytest.mark.parametrize("text, removed", UNCUED)
def test_everywhere_reading_takes_what_no_cue_announces(text, removed):
    assert out(text) == text, "the prudent reading must leave initials nobody announced"
    result = out(text, EVERYWHERE)
    for value in removed:
        assert value not in result, f"{value!r} survived in {result!r}"


# ── sigle and references stay, under both readings ──────────────────────────

#: Texts with nothing to replace. Each line stands for a false positive found on real text.
UNTOUCHED = [
    pytest.param("P.Q.M. La Corte rigetta il ricorso e condanna la ricorrente alle spese.",
                 id="pqm"),
    pytest.param("Il P.M. ha concluso per l'inammissibilità; il P.G. presso la Corte ha chiesto "
                 "il rigetto.", id="pm-pg"),
    pytest.param("ai sensi del D.P.R. 633/72, art. 54, e del D.L. n. 78/2010", id="dpr-dl"),
    pytest.param("Cass., S.U., n. 186 del 1987; Cass. sez. U, 5 novembre 2001, n. 1368",
                 id="cassazione-su"),
    pytest.param("T.A.R. Lazio; A.T.P.; la C.T.U. nominata; la C.T.P. di parte", id="tar-ctu"),
    pytest.param("art. 2697 C.C. e art. 112 C.P.C.; art. 360 C.P.C. e 574 C.P.P.", id="codici"),
    pytest.param("Alfa S.p.A., Beta S.r.l., Gamma S.a.s. e Delta S.n.c.", id="companies"),
    pytest.param("il versamento dell'I.V.A., dell'I.R.A.P. e dell'I.R.P.E.F. all'I.N.P.S.",
                 id="tax-and-agencies"),
    pytest.param("Il G.I.P. ha disposto; il G.U.P. del Tribunale ha rinviato; il G.O.T. no.",
                 id="penal-bodies"),
    pytest.param("R.G. 1054/2016 e N.R.G. 2345/2018", id="ruoli"),
    pytest.param("il Presidente dott. N.A. Vecchio e il relatore A.B. hanno deciso", id="bench"),
    pytest.param("Presidente: R.M.\nRelatore: A.B.\nCancelliere: T.S.", id="header-fields"),
    pytest.param("il consigliere avv. N.A. riferì", id="consigliere-avv"),
    pytest.param("la R.B. s.p.a. ha proposto ricorso", id="company-initials"),
    pytest.param("l'appello della G.M.G. Motors s.r.l. è fondato", id="company-name"),
    pytest.param("assegnato al Cons. est. G.M. Nonno e al dott. Verdi", id="name-follows"),
    pytest.param("residente in via G.B. Martini 3, Torino", id="street-name"),
    pytest.param("ex art. 59 D.L. 5 maggio 1999, n. 1 e D.L.\n30 settembre 2003, n. 269.",
                 id="number-on-the-next-line"),
    pytest.param("il D.M. Giustizia n. 37/2018 e il D.L. Sviluppo 12 del 2020", id="decree-named"),
    pytest.param("(C.F.: n.d.) e la C.F. del contribuente", id="codice-fiscale-label"),
    pytest.param("rappresentata da (C.F. L e P.I. 12345678901)", id="reduced-codice-fiscale"),
    pytest.param("la società I.A.c.p. e la R.E.S.A.I.S. di Roma, l'E.N.E.L. e l'A.N.A.S.",
                 id="longer-than-three-letters"),
    pytest.param("in a.g., d.lgs. 74/2000, c.p.c. e p.m. minuscoli", id="lower-case"),
    pytest.param("il verbale AG e SI non sono iniziali", id="no-dots"),
    pytest.param("IL DISPOSITIVO È QUESTO. NESSUNA INIZIALE QUI.", id="shouting"),
    pytest.param("la sentenza della Corte E.D.U. e l'art. 6 della Convenzione E.D.U.; la stima "
                 "dell'U.T.E., la decisione della C.T.C. e il P.V.C. notificato",
                 id="ilforo-cassazione-sigle"),
    pytest.param("approvato il P.I.P. con le N.T.A. del piano", id="planning-sigle"),
]


@pytest.mark.parametrize("text", UNTOUCHED)
def test_sigle_and_references_are_left_alone(text):
    assert out(text) == text
    assert out(text, EVERYWHERE) == text


#: What the everywhere reading cannot know: an unlisted sigla or an organisation it has
#: never seen looks like three letters of a person.
EVERYWHERE_GAPS = [
    pytest.param("indetta dalla O.U.A. per il 10 maggio", id="unlisted-sigla"),
    pytest.param("il piano della R.T.P. e della U.A.P. di Parigi", id="unlisted-organisations"),
    pytest.param("approvato il piano con il D.D.G. regionale", id="planning-decree"),
]


@pytest.mark.parametrize("text", EVERYWHERE_GAPS)
@gap("the everywhere reading takes an unlisted three-letter sigla for a person")
def test_everywhere_reading_leaves_unlisted_sigle(text):
    assert out(text, EVERYWHERE) == text


def test_the_prudent_reading_takes_an_unlisted_sigla_behind_a_cue_and_only_there():
    assert out("ricorso proposto da O.U.A. avverso la sentenza") == \
        "ricorso proposto da Ricorrente_1 avverso la sentenza"
    text = "il parere reso nell'interesse della O.U.A. non muta"
    assert out(text) == text


# ── known gaps ──────────────────────────────────────────────────────────────

@gap("initials followed by a surname in clear are one name, and the surname is not read")
def test_initials_with_a_surname():
    assert "D'Ascoli" not in out("rappresentato e difeso dall'avv. E.M. D'Ascoli")


@gap("a surname followed by an initial is not read as a name")
def test_surname_then_initial():
    assert "Bianchi G." not in out("Il ricorrente Bianchi G. ha depositato memoria.")


@gap("a person whose initials are those of a listed sigla stays in clear")
def test_person_with_the_initials_of_a_sigla():
    assert "D.M." not in out("Propone ricorso per cassazione il sig. D.M. a mezzo di tre motivi.")


@gap("initials of four letters are left to the sigle")
def test_four_letter_initials():
    assert "L.B.E.F." not in out("Il fondo di proprietà di L.B.E.F. fu ceduto.", EVERYWHERE)


@gap("the judicial detector cannot infer a judge from initials alone")
def test_judge_initials_follow_keep_roles():
    result = out("Presidente: R.M.\nRelatore: A.B.\nproposto da C.S.",
                 Config(initials=True, keep_roles=()))
    assert "R.M." not in result


# ── tags and roles ──────────────────────────────────────────────────────────

def test_roles_follow_the_anchor():
    result = out("ricorso proposto da A.G. nei confronti di S.T., difeso dall'avv. B.N.; "
                 "il sig. M.O. e l'imputato C.L. non si sono costituiti")
    assert result == ("ricorso proposto da Ricorrente_1 nei confronti di Resistente_1, difeso "
                      "dall'avv. Difensore_1; il sig. Nominativo_1 e l'imputato Nominativo_2 "
                      "non si sono costituiti")


def test_two_anchors_at_the_same_place_give_the_role_of_the_earlier_one():
    # S.T. is behind "contro" and in front of "domiciliata": counterparty wins over biographic
    result = out("proposto da:\nA.G., elettivamente domiciliato in Roma;\n- ricorrente -\n"
                 "contro\nS.T., domiciliata in Roma, difesa dall'avvocato L.S.;\n")
    assert result == ("proposto da:\nRicorrente_1, elettivamente domiciliato in Roma;\n"
                      "- ricorrente -\ncontro\nResistente_1, domiciliata in Roma, difesa "
                      "dall'avvocato Difensore_1;\n")


def test_without_roles_everyone_is_nominativo():
    result = out("ricorso proposto da A.G. nei confronti di S.T., difeso dall'avv. B.N.",
                 Config(initials=True))
    assert result == "ricorso proposto da Nominativo_1 nei confronti di Nominativo_2, " \
                     "difeso dall'avv. Nominativo_3."


def test_the_same_initials_get_one_tag_however_they_are_spaced():
    result = out("proposto da A.G. e nei confronti di S.T., poi A. G. insiste e A.G. replica")
    assert result.count("Ricorrente_1") == 3 and "A." not in result


def test_the_first_anchor_gives_the_role_when_a_person_is_named_twice():
    result = out("i ricorrenti A.G. e S.T.; nei confronti di A.G. si procede")
    assert result.count("Ricorrente_1") == 2 and "Resistente" not in result


def test_tags_are_numbered_in_document_order_with_names_and_initials_together():
    result = out("Il sig. Mario Rossi ricorre contro Lucia Verdi; ricorso proposto da A.G. nei "
                 "confronti di S.T., che resiste.", Config(initials=True))
    assert result == ("Il sig. Nominativo_1 ricorre contro Nominativo_2; ricorso proposto da "
                      "Nominativo_3 nei confronti di Nominativo_4, che resiste.")


def test_a_tag_is_never_a_candidate_again():
    once = out("proposto da A.G. nei confronti di S.T.", EVERYWHERE)
    assert out(once, EVERYWHERE) == once


# ── what the option leaves alone ────────────────────────────────────────────

def test_off_by_default():
    text = "ricorso proposto da A.G. nei confronti di S.T., difeso dall'avv. B.N."
    assert Config().initials is False
    assert anonymize(text)[0] == text
    assert anonymize(text, initials=False)[0] == text


def test_off_matches_the_library_before_the_option_on_text_without_initials():
    text = "Il sig. Mario Rossi, nato a Torino, C.F. RSSMRA80A01H501U, ricorre contro l'INPS."
    assert anonymize(text, initials=True)[0] == anonymize(text)[0]
    assert anonymize(text, initials="all")[0] == anonymize(text)[0]


def test_option_values_are_validated():
    for value in (False, True, "all"):
        assert Config(initials=value).initials == value
    for value in ("sometimes", 1, None, "ALL"):
        with pytest.raises(ValueError):
            Config(initials=value)


def test_config_can_be_replaced_per_source():
    base = Config(roles=True, initials=True)
    assert dataclasses.replace(base, initials="all").initials == "all"
    assert base.initials is True


def test_judges_stay_in_clear_and_parties_go():
    text = ("Presidente: Mario Verdi\nRelatore: Lucia Neri\n"
            "ricorso proposto da A.G. nei confronti di S.T.")
    result = out(text, Config(initials=True, roles=True, keep_roles=("giudice",)))
    assert "Mario Verdi" in result and "Lucia Neri" in result
    assert "A.G." not in result and "S.T." not in result


def test_case_numbers_stay():
    text = "R.G. n. 1054/2016, proposto da A.G.; n. 25696/2018 R.G."
    result = out(text)
    assert "1054/2016" in result and "25696/2018" in result and "A.G." not in result


def test_structured_identifiers_are_still_replaced_next_to_initials():
    result = out("M.R., C.F. RSSMRA80A01H501U, nato a Torino, scrive a m.r@studio.it")
    assert "RSSMRA80A01H501U" not in result and "m.r@studio.it" not in result
    assert "M.R." not in result and "C.F." in result


def test_a_company_named_by_initials_stays_whole():
    text = "ricorso proposto da A.G. e dalla R.B. s.p.a."
    result = out(text)
    assert "R.B. s.p.a." in result and "A.G." not in result


def test_names_and_initials_of_the_same_document_are_all_replaced():
    result = out("Il ricorso proposto da A.G. nei confronti di S.T. è fondato. Mario Rossi e "
                 "Lucia Verdi, nati a Roma, resistono.")
    for value in ("A.G.", "S.T.", "Mario Rossi", "Lucia Verdi"):
        assert value not in result


# ── text hygiene ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("proposto da A.G. Il ricorso è fondato.", "proposto da Ricorrente_1. Il ricorso è fondato."),
    ("nei confronti di A.G.\nIl ricorso è fondato.", "nei confronti di Resistente_1.\nIl ricorso è fondato."),
    ("nei confronti di A.G.", "nei confronti di Resistente_1."),
    ("proposto da A.G., S.T.; e (A.G.)", "proposto da Ricorrente_1, Ricorrente_2; e (Ricorrente_1)"),
    ("proposto da A.G. e dal sig. S.T. ricorrente", "proposto da Ricorrente_1 e dal sig. Nominativo_1 ricorrente"),
    ("«proposto da A.G.»", "«proposto da Ricorrente_1»"),
], ids=["sentence-end", "line-end", "text-end", "punctuation", "inline", "quotes"])
def test_punctuation_and_spacing_around_the_tag(text, expected):
    assert out(text) == expected


def test_nothing_else_changes():
    text = "Il ricorso proposto da A.G. richiama l'art. 2697 C.C. e il D.P.R. 633/72."
    result = out(text)
    assert result.replace("Ricorrente_1", "A.G.") == text


# ── the API around it ───────────────────────────────────────────────────────

def test_decisions_report_the_detector_and_the_reason():
    analysis = analyze("ricorso proposto da A.G. nei confronti di S.T.; più oltre A.G. insiste",
                       PRUDENT)
    initials = [d for d in analysis.decisions if d.source == "regex:initials"]
    assert [d.text for d in initials] == ["A.G.", "S.T.", "A.G."]
    assert {d.kind for d in initials} == {"PERSON"}
    assert [d.role for d in initials] == ["ricorrente", "resistente", "ricorrente"]
    assert all(d.action == "redact" and d.replacement for d in initials)
    assert initials[0].replacement == initials[2].replacement
    assert "initials" in initials[0].reason


def test_the_everywhere_reading_says_so():
    analysis = analyze("Il Tribunale dichiarava D.C. colpevole.", EVERYWHERE)
    (decision,) = [d for d in analysis.decisions if d.kind == "PERSON"]
    assert decision.source == "regex:initials_everywhere"
    assert "source that writes its parties as initials" in decision.reason


def test_entity_records_group_the_spellings_of_one_person():
    analysis = analyze("proposto da A.G. e da A. G., poi A.G. insiste", PRUDENT)
    (record,) = [r for r in analysis.entities if r.role == "ricorrente"]
    assert set(record.aliases) == {"A.G.", "A. G."}
    assert len(record.spans) == 3 and record.action == "redact"


def test_mapping_and_report_count_the_initials():
    text = "proposto da A.G. nei confronti di S.T.; A.G. insiste"
    result, report = anonymize(text, PRUDENT)
    assert report.mapping == {"A.G.": "Ricorrente_1", "S.T.": "Resistente_1"}
    assert report.replacements == 3 and report.entities == 2
    assert [text[a:b] for a, b in report.replacement_spans] == ["A.G.", "S.T.", "A.G."]


def test_analyze_then_render_is_anonymize():
    text = "ricorso proposto da A.G. nei confronti di S.T., difeso dall'avv. B.N."
    assert render(analyze(text, PRUDENT))[0] == anonymize(text, PRUDENT)[0]


def test_replaying_state_keeps_the_numbers_when_the_text_changes():
    first = analyze("ricorso proposto da A.G. e S.T.", Config(initials=True))
    edited = analyze("proposto da C.D.F., A.G. e S.T.", Config(initials=True),
                     state=first.state)
    assert edited.mapping["A.G."] == first.mapping["A.G."]
    assert edited.mapping["S.T."] == first.mapping["S.T."]
    assert edited.mapping["C.D.F."] not in first.mapping.values()


def test_a_reviewer_can_keep_one_occurrence():
    text = "ricorso proposto da A.G. e da S.T."
    analysis = analyze(text, PRUDENT)
    start = analysis.text.index("S.T.")
    anchor = TextAnchor.capture(analysis.text, start, start + 4)
    edited = analyze(text, PRUDENT, state={"occurrences": [
        {"action": "keep", "anchor": {"quote": anchor.quote, "prefix": anchor.prefix,
                                      "suffix": anchor.suffix}}]})
    assert "S.T." in render(edited)[0] and "A.G." not in render(edited)[0]


def test_batch_resume_redoes_a_file_when_the_option_changes(tmp_path):
    source, destination = tmp_path / "input", tmp_path / "output"
    source.mkdir()
    (source / "case.txt").write_text("ricorso proposto da A.G. nei confronti di S.T.", encoding="utf-8")
    anonymize_batch(source, destination, workers=1, sidecar=True)
    assert "A.G." in (destination / "case.txt").read_text("utf-8")
    anonymize_batch(source, destination, config=Config(initials=True), workers=1, sidecar=True,
                    resume=True)
    assert "A.G." not in (destination / "case.txt").read_text("utf-8")
    data = json.loads((destination / "case.txt.map.json").read_text("utf-8"))
    assert data["config"]["initials"] is True


# ── input the option must survive ───────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "", " ", "\n\n", ".", "A.", "A.G", "A.G.", "..", "A..G..", ". . .", "A. B. C. D. E.",
    "A.B.C.D.E.F.", "proposto da ", "proposto da A.", "nei confronti di A.G.G.G.G.",
], ids=repr)
def test_degenerate_text_does_not_break(text):
    for config in (PRUDENT, EVERYWHERE):
        result, report = anonymize(text, config)
        assert isinstance(result, str) and report.status in ("passed_checks", "needs_review")


def test_a_long_run_of_initials_is_not_slow():
    started = time.perf_counter()
    text = "nei confronti di " + ", ".join("A.G." for _ in range(8000)) + " e altri. " * 100
    out(text, EVERYWHERE)
    out("A. " * 20000 + "B.C. " * 5000 + "x" * 100000, EVERYWHERE)
    assert time.perf_counter() - started < 30


def test_the_sigle_resource_is_loaded_once():
    assert seeds.sigle() is seeds.sigle()
