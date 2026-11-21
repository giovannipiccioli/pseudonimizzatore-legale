"""The review API: `analyze` + `render`, and review decisions passed as JSON state."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from pseudonimizzatore_legale import (
    Config, Mention, analyze, anonymize, normalize, render,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = sorted(
    path.with_suffix("").with_suffix(".txt")
    for path in (ROOT / "evaluation" / "corpus").rglob("*.gold.json")
)

DOC = (
    "Presidente: BIANCHI LUCA\n"
    "sul ricorso proposto da\nROSSI LUCIA\n"
    "difesa dall'avv. Marco Ferretti.\n"
    "La Rossi insiste. Sentito il teste Zappacosta, tel. 333 1234567.\n"
    "Lucia Rossi chiede il rimborso a Bianchi Luca."
)


def run(state=None, **kwargs):
    # Role tags make these tests readable: which entity ended up where.
    analysis = analyze(DOC, Config(roles=True, keep_roles=("giudice",)), state=state, **kwargs)
    output, report = render(analysis)
    return analysis, output, report


def anonymize_with(state, text):
    analysis = analyze(text, state=state)
    return (analysis, *render(analysis))


def row(analysis, tag):
    return next(item for item in analysis.entities if item.placeholder == tag)


def span(text, start_at=0):
    start = DOC.index(text, start_at)        # DOC needs no sanitizing: offsets agree
    return start, start + len(text)


def test_fixtures_count():
    assert len(FIXTURES) == 124


@pytest.mark.parametrize("config", [Config(), Config(companies=True)], ids=["default", "companies"])
def test_anonymize_is_render_of_analyze_on_every_fixture(config):
    for path in FIXTURES:
        raw = path.read_text(encoding="utf-8")
        expected, report = anonymize(raw, config)
        analysis = analyze(raw, config)
        output, rendered = render(analysis)
        assert output == expected, path
        assert rendered.mapping == report.mapping, path
        assert rendered.status == report.status, path
        assert rendered.residuals == report.residuals, path
        assert rendered.decisions == report.decisions, path


@pytest.mark.parametrize("config", [
    Config(), Config(companies=True), Config(roles=True, keep_roles=["giudice"], initials=True),
], ids=["default", "companies", "role-tags-and-initials"])
def test_unedited_report_reproduces_exact_text_on_every_fixture(config):
    for path in FIXTURES:
        source = path.read_text(encoding="utf-8")
        first, report = anonymize(source, config)
        saved = json.loads(json.dumps(report.state))
        replayed, _ = anonymize(source, config, state=saved)
        assert replayed == first, path


def test_analysis_rows_carry_tags_aliases_and_spans():
    analysis, output, _ = run()
    party = row(analysis, "Ricorrente_1")
    assert party.aliases == ("Lucia Rossi", "Rossi", "ROSSI LUCIA")
    assert [analysis.text[start:end] for start, end in party.spans] == [
        "ROSSI LUCIA", "Rossi", "Lucia Rossi"]
    assert party.action == "redact"
    assert output.count("Ricorrente_1") == 3


def test_user_person_is_seeded_and_propagated():
    analysis, output, _ = run({"people": [{"name": "Zappacosta", "role": "Nominativo"}]})
    assert "Zappacosta" not in output
    assert "teste Nominativo_1" in output
    assert "user" in row(analysis, "Nominativo_1").sources[0]


def test_user_person_folds_into_a_detected_one_and_sets_its_role():
    _, output, report = run({"people": [{"name": "Lucia Rossi", "role": "Resistente"}]})
    assert "Resistente_1" in output and "Ricorrente_1" not in output
    assert len([tag for tag in report.mapping.values() if tag.startswith("Resistente")]) == 1


def test_user_person_skips_the_seed_guards():
    # "Via" opens a street, so detection would refuse it as a name.
    _, output, _ = anonymize_with({"people": [{"name": "Via Lattea", "role": "Nominativo"}]},
                                  "Il teste Via Lattea conferma.")
    assert output == "Il teste Nominativo_1 conferma."



def test_user_person_overrides_a_judge():
    _, output, report = run({"people": [{"name": "Bianchi Luca", "role": "Resistente"}]})
    assert "BIANCHI LUCA" not in output and "Bianchi Luca" not in output
    assert report.protected == []
    assert report.warnings == []


def test_user_term_is_redacted_everywhere_at_top_priority():
    text = "Il canone di 1.200 euro. Canone di\n1.200 euro versato."
    _, output, report = anonymize_with({"data": [{"value": "canone di 1.200 euro", "placeholder": "Importo_1"}]}, text)
    assert output == "Il Importo_1. Importo_1 versato."
    assert report.mapping == {"canone di 1.200 euro": "Importo_1"}


def test_document_keep_is_audited():
    _, output, report = run({"people": [{"name": "Lucia Rossi", "action": "keep",
                                         "aliases": ["Rossi"]}]})
    assert "ROSSI LUCIA" in output and "La Rossi" in output and "Lucia Rossi" in output
    assert "Ricorrente_1" not in report.mapping.values()
    assert any(row.action == "keep" and "Rossi" in row.aliases for row in report.entity_records)


def test_keep_one_occurrence_leaves_the_entity_default_intact():
    choice = {"action": "keep", "anchor": {"quote": "Rossi", "prefix": "La ", "suffix": " insiste."}}
    analysis, output, report = run({"occurrences": [choice]})
    assert "La Rossi insiste" in output
    assert output.count("Ricorrente_1") == 2
    assert row(analysis, "Ricorrente_1").action == "mixed"
    assert any(item.text == "Rossi" for item in report.residuals)


def test_judge_keep_is_still_exempt_from_review():
    _, _, report = run()
    assert not any(item.text == "BIANCHI LUCA" for item in report.residuals)


def test_alias_joins_two_full_spellings():
    analysis, output, _ = run({"people": [{"name": "ROSSI LUCIA", "role": "ricorrente",
                                           "aliases": ["Marco Ferretti"]}]})
    assert "avv. Ricorrente_1" in output
    assert "Difensore_1" not in output
    assert "Marco Ferretti" in row(analysis, "Ricorrente_1").aliases


def test_placeholder_sets_a_custom_tag():
    _, output, report = run({"people": [{"name": "Lucia Rossi", "placeholder": "Attrice_1"}]})
    assert output.count("Attrice_1") == 3
    assert set(report.mapping.values()) >= {"Attrice_1"}


def test_saved_tag_survives_a_role_change_and_another_person_being_kept():
    text = "Difesi dall'avv. Marco Ferretti e dall'avv. Paolo Gualtieri."
    before = analyze(text, Config(roles=True))
    first, second = before.state["people"]
    first["action"] = "keep"
    second["role"] = "ricorrente"
    output, _ = anonymize(text, roles=True, state=before.state)
    assert output == "Difesi dall'avv. Marco Ferretti e dall'avv. Difensore_2."


def test_external_mentions_are_one_more_seed_source():
    analysis, output, _ = run(mentions=(Mention("Zappacosta", *span("Zappacosta"),
                                                source="ner:browser"),))
    assert "teste Nominativo_1" in output
    assert "ner:browser" in row(analysis, "Nominativo_1").sources[0]


def test_mentions_are_read_in_normalized_coordinates():
    raw = "**Il teste** Zappacosta conferma."
    text = normalize(raw)
    start = text.index("Zappacosta")
    output, _ = render(analyze(raw, mentions=(Mention("?", start, start + 10),)))
    assert output == "Il teste Nominativo_1 conferma."


def test_importing_the_package_does_not_load_the_batch_driver():
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import pseudonimizzatore_legale as p; "
            "assert 'multiprocessing' not in sys.modules; "
            "assert 'pseudonimizzatore_legale.batch' not in sys.modules; "
            "p.anonymize_batch")
    subprocess.run([sys.executable, "-c", code, str(ROOT)], check=True)
