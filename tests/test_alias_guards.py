"""Places, organisations and fragments are not people, even when a list says otherwise.

Each case was met in the consolidated Cassazione corpus, where the first-name list and the
party cues turned them into ``Nominativo_N``.
"""

import pytest

from pseudonimizzatore_legale import Config, anonymize

CORPUS = Config(companies="person_named", roles=True)


@pytest.mark.parametrize(
    "text,kept",
    [
        # a place whose name starts like a person's: a prefix of a comune, a region
        ("Con ordinanza il Tribunale di Santa Maria Capua Vetere, a seguito del riesame, "
         "ha deciso.", "Santa Maria Capua"),
        ("Si erano trasferiti nel Comune di Fara Gera d'Adda.", "Fara Gera"),
        ("La Commissione tributaria della regione Emilia Romagna ha accolto l'appello.",
         "Emilia Romagna"),
        # a bank or an institute: its name is not a person's
        ("La notifica è stata fatta alla Banca Popolare Antoniana Veneta\ns.p.a. di Padova.",
         "Antoniana Veneta"),
        ("contro\nI.N.P.S. - ISTITUTO NAZIONALE DELLA PREVIDENZA SOCIALE C.F. 80078750587, "
         "in persona del legale rappresentante pro tempore", "NAZIONALE DELLA PREVIDENZA SOCIALE"),
        # a slice of an ALL-CAPS run cut at a head word
        ("contro\nRISCOSSIONE SICILIA SPA, AGENTE PER LA RISCOSSIONE\nDELLA PROVINCIA DI AGRIGENTO, "
         "in persona del legale rappresentante pro tempore", "AGENTE PER LA"),
    ],
)
def test_a_place_an_institute_or_a_fragment_is_kept(text, kept):
    output, _ = anonymize(text, CORPUS)
    assert kept in output


def test_a_bare_token_does_not_follow_its_name_into_lower_case():
    text = ("proposto da: Zanoni Impianti, rappresentato e difeso dall'avv. Luca Bianchi.\n"
            "La carenza degli impianti era evidente; Zanoni Impianti non rispose.")
    output, _ = anonymize(text, CORPUS)
    assert "degli impianti" in output
    assert "Zanoni" not in output


def test_a_comune_is_also_known_by_its_leading_words():
    from pseudonimizzatore_legale.seeds import places

    names = places()
    assert {"santa maria capua vetere", "santa maria capua", "emilia romagna"} <= names
    assert "maria" not in names                      # one word alone is never a prefix
    assert "mario rossi" not in names
