"""Putting the originals back into a text written with the tags (`restore`).

All names are invented.
"""
import json

import pytest

from pseudonimizzatore_legale import Config, anonymize, normalize, restore


def saved(state):
    """The state as a caller gets it back after storing it as JSON."""
    return json.loads(json.dumps(state))


def test_a_document_written_with_one_spelling_per_identity_comes_back_whole():
    source = "Il ricorrente Mario Rossi, C.F. RSSMRA80A01H501U, è rappresentato dall'avv. Laura Bianchi."
    output, report = anonymize(source)
    text, restoration = restore(output, saved(report.state))
    assert text == normalize(source)
    assert restoration.restored == {"Nominativo_1": 1, "CF_1": 1, "Nominativo_2": 1}
    assert restoration.unknown == []


def test_a_person_comes_back_under_the_name_of_the_row_whatever_spelling_the_source_used():
    source = ("sul ricorso proposto da\nMALASPINA FERRUCCIO\n-ricorrente-\n"
              "Ferruccio Malaspina insiste. Il Malaspina ricorre.")
    output, report = anonymize(source, roles=True)
    assert output.count("Ricorrente_1") == 3
    assert restore(output, report.state)[0] == (
        "sul ricorso proposto da\nFerruccio Malaspina\n-ricorrente-\n"
        "Ferruccio Malaspina insiste. Il Ferruccio Malaspina ricorre.")


def test_a_name_the_source_wrote_only_in_capitals_comes_back_in_capitals():
    source = "sul ricorso proposto da\nMALASPINA FERRUCCIO\n-ricorrente-\nIl Malaspina ricorre."
    output, report = anonymize(source, roles=True)
    assert restore("Ricorrente_1 ha ragione.", report.state)[0] == "MALASPINA FERRUCCIO ha ragione."


def test_a_tag_is_read_however_a_writer_formats_it():
    state = {"people": [{"name": "Ada Malaspina", "placeholder": "Nominativo_1"}],
             "data": [{"value": "MLSDAA61D43I952X", "type": "cf", "placeholder": "CF_1"},
                      {"value": "Brambillasca Costruzioni S.r.l.", "type": "società",
                       "placeholder": "Società_1"}]}
    draft = ("# RICORSO DI NOMINATIVO_1\n"
             "**Nominativo_1**, C.F. CF\\_1, socia di _Società_1_; nominativo_1 insiste.")
    text, restoration = restore(draft, state)
    assert text == ("# RICORSO DI ADA MALASPINA\n"
                    "**Ada Malaspina**, C.F. MLSDAA61D43I952X, socia di _Brambillasca Costruzioni "
                    "S.r.l._; Ada Malaspina insiste.")
    assert restoration.restored == {"Nominativo_1": 3, "CF_1": 1, "Società_1": 1}


def test_a_tag_is_a_whole_word():
    state = {"people": [{"name": "Ada Malaspina", "placeholder": "Nominativo_1"},
                        {"name": "Marta Zappacosta", "placeholder": "Nominativo_12"}]}
    draft = "Nominativo_12 e Nominativo_1; non XNominativo_1, Nominativo_1_bis, Nominativo_1a."
    text, restoration = restore(draft, state)
    assert text == ("Marta Zappacosta e Ada Malaspina; "
                    "non XNominativo_1, Nominativo_1_bis, Nominativo_1a.")
    assert restoration.unknown == []


def test_a_tag_the_state_does_not_know_stays_and_is_reported():
    state = {"data": [{"value": "studio@example.test", "type": "email", "placeholder": "Contatto_7"}]}
    draft = "Scrivere a Contatto_7 o a Contatto_3. Nominativo_9 e Nominativo\\_9 tacciono. Il numero 1 resta."
    text, restoration = restore(draft, state)
    assert text == ("Scrivere a studio@example.test o a Contatto_3. "
                    "Nominativo_9 e Nominativo\\_9 tacciono. Il numero 1 resta.")
    assert restoration.unknown == ["Contatto_3", "Nominativo_9"]


def test_a_passage_redacted_on_its_own_comes_back_as_its_quote():
    note = "Il progetto Aurora parte. Evento pubblico: Aurora."
    state = {"occurrences": [{"action": "redact",
                              "anchor": {"quote": "Aurora", "prefix": "Il progetto ", "suffix": " parte"}}]}
    output, report = anonymize(note, state=state)
    assert output == "Il progetto Dato_1 parte. Evento pubblico: Aurora."
    assert restore(output, saved(report.state))[0] == note


def test_a_kept_person_redacted_at_one_passage_comes_back_under_their_name():
    state = {"people": [{"name": "Ada Malaspina", "role": "giudice", "action": "keep"}]}
    source = "Presidente Ada Malaspina. Firma: Ada Malaspina."
    state["occurrences"] = [{"action": "redact", "entity_id": "p1",
                             "anchor": {"quote": "Ada Malaspina", "prefix": "Firma: ", "suffix": "."}}]
    state["people"][0]["id"] = "p1"
    output, report = anonymize(source, state=state)
    assert output == "Presidente Ada Malaspina. Firma: Nominativo_1."
    assert restore(output, saved(report.state))[0] == source


def test_a_state_carried_across_documents_restores_both():
    config = Config(roles=True)
    first, report = anonymize("Ricorso proposto da Ferruccio Malaspina, C.F. MLSFRC61D03I952X.",
                              config=config)
    carried = {"people": report.state["people"], "data": report.state["data"]}
    second, report = anonymize("Il Malaspina, difeso dall'avv. Ortensia Vimercati, insiste.",
                               config=config, state=carried)
    assert "Ricorrente_1" in second and "Difensore_1" in second
    text, restoration = restore("Ricorrente_1 (CF_1), con Difensore_1.", saved(report.state))
    assert text == "Ferruccio Malaspina (MLSFRC61D03I952X), con Ortensia Vimercati."
    assert restoration.unknown == []


def test_a_malformed_state_is_refused():
    with pytest.raises(ValueError):
        restore("Nominativo_1", {"people": [{"placeholder": "Nominativo_1"}]})
