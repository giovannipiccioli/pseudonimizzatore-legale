import pytest

from evaluation.metrics import group_entities, score_output


def test_surface_forms_are_grouped_into_one_identity():
    gold = {
        "must_remove": [
            "MALASPINA FERRUCCIO",
            "Ferruccio Malaspina",
            "Malaspina",
            "RSSMRA80A01H501U",
        ],
        "must_keep": [],
    }
    groups = group_entities(gold)
    assert len(groups) == 2
    assert any(set(group.values) == {
        "MALASPINA FERRUCCIO", "Ferruccio Malaspina", "Malaspina"
    } for group in groups)


def test_one_remaining_alias_fails_the_whole_entity():
    original = "MALASPINA FERRUCCIO ricorre. In seguito parla Malaspina."
    output = "Ricorrente_1 ricorre. In seguito parla Malaspina."
    gold = {
        "must_remove": ["MALASPINA FERRUCCIO", "Malaspina"],
        "must_keep": [],
    }
    score = score_output(original, output, gold, [(0, 20)])
    assert score.surface_ok == 1
    assert score.entity_ok == 0
    assert score.entity_partial == 1


def test_repeated_surface_must_be_removed_everywhere():
    original = "Malaspina ricorre. Malaspina insiste."
    output = "Ricorrente_1 ricorre. Malaspina insiste."
    gold = {"must_remove": ["Malaspina"], "must_keep": []}
    score = score_output(original, output, gold, [(0, 9)])
    assert score.surface_ok == 0
    assert score.entity_ok == 0


def test_prediction_precision_penalizes_an_unrelated_replacement():
    original = "Mario Rossi vive a Roma"
    output = "Nominativo_1 vive a Luogo_1"
    gold = {"must_remove": ["Mario Rossi"], "must_keep": ["Roma"]}
    score = score_output(original, output, gold, [(0, 11), (19, 23)])
    assert (score.prediction_ok, score.prediction_total) == (1, 2)
    assert (score.predicted_char_ok, score.predicted_char_total) == (11, 15)
    assert score.keep_ok == 0


def test_explicit_entity_groups_work_without_legacy_surface_list():
    original = "Mario Rossi ricorre. Rossi insiste."
    output = "Nominativo_1 ricorre. Rossi insiste."
    gold = {
        "must_remove_entities": [
            {"kind": "name", "values": ["Mario Rossi", "Rossi"]}
        ],
        "must_keep": [],
    }
    score = score_output(original, output, gold, [(0, 11)])
    assert score.surface_total == 2
    assert score.entity_total == 1
    assert score.entity_ok == 0
    assert score.entity_partial == 1


def test_legacy_values_missing_from_explicit_groups_become_entities():
    gold = {
        "must_remove": ["Mario Rossi", "RSSMRA80A01H501U"],
        "must_remove_entities": [
            {"kind": "name", "values": ["Mario Rossi"]},
        ],
        "must_keep": [],
    }
    score = score_output(
        "Mario Rossi RSSMRA80A01H501U",
        "Mario Rossi RSSMRA80A01H501U",
        gold,
        [],
    )
    assert score.entity_total == 2
    assert score.entity_missed == 2


def test_duplicate_surface_across_explicit_groups_is_rejected():
    gold = {
        "must_remove_entities": [
            ["Mario Rossi"],
            ["Mario Rossi", "Rossi"],
        ]
    }
    with pytest.raises(ValueError, match="multiple entity groups"):
        group_entities(gold)
