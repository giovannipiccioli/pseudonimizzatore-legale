"""Public JSON state, first-pass metadata, and replay after editing the source."""
import json
import re
from dataclasses import asdict
from pathlib import Path

import pytest

from pseudonimizzatore_legale import Config, TextAnchor, analyze, anonymize


def at(action, quote, **context):
    return {"action": action, "anchor": {"quote": quote, **context}}


def test_meeting_note_and_revision_as_published_in_the_spec():
    spec = (Path(__file__).parents[1] / "API_SPEC.md").read_text()
    source, expected = re.findall(r"```text\n(.*?)\n```", spec, re.S)
    state = json.loads(re.search(r"```json\n(.*?)\n```", spec, re.S)[1])
    original = json.dumps(state)
    output, report = anonymize(source, state=state)
    assert output == expected
    assert not report.residuals
    assert report.state == state
    assert json.dumps(state) == original
    assert next(r for r in report.entity_records if r.entity_id == "d3").action == "mixed"
    edited = "Evento pubblico: Aurora.\nM. Zappacosta aggiorna il progetto Aurora."
    output, report = anonymize(edited, state=json.loads(json.dumps(report.state)))
    assert output == "Evento pubblico: Aurora.\nNominativo_1 aggiorna il progetto Progetto_1."
    assert report.state == state


def test_legal_metadata_and_edited_policy():
    state = {"people": [{"name": "Ada Malaspina", "role": "giudice"},
                        {"name": "Marta Zappacosta", "role": "ricorrente", "placeholder": "Parte_7"}]}
    text = "Ada Malaspina ascolta Marta Zappacosta."
    out, first = anonymize(text, Config(keep_roles=["giudice"]), state=state)
    assert out == "Ada Malaspina ascolta Parte_7."
    assert [p["action"] for p in first.state["people"]] == ["keep", "redact"]
    assert anonymize("Marta Zappacosta firma.", state=first.state)[0] == "Parte_7 firma."
    assert anonymize(text, state=first.state)[0] == out
    del first.state["people"][0]["action"]
    assert anonymize(text, state=first.state)[0] == "Nominativo_1 ascolta Parte_7."


@pytest.mark.parametrize("rename", [False, True])
def test_accepted_name_matches_after_the_detection_cue_is_deleted(rename):
    first = analyze("Il sig. Zappacosta firma.")
    person, = first.state["people"]
    if rename:
        person.update(role="locatrice", placeholder="Parte_7")
    out, report = anonymize("Zappacosta replica.", roles=True, state=first.state)
    assert out == person["placeholder"] + " replica."
    assert report.state["people"] == [person]
    assert report.entity_records[0].entity_id == person["id"]


def test_absent_entity_reserves_id_and_tag_for_later_revisions():
    _, first = anonymize("Marta D'Angelo firma.", state={"people": [{"name": "Marta D’Angelo"}]})
    _, second = anonymize("Il sig. Zappacosta firma.", state=first.state)
    assert second.mapping == {"Zappacosta": "Nominativo_2"}
    out, third = anonymize("Zappacosta replica. D'ANGELO MARTA firma.", state=second.state)
    assert out == "Nominativo_2 replica. Nominativo_1 firma."
    assert first.state["people"][0].items() <= third.state["people"][0].items()
    assert third.state["people"][0]["aliases"] == ["D'ANGELO MARTA"]


def test_structured_types_and_labels_are_independent_and_replay_without_cues():
    raw = ("C.F. RSSMRA80A01H501U; P.IVA 01234567890; IBAN IT60X0542811101000000123456; "
           "targa AB123CD; tel. 0422 541 337; email studio@example.test. Residente in Via Roma 12.")
    first = analyze(raw)
    rows = {r["type"]: r for r in first.state["data"]}
    assert set(rows) >= {"cf", "iva", "iban", "targa", "telefono", "email", "indirizzo"}
    rows["iva"]["action"] = "keep"
    rows["email"].update(placeholder="Contatto_7", aliases=["ufficio@example.test"])
    current = "01234567890 / ufficio@example.test / 0422 541 337"
    out, report = anonymize(current, state=first.state)
    assert out == "01234567890 / Contatto_7 / Telefono_1"
    assert not report.residuals
    assert report.state == first.state


def test_missing_data_type_comes_from_detection_or_falls_back_to_dato():
    state = {"data": [{"value": "studio@example.test"}, {"value": "zefiro"}]}
    out, report = anonymize("studio@example.test e zefiro", state=state)
    assert out == "Email_1 e Dato_1"
    assert [r["type"] for r in report.state["data"]] == ["email", "dato"]


def test_shared_surname_stays_neutral_and_can_be_assigned_at_one_passage():
    rules = {"people": [{"id": "a", "name": "Marta Zappacosta", "role": "giudice", "action": "keep",
                         "aliases": ["Zappacosta"]},
                        {"id": "b", "name": "Paolo Zappacosta", "role": "ricorrente"}]}
    text = "Paolo Zappacosta replica. Marta Zappacosta firma. Zappacosta insiste."
    out, report = anonymize(text, roles=True, state=rules)
    assert out == "Ricorrente_1 replica. Marta Zappacosta firma. Nominativo_1 insiste."
    assert report.status == "needs_review"
    report.state["occurrences"].append(dict(at("redact", "Zappacosta", suffix=" insiste."), entity_id="b"))
    out, report = anonymize(text, roles=True, state=report.state)
    assert out == "Ricorrente_1 replica. Marta Zappacosta firma. Ricorrente_1 insiste."


