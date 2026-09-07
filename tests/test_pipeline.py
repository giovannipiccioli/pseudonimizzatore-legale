"""Behavioral tests for late policy and high-recall review checks."""
from dataclasses import asdict
import json

from pseudonimizzatore_legale import Config, anonymize
from pseudonimizzatore_legale.model import Candidate, Mention
from pseudonimizzatore_legale.policy import PRI_PERSON_FULL, PRI_PROTECTED, resolve


def test_party_sharing_a_judge_surname_is_not_vetoed():
    text = (
        "Presidente: ROSSI MARIO\n"
        "sul ricorso proposto da\n"
        "ROSSI LUCIA\n"
        "-ricorrente-\n"
        "Lucia Rossi insiste. La Rossi ricorre."
    )
    output, report = anonymize(text)
    assert "ROSSI MARIO" in output
    assert "ROSSI LUCIA" not in output
    assert "Lucia Rossi" not in output
    assert "La Rossi" not in output
    assert len(set(report.mapping.values())) == 1
    assert report.status == "passed_checks"


def test_unhandled_private_person_forces_review():
    text = "La decisione riguarda Antonio De Luca senza altre indicazioni."
    output, report = anonymize(text)
    assert output == text
    assert report.status == "needs_review"
    assert any(item.text == "Antonio De Luca" for item in report.residuals)
    json.dumps(asdict(report), ensure_ascii=False)


def test_verified_judicial_roles_do_not_force_review():
    text = (
        "Presidente: ROSSI MARIO\n"
        "Relatore: BIANCHI LUCA\n"
        "AGENZIA DELLE ENTRATE ricorre."
    )
    output, report = anonymize(text)
    assert output == text
    assert report.status == "passed_checks"
    assert report.residuals == []


def test_successful_party_redaction_passes_checks():
    text = (
        "sul ricorso proposto da\nROSSI LUCIA\n-ricorrente-\n"
        "Lucia Rossi insiste. La Rossi ricorre."
    )
    output, report = anonymize(text)
    assert "Rossi" not in output and "ROSSI" not in output
    assert report.status == "passed_checks"


def test_tags_and_publisher_omissions_do_not_create_review_loop():
    text = "Nominativo_1 e B.S.M. risultano già indicati come (Omissis)."
    _, report = anonymize(text)
    assert report.status == "passed_checks"


def test_policy_is_applied_after_detection():
    text = "ROSSI MARIO"
    person = Candidate(
        mention=Mention(text, 0, len(text), source="ner:test"),
        priority=PRI_PERSON_FULL,
        label="Nominativo",
        value=text,
    )
    judge = Candidate(
        mention=Mention(text, 0, len(text), role="Giudice", kind="JUDGE",
                        source="legal_role:judge"),
        priority=PRI_PROTECTED,
        protection="judge",
    )
    assert resolve([person, judge], len(text), Config())[0].action == "keep"
    assert resolve([person, judge], len(text), Config(keep_judges=False))[0].action == "redact"


def test_legacy_document_profiles_are_source_agnostic_aliases():
    assert Config(profile="cassazione").profile == "legal"
    assert Config(profile="generic").profile == "legal"


def test_offsets_are_explicitly_normalized_input_offsets():
    raw = "Il sig. **Mario** Rossi ricorre."
    output, report = anonymize(raw)
    normalized = "Il sig. Mario Rossi ricorre."
    assert "Mario Rossi" not in output
    assert report.offset_space == "normalized_input"
    assert [normalized[start:end] for start, end in report.replacement_spans] == [
        "Mario Rossi"
    ]


def test_date_of_birth_outranks_case_number_protection():
    text = "Il sig. Mario Rossi, nato il 12/03/1974, ricorre."
    output, report = anonymize(text)
    assert "12/03/1974" not in output
    assert "Data_nascita_1" in output
    assert all(decision.text != "12/03" for decision in report.decisions)


def test_same_identity_with_judicial_and_private_roles_is_redacted_and_reviewed():
    text = (
        "Presidente: DE LUCA ANTONIO\n"
        "Il contribuente Antonio De Luca contesta l'avviso."
    )
    output, report = anonymize(text)
    assert "DE LUCA ANTONIO" not in output
    assert "Antonio De Luca" not in output
    assert report.status == "needs_review"
    assert report.warnings


def test_uncued_capitalized_name_is_a_review_candidate():
    text = "La decisione riguarda Antonio De Luca senza altre indicazioni."
    output, report = anonymize(text)
    assert output == text
    assert report.status == "needs_review"
    assert any(item.source == "verification:name-shape" for item in report.residuals)


def test_uncued_all_common_name_is_a_review_candidate():
    text = "La decisione riguarda Luca Romano senza altre indicazioni."
    output, report = anonymize(text)
    assert output == text
    assert report.status == "needs_review"
    assert any(item.text == "Luca Romano" for item in report.residuals)


def test_strong_legal_cues_accept_names_made_of_common_tokens():
    samples = (
        "Il sig. Giovanni Esposito ricorre.",
        "Il socio Giovanni Esposito impugna.",
    )
    for text in samples:
        output, _ = anonymize(text)
        assert "Giovanni Esposito" not in output


def test_counsel_list_accepts_names_made_of_common_tokens():
    text = "difesi dagli avvocati Mario Rossi, Giovanni Esposito e Luca Romano."
    output, report = anonymize(text)
    for name in ("Mario Rossi", "Giovanni Esposito", "Luca Romano"):
        assert name not in output
    assert report.entities == 3


def test_party_block_accepts_a_name_made_of_common_tokens():
    text = (
        "sul ricorso proposto da\nGIOVANNI ESPOSITO\n-ricorrente-\n"
        "Giovanni Esposito insiste."
    )
    output, _ = anonymize(text)
    assert "GIOVANNI ESPOSITO" not in output
    assert "Giovanni Esposito" not in output


def test_four_token_name_rotation_keeps_one_tag():
    text = (
        "sul ricorso proposto da\nDE LUCA MARIO ANTONIO\n-ricorrente-\n"
        "Mario Antonio De Luca insiste."
    )
    output, report = anonymize(text)
    assert "DE LUCA MARIO ANTONIO" not in output
    assert "Mario Antonio De Luca" not in output
    assert len(set(report.mapping.values())) == 1


def test_report_keeps_legacy_positional_field_order():
    from pseudonimizzatore_legale.core import Report

    report = Report({"Mario Rossi": "Nominativo_1"}, ["BIANCHI LUCA"], 2,
                    [(0, 11)], 0.5)
    assert report.mapping == {"Mario Rossi": "Nominativo_1"}
    assert report.protected == ["BIANCHI LUCA"]
    assert report.replacements == 2
    assert report.replacement_spans == [(0, 11)]
    assert report.risk == 0.5
    assert report.residual_offset_space == "output"
