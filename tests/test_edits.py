"""The review API: `analyze` + `render`, and reviewer edits replayed as `Edits`."""
import subprocess
import sys
from pathlib import Path

import pytest

from pseudonimizzatore_legale import (
    Config, Edits, Mention, analyze, anonymize, normalize, render,
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


def run(edits=Edits(), **kwargs):
    # Role tags make these tests readable: which entity ended up where.
    analysis = analyze(DOC, edits=edits, **kwargs)
    output, report = render(analysis)
    return analysis, output, report


def anonymize_with(edits, text):
    analysis = analyze(text, edits=edits)
    return (analysis, *render(analysis))


def row(analysis, tag):
    return next(item for item in analysis.entities if item.entity_id == tag)


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
        # Replaying a document's own tags changes nothing.
        replayed, _ = render(analyze(
            raw, config, edits=Edits(prior_tags=tuple(analysis.mapping.items()))))
        assert replayed == expected, path


def test_analysis_rows_carry_tags_aliases_and_spans():
    analysis, output, _ = run()
    party = row(analysis, "Ricorrente_1")
    assert party.aliases == ("Lucia Rossi", "Rossi", "ROSSI LUCIA")
    assert [analysis.text[start:end] for start, end in party.spans] == [
        "ROSSI LUCIA", "Rossi", "Lucia Rossi"]
    assert party.action == "redact"
    assert output.count("Ricorrente_1") == 3


def test_user_person_is_seeded_and_propagated():
    analysis, output, _ = run(Edits(people=(("Zappacosta", "Nominativo"),)))
    assert "Zappacosta" not in output
    assert "teste Nominativo_1" in output
    assert "user" in row(analysis, "Nominativo_1").sources[0]


def test_user_person_folds_into_a_detected_one_and_sets_its_role():
    _, output, report = run(Edits(people=(("Lucia Rossi", "Resistente"),)))
    assert "Resistente_1" in output and "Ricorrente_1" not in output
    assert len([tag for tag in report.mapping.values() if tag.startswith("Resistente")]) == 1


def test_user_person_skips_the_seed_guards():
    # "Via" opens a street, so detection would refuse it as a name.
    _, output, _ = anonymize_with(Edits(people=(("Via Lattea", "Nominativo"),)),
                                  "Il teste Via Lattea conferma.")
    assert output == "Il teste Nominativo_1 conferma."



def test_user_person_overrides_a_judge():
    _, output, report = run(Edits(people=(("Bianchi Luca", "Resistente"),)))
    assert "BIANCHI LUCA" not in output and "Bianchi Luca" not in output
    assert report.protected == []
    assert report.warnings == []


def test_user_term_is_redacted_everywhere_at_top_priority():
    text = "Il canone di 1.200 euro. Canone di\n1.200 euro versato."
    _, output, report = anonymize_with(Edits(terms=(("canone di 1.200 euro", "Importo"),)), text)
    assert output == "Il Importo_1. Importo_1 versato."
    assert report.mapping == {"canone di 1.200 euro": "Importo_1"}


def test_exclude_gives_back_an_entity():
    _, output, report = run(Edits(exclude=("Rossi",)))
    assert "ROSSI LUCIA" in output and "La Rossi" in output and "Lucia Rossi" in output
    assert "Ricorrente_1" not in report.mapping.values()


def test_exclude_keeps_a_surname_shared_with_another_person_redacted():
    text = ("Il sig. Mario Zappacosta e la sig.ra Anna Zappacosta ricorrono. "
            "Zappacosta insiste.")
    _, output, _ = anonymize_with(Edits(exclude=("Mario Zappacosta",)), text)
    assert output == ("Il sig. Mario Nominativo_1 e la sig.ra Nominativo_2 ricorrono. "
                      "Nominativo_1 insiste.")


def test_keep_span_leaves_one_occurrence_and_forces_review():
    analysis, output, report = run(Edits(keep_spans=(span("Rossi", DOC.index("La Rossi")),)))
    assert "La Rossi insiste" in output
    assert output.count("Ricorrente_1") == 2
    assert any(item.text == "Rossi" and item.source == "verification:alias"
               for item in report.residuals)
    assert report.status == "needs_review"
    assert any(item.action == "keep" and item.aliases == ("Rossi",)
               for item in analysis.entities)


def test_judge_keep_is_still_exempt_from_review():
    _, _, report = run()
    assert not any(item.text == "BIANCHI LUCA" for item in report.residuals)


def test_include_span_redacts_an_occurrence_as_that_entity():
    _, output, _ = run(Edits(include_spans=((*span("Zappacosta"), "Lucia Rossi"),)))
    assert "teste Ricorrente_1" in output


def test_include_span_of_an_unknown_alias_is_a_new_person():
    _, output, _ = run(Edits(include_spans=((*span("Zappacosta"), "Zappacosta"),)))
    assert "teste Nominativo_1" in output


def test_merge_gives_two_entities_one_tag():
    analysis, output, _ = run(Edits(merge=(("Marco Ferretti", "ROSSI LUCIA"),)))
    assert "avv. Ricorrente_1" in output
    assert "Difensore_1" not in output
    assert "Marco Ferretti" in row(analysis, "Ricorrente_1").aliases


def test_merge_keeps_the_merged_entity_under_verification():
    analysis, _, _ = run(Edits(merge=(("Marco Ferretti", "ROSSI LUCIA"),)))
    assert "Ferretti" in analysis.expected_aliases


def test_placeholder_sets_a_custom_tag():
    _, output, report = run(Edits(placeholders=(("rossi", "Attrice_1"),)))
    assert "Ricorrente_1" not in output
    assert output.count("Attrice_1") == 3
    assert report.mapping["ROSSI LUCIA"] == "Attrice_1"


def test_prior_tags_stop_renumbering_after_an_exclusion():
    text = "Difesi dall'avv. Marco Ferretti e dall'avv. Paolo Gualtieri."
    before = analyze(text)
    assert before.mapping == {"Marco Ferretti": "Difensore_1", "Paolo Gualtieri": "Difensore_2"}
    edits = Edits(exclude=("Marco Ferretti",))
    assert "Difensore_1" in render(analyze(text, edits=edits))[0]
    edits = Edits(exclude=("Marco Ferretti",), prior_tags=tuple(before.mapping.items()))
    output, _ = render(analyze(text, edits=edits))
    assert output == "Difesi dall'avv. Marco Ferretti e dall'avv. Difensore_2."


def test_prior_tags_do_not_carry_a_tag_to_another_role():
    edits = Edits(people=(("Marco Ferretti", "Ricorrente"),),
                  prior_tags=(("Marco Ferretti", "Difensore_1"),))
    output, _ = render(analyze("Difeso dall'avv. Marco Ferretti.", edits=edits))
    assert output == "Difeso dall'avv. Ricorrente_1."


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