def test_person_keep_inside_longer_private_name_yields_to_whole_name():
    rules = {"people": [{"name": "Marta Quercetani", "role": "giudice"},
                        {"name": "Marta Quercetani Zappacosta", "role": "testimone"}]}
    out, report = anonymize("Marta Quercetani Zappacosta firma.", state=rules,
                            keep_roles=["giudice"], roles=True)
    assert out == "Testimone_1 firma."
    assert report.warnings


@pytest.mark.parametrize("action", ["keep", "redact"])
def test_partial_saved_match_cannot_expose_a_longer_identifier(action):
    state = {"data": [{"value": "zefiro", "action": action}]}
    out, report = anonymize("zefiro e zefiro@example.test", state=state)
    assert out == ("zefiro" if action == "keep" else "Dato_1") + " e Email_1"
    assert report.warnings


@pytest.mark.parametrize("text,expected", [
    ("Nota. Prima: zefiro. **Dopo**: zefiro.", "Nota. Prima: zefiro. Dopo: Dato_1."),
    ("Dopo: zefiro. Prima: zefiro.", "Dopo: Dato_1. Prima: zefiro."),
    ("Prima: zefiro. Altri zefiro. Dopo: zefiro.", "Prima: zefiro. Altri zefiro. Dopo: Dato_1."),
    ("Prima: zefiro.", None), ("Dopo: levante.", None), ("Infine: zefiro.", None),
    ("Dopo: zefiro. Dopo: zefiro.", None),
])
def test_unlinked_occurrence_survives_edits_without_promoting_the_quote(text, expected):
    old = analyze("Prima: zefiro.\nDopo: zefiro.")
    start = old.text.rindex("zefiro")
    anchor = TextAnchor.capture(old.text, start, start + 6)
    choice = {"action": "redact", "anchor": asdict(anchor)}
    _, first = anonymize(old.text, state={"occurrences": [choice]})
    saved, = first.state["occurrences"]
    assert saved["placeholder"] == "Dato_1"
    assert first.state["data"] == first.state["people"] == []
    out, report = anonymize(text, state=first.state)
    assert out == (text if expected is None else expected)
    assert report.unresolved == ([saved] if expected is None else [])
    if expected is None:
        assert report.status == "needs_review"


def test_local_redactions_of_the_same_quote_have_independent_placeholders():
    text = "A: zefiro. B: zefiro."
    rules = {"occurrences": [at("redact", "zefiro", prefix=p) for p in ("A: ", "B: ")]}
    out, report = anonymize(text, state=rules)
    assert out == "A: Dato_1. B: Dato_2."
    assert report.entities == 2
    assert "zefiro" not in report.mapping
    assert anonymize("B: zefiro. A: zefiro.", state=report.state)[0] == "B: Dato_2. A: Dato_1."


def test_linked_redaction_of_an_absent_person_tracks_an_edited_name_and_tag():
    state = {"people": [{"id": "p1", "name": "Marta Quercetani", "role": "ricorrente", "action": "keep"}],
             "occurrences": [dict(at("redact", "x", prefix="firma "), entity_id="p1")]}
    out, first = anonymize("firma x", state=state, roles=True)
    assert out == "firma Ricorrente_1"
    first.state["people"][0].update(name="Marta Zappacosta", placeholder="Parte_7")
    out, second = anonymize("Marta Zappacosta. firma x", state=first.state)
    assert out == "Marta Zappacosta. firma Parte_7"
    assert second.entity_records[0].action == "mixed"


def test_dismiss_is_local_and_never_prevents_a_later_redaction():
    state = {"occurrences": [at("dismiss", "Bosco Verde", prefix="qui: ")]}
    text = "qui: Bosco Verde. lì: Bosco Verde."
    _, report = anonymize(text, state=state, first_names=False)
    assert [(f.text, f.start) for f in report.residuals] == [("Bosco Verde", text.rindex("Bosco Verde"))]
    report.state["data"].append({"value": "Bosco Verde"})
    assert anonymize(text, state=report.state, first_names=False)[0] == "qui: Dato_1. lì: Dato_1."


def test_unresolved_or_partial_exception_keeps_other_choices_and_detection():
    rules = {"occurrences": [at("keep", "zefiro"), at("redact", "grecale"), at("keep", "missing")]}
    out, report = anonymize("grecale / zefiro@example.test", state=rules)
    assert out == "Dato_1 / Email_1"
    assert {item["anchor"]["quote"] for item in report.unresolved} == {"zefiro", "missing"}


