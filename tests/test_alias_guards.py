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
        # a region written in two halves, the second one read as a name before "rappresentato"
        ("Ricorso della Regione Trentino-Alto Adige, rappresentata e difesa dall'avv. Luca Neri.",
         "Trentino-Alto Adige"),
        ("Ricorso della Regione Friuli-Venezia Giulia, rappresentata e difesa dall'avv. Luca Neri.",
         "Friuli-Venezia Giulia"),
        # public bodies in the plural, or as an office: neither is a party's surname
        ("Le ricorrenti Regioni Calabria e Puglia hanno impugnato la legge. Le Regioni insistono.",
         "Le Regioni insistono"),
        ("Le ricorrenti Province autonome di Trento e di Bolzano. Le Province insistono.",
         "Le Province insistono"),
        ("Il ricorrente Commissario dello Stato ha impugnato la legge. Il Commissario insiste.",
         "Il Commissario insiste"),
        ("nei confronti di Comunità Montana Valdoro, rappresentata e difesa dall'avv. Luca Neri",
         "Comunità Montana Valdoro"),
    ],
)
def test_a_place_an_institute_or_a_fragment_is_kept(text, kept):
    output, _ = anonymize(text, CORPUS)
    assert kept in output


def test_a_name_never_crosses_a_blank_line():
    # "Rovelli Marco" is a spelling of Marco Rovelli, and so is the name wrapped over a line
    # break, but not the end of one paragraph and the start of the next ("DELLA TORRE¶LA CORTE")
    from pseudonimizzatore_legale.model import Entity
    from pseudonimizzatore_legale.seeds import variant_patterns

    full = [p for p, is_full in variant_patterns(Entity("Marco Rovelli", "Nominativo"), 4)
            if is_full]
    for text, hit in (("Rovelli Marco", True), ("Rovelli\nMarco", True),
                      ("Rovelli \n  Marco", True), ("Rovelli\n\nMarco", False)):
        assert any(p.search(text) for p in full) is hit, repr(text)

    # a saved name is read the same way (the surname alone is still an alias of its own)
    state = {"people": [{"name": "Marco Rovelli"}]}
    output, _ = anonymize("Marco\nRovelli firma.\n\nMarco\n\nRovelli", Config(first_names=False),
                          state=state)
    assert output == "Nominativo_1 firma.\n\nMarco\n\nNominativo_1"


def test_a_surname_known_from_its_cue_is_not_a_common_noun():
    text = ("Il teste Sanitari ha riferito. I servizi sanitari erano chiusi, disse SANITARI.\n"
            "Il perito Brambillasca ha confermato; così il bRAMBILLASCA.")
    output, _ = anonymize(text, CORPUS)
    assert "servizi sanitari" in output
    assert not {"Sanitari", "SANITARI", "Brambillasca", "bRAMBILLASCA"} & set(output.split())


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


def test_a_region_is_known_by_the_parts_of_its_name():
    from pseudonimizzatore_legale.seeds import is_region

    assert all(is_region(name) for name in
               ("Alto Adige", "Venezia Giulia", "Friuli", "Emilia", "Emilia-Romagna", "TOSCANA"))
    assert not any(is_region(name) for name in ("Giulia", "Mario Rossi", "Alto Adige Rossi"))


def test_a_region_word_is_a_first_name_only_where_a_cue_says_so():
    output, _ = anonymize("Il ricorrente Emilia-Romagna ha impugnato. Emilia insiste.", CORPUS)
    assert output == "Il ricorrente Emilia-Romagna ha impugnato. Emilia insiste."
    output, _ = anonymize("Mia figlia Emilia studia.", CORPUS)
    assert output == "Mia figlia Nominativo_1 studia."


def test_a_company_after_a_party_word_is_not_a_person():
    text = "Le società Gamma Italia Manufacturing srl e Beta Holdings spa hanno proposto ricorso."
    output, _ = anonymize(text, CORPUS)
    assert "Gamma Italia Manufacturing" in output and "Beta Holdings" in output