def test_ambiguous_capture_and_word_edges():
    with pytest.raises(ValueError, match="unique occurrence"):
        TextAnchor.capture("Dopo: zefiro.\nDopo: zefiro.", 6, 12)
    assert TextAnchor.capture("firma Rossi", 6, 11).locate("firma Rossini") is None
    with pytest.raises(ValueError):
        TextAnchor.capture("ciao", 0, 5)


@pytest.mark.parametrize("state", [
    {"terms": []}, {"discovery_revision": "invalid"}, {"data": "wrong"}, {"people": [{"name": ""}]},
    {"people": [{"name": "Marta D'Angelo"}, {"name": "D’ANGELO MARTA"}]},
    {"people": [{"name": "Ada", "id": "x"}], "data": [{"value": "a", "id": "x"}]},
    {"data": [{"value": "x", "placeholder": "A"}, {"value": "y", "placeholder": "A"}]},
    {"data": [{"value": "a", "action": "mixed"}]}, {"data": [{"value": "b", "type": "typo"}]},
    {"data": [{"value": "a", "aliases": "b"}]}, {"people": [{"name": "Ada", "role": "typo"}]},
    {"occurrences": [dict(at("redact", "x"), entity_id="missing")]},
    {"occurrences": [dict(at("keep", "x"), placeholder="Only_1")]},
])
def test_invalid_state_is_rejected_before_use(state):
    with pytest.raises(ValueError):
        anonymize("sample", state=state)


def test_inferred_counsel_match_cannot_swallow_the_advocate_general_heading():
    raw = "CONCLUSIONI DELL'AVVOCATO GENERALE\nMARTA QUERCETANI\npresentate l'11 settembre."
    output, report = anonymize(raw, keep_roles=("giudice",))
    assert output == raw
    assert report.protected == ["MARTA QUERCETANI"]

def test_policy_keep_is_consistent_when_a_unique_surname_appears_first():
    text = "Rossi insiste. L'avv. Marta Rossi dichiara."
    out, first = anonymize(text, keep_roles=["avvocato"])
    assert out == text
    assert first.state["people"][0]["action"] == "keep"
    assert anonymize(text, state=first.state)[0] == text


def test_replay_of_spaced_initials_without_any_detection_cue():
    _, first = anonymize("ricorso proposto da A. G., che firma.", initials=True)
    row, = first.state["people"]
    assert "A. G." in row["aliases"]
    assert anonymize("oggi A. G. firma", state=first.state)[0] == "oggi Nominativo_1 firma"


def test_alias_identified_separately_by_the_detector_shares_the_document_identity():
    state = {"people": [{"name": "Marta Zappacosta", "aliases": ["Elia Quercetani"],
                         "placeholder": "Parte_7"}]}
    out, report = anonymize("L'avv. Elia Quercetani firma. Quercetani replica.", state=state)
    assert out == "L'avv. Parte_7 firma. Parte_7 replica."
    assert len(report.state["people"]) == 1


def test_ambiguous_overlapping_passage_choices_do_not_depend_on_order():
    rules = [at("keep", "progetto zefiro"), at("redact", "zefiro")]
    for choices in (rules, rules[::-1]):
        out, report = anonymize("progetto zefiro", state={"occurrences": choices})
        assert out == "progetto zefiro"
        assert report.unresolved == choices
        assert report.status == "needs_review"


def test_same_source_preserves_birthplace_scope_after_replay_or_renaming():
    text = "Tribunale di Roma. Nato a Roma il 03/04/1960. Email studio@example.test."
    output, first = anonymize(text)
    assert output == "Tribunale di Roma. Nato a Luogo_1 il Data_nascita_1. Email Email_1."
    state = json.loads(json.dumps(first.state))
    assert anonymize(text, state=state)[0] == output

    # A label change and a separate review choice leave the court seat visible.
    next(r for r in state["data"] if r["type"] == "luogo")["placeholder"] = "Città_A"
    next(r for r in state["data"] if r["type"] == "email")["action"] = "keep"
    revised, report = anonymize(text, state=state)
    assert revised == "Tribunale di Roma. Nato a Città_A il Data_nascita_1. Email studio@example.test."
    assert anonymize(text, state=report.state)[0] == revised


def test_new_uncued_occurrence_is_matched_even_if_fresh_discovery_finds_the_same_rows():
    original = "P.IVA 01234567890."
    output, first = anonymize(original)
    assert output == "P.IVA IVA_1."
    edited = original + " Riferimento 01234567890."
    assert anonymize(edited)[0].endswith("Riferimento 01234567890.")
    assert anonymize(edited, state=first.state)[0] == "P.IVA IVA_1. Riferimento IVA_1."

def test_initial_metadata_can_still_request_document_wide_matching():
    text = "Tribunale di Roma. Nato a Roma."
    _, first = anonymize(text)
    city, = first.state["data"]
    # A caller supplying ordinary metadata can request all mentions on the first run.
    output, _ = anonymize(text, state={"data": [city]})
    assert output == "Tribunale di Luogo_1. Nato a Luogo_1."


def test_round_trip_uses_the_normalized_source():
    text = "Tribunale di Roma. Nato a Roma."
    expected, report = anonymize(text)
    assert anonymize("Tribunale di **Roma**. Nato a Roma.", state=report.state)[0] == expected
