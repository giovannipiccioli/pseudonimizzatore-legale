"""End-to-end behaviour of `anonymize()`.

The fixture is a redacted-shape Cassazione header: same structure as the real files,
invented names.
"""
import regex as re
import pytest

from pseudonimizzatore_legale import Config, anonymize

DECISION = """Civile Ord. Sez. 5 Num. 15211 Anno 2025
Presidente: CATALDI MICHELE
Relatore: CHIECA DANILO
Data pubblicazione: 07/06/2025
ORDINANZA
sul ricorso iscritto al n. 17382/2023 R.G. proposto da
AGENZIA DELLE ENTRATE, in persona del Direttore pro tempore,
domiciliata in Roma alla via dei Portoghesi n. 12 presso gli uffici
dell'Avvocatura Generale dello Stato
 -ricorrente-
 contro
BENATTI ROSSELLA, rappresentata e difesa dall'avv. Gallusi Sandro
(domicilio digitale: sandro.gallusi@ordineavvocati.it)
 -controricorrente-
avverso la SENTENZA della CORTE DI GIUSTIZIA TRIBUTARIA n. 274/2023
FATTI DI CAUSA
A seguito di controllo formale della dichiarazione presentata da Rossella Benatti
ai fini dell'IRPEF per l'anno 2013, la Direzione Provinciale di Reggio nell'Emilia
procedeva all'iscrizione a ruolo. La Benatti impugnava la cartella.
"""


class TestLocalConsistency:
    """A party named three ways must end up as one tag.

    The single most important behaviour in the library: a document whose header is
    pseudonymized but whose body still says "La Benatti" is not anonymized at all.
    """

    def test_all_surface_forms_of_a_party_collapse_to_one_tag(self):
        out, rep = anonymize(DECISION)
        assert "BENATTI" not in out and "Benatti" not in out
        tags = {t for t in re.findall(r"\b(?:Ricorrente|Resistente)_\d+", out)}
        assert len(tags) == 1, f"header and body mentions disagree: {tags}"

    def test_reversed_token_order_is_the_same_person(self):
        out, _ = anonymize(DECISION)
        # "BENATTI ROSSELLA" (header) and "Rossella Benatti" (body) are one entity
        assert "Rossella" not in out

    def test_counsel_is_pseudonymized(self):
        out, _ = anonymize(DECISION)
        assert "Gallusi" not in out
        assert "Difensore_1" in out


class TestLateKeepPolicy:
    def test_judges_stay_in_clear(self):
        out, rep = anonymize(DECISION)
        assert "CATALDI MICHELE" in out
        assert "CHIECA DANILO" in out
        assert "CATALDI MICHELE" in rep.protected

    def test_public_bodies_stay_in_clear(self):
        out, _ = anonymize(DECISION)
        assert "AGENZIA DELLE ENTRATE" in out
        assert "Avvocatura Generale dello Stato" in out

    def test_case_numbers_stay_in_clear(self):
        out, _ = anonymize(DECISION)
        assert "n. 274/2023" in out
        assert "17382/2023" in out

    def test_places_stay_in_clear(self):
        out, _ = anonymize(DECISION)
        assert "Roma" in out
        assert "Reggio nell'Emilia" in out

    def test_case_numbers_can_be_turned_off(self):
        out, _ = anonymize(DECISION, Config(keep_case_numbers=False))
        assert "n. 274/2023" in out  # still kept: nothing claims that span


class TestStructuredIdentifiers:
    def test_email_removed(self):
        out, _ = anonymize(DECISION)
        assert "sandro.gallusi@ordineavvocati.it" not in out
        assert "Email_1" in out

    def test_codice_fiscale_removed(self):
        out, _ = anonymize("Il sig. Mario Rossi, C.F. RSSMRA80A01H501U, ricorre.")
        assert "RSSMRA80A01H501U" not in out
        assert re.search(r"CF_\d+", out)

    def test_email_inside_an_institution_domain_is_still_removed(self):
        # An unbounded institution match used to shield this address.
        text = "ope legis domicilia (pec.: ags.rm@mailcert.avvocaturastato.it);"
        out, _ = anonymize(text)
        assert "ags.rm@mailcert.avvocaturastato.it" not in out


class TestNoCorruption:
    """Ordinary Italian must survive.

    Propagating a name whose surname collides with a common word is how an anonymizer
    silently destroys the corpus it was meant to produce — every "del" in the document
    replaced by a tag.
    """

    def test_function_words_are_never_substituted(self):
        out, _ = anonymize(DECISION)
        for word in ("del", "della", "causa", "ricorso", "sentenza"):
            assert re.search(rf"(?<![\p{{L}}]){word}(?![\p{{L}}])", out, re.I), \
                f"{word!r} disappeared from the text"

    def test_section_headings_are_not_people(self):
        out, _ = anonymize(DECISION)
        assert "FATTI DI CAUSA" in out

    def test_a_name_capture_stops_at_the_next_section_heading(self):
        # Patterns that tolerate a line break inside a name ran into the heading below:
        # "Gallusi Sandro\nFATTI DI CAUSA" became the person "Gallusi Sandro FATTI DI",
        # and the heading vanished from the output.
        text = ("BENATTI ROSSELLA, difesa dall'avv. Gallusi Sandro\n"
                "FATTI DI CAUSA\nLa Benatti impugnava la cartella.")
        out, rep = anonymize(text)
        assert "FATTI DI CAUSA" in out
        assert "Gallusi" not in out
        assert all("fatti" not in k for k in rep.mapping)

    def test_an_institution_fragment_is_not_a_person(self):
        text = ("sul ricorso proposto da\n"
                "MINISTERO DELL'ECONOMIA E DELLE FINANZE\n -ricorrente-\n")
        out, rep = anonymize(text)
        assert "DELLE FINANZE" in out
        assert rep.entities == 0

    def test_tail_of_an_institution_in_a_party_block_is_not_a_person(self):
        text = (
            "sul ricorso proposto da\nBANCA NAZIONALE DEL LAVORO\n"
            "-ricorrente-\n"
        )
        out, rep = anonymize(text)
        assert "BANCA NAZIONALE DEL LAVORO" in out
        assert rep.entities == 0

    def test_tail_of_a_public_body_in_a_party_block_is_not_a_person(self):
        text = (
            "sul ricorso proposto da\n"
            "ISTITUTO NAZIONALE DELLA PREVIDENZA SOCIALE\n-ricorrente-\n"
        )
        out, rep = anonymize(text)
        assert "ISTITUTO NAZIONALE DELLA PREVIDENZA SOCIALE" in out
        assert rep.entities == 0


class TestCompanies:
    def test_legal_form_capitalization(self):
        for suffix in ("S.r.l.", "s.r.l.", "S.R.L.", "SRL", "srl", "S.P.A.", "spa"):
            text = f"Alfa Costruzioni {suffix} ricorre."
            assert anonymize(text, Config(companies=True))[0] == "Società_1 ricorre."
            assert anonymize(text, Config(companies=False))[0] == text

    def test_company_introducers_are_preserved(self):
        text = "Il ricorso della Alfa Costruzioni S.r.l. e di Alfa Costruzioni S.r.l."
        out, _ = anonymize(text, Config(companies=True))
        assert out == "Il ricorso della Società_1 e di Società_1"

    def test_institution_guard_also_applies_after_introducers(self):
        for name in ("Equitalia Nord", "Poste Italiane", "Agenzia delle Entrate"):
            text = f"Il ricorso della {name} S.p.A. è respinto."
            assert anonymize(text, Config(companies=True))[0] == text

    def test_article_and_legal_form_alone_are_not_a_company_name(self):
        text = "La S.p.A. ricorre."
        assert anonymize(text, Config(companies=True))[0] == text

    def test_institution_guard_after_societa(self):
        text = "Ricorre la Società Poste Italiane S.p.A., già Ente Poste Italiane."
        assert anonymize(text, Config(companies=True))[0] == text

    def test_public_entity_aliases_and_wrapped_names(self):
        for name in ("ROMA CAPITALE", "AVVOCATURA\nGENERALE DELLO STATO"):
            text = f"sul ricorso proposto da\n{name}\n-ricorrente-\n{name} insiste."
            for companies in (False, "person_named", True):
                assert anonymize(text, Config(companies=companies))[0] == text

    def test_companies_are_opt_in(self):
        text = "La Alfa Costruzioni S.r.l. impugna la cartella."
        assert "Alfa Costruzioni" in anonymize(text)[0]
        assert "Alfa Costruzioni" not in anonymize(text, Config(companies=True))[0]

    def test_public_bodies_are_not_companies(self):
        text = "AGENZIA DELLE ENTRATE S.p.A. non esiste ma il prefisso conta."
        out, _ = anonymize(text, Config(companies=True))
        assert "AGENZIA DELLE ENTRATE" in out

    def test_person_named_mode_replaces_strong_family_signals(self):
        companies = (
            "F.lli Filippi s.r.l.",
            "Mazzetti e Franchi s.r.l.",
            "Sicil Tiller dei Fratelli Palminteri S.r.l.",
            "Calcestruzzi Fratelli Vignali S.r.l.",
            "Traini & Torresi S.p.A.",
            "Molino & Molino S.r.l.",
            "Ottonello & Mosca S.r.l.",
        )
        for company in companies:
            out, _ = anonymize(
                f"La {company} ricorre.",
                Config(companies="person_named"),
            )
            assert out == "La Società_1 ricorre.", company

    def test_person_named_company_wins_over_a_shared_person_alias(self):
        text = (
            "contro\nSicil Tiller dei Fratelli Palminteri s.n.c., "
            "in persona del legale rappresentante, ed il socio Samuele Palminteri."
        )
        out, report = anonymize(text, Config(companies="person_named"))
        assert out.startswith("contro\nSocietà_1,")
        assert any(
            decision.kind == "ORGANIZATION"
            and decision.text == "Sicil Tiller dei Fratelli Palminteri s.n.c."
            for decision in report.decisions
        )

    def test_person_named_mode_keeps_ambiguous_brand_names(self):
        companies = (
            "Labium spa",
            "Etofi srl",
            "Ambiente & Sviluppo S.r.l.",
            "Fish & Meats S.r.l.",
            "Vodafone e Comdata S.r.l.",
            "Fratelli S.p.A.",
            "Eredi s.a.s.",
        )
        for company in companies:
            text = f"La {company} ricorre."
            assert anonymize(text, Config(companies="person_named"))[0] == text
            assert anonymize(text, Config(companies=True))[0] == "La Società_1 ricorre."

    def test_unknown_company_mode_is_rejected(self):
        with pytest.raises(ValueError, match="companies must be"):
            Config(companies="all")


class TestReport:
    def test_report_counts(self):
        _, rep = anonymize(DECISION)
        assert rep.entities >= 3
        assert rep.replacements >= rep.entities
        assert len(rep.replacement_spans) == rep.replacements
        assert 0.0 <= rep.risk <= 1.0

    def test_report_exposes_original_offsets_of_actual_replacements(self):
        text = "Il sig. Mario Rossi, C.F. RSSMRA80A01H501U, ricorre."
        _, rep = anonymize(text)
        assert rep.replacement_spans == [(8, 19), (26, 42)]
        assert [text[start:end] for start, end in rep.replacement_spans] == [
            "Mario Rossi",
            "RSSMRA80A01H501U",
        ]

    def test_risk_flags_a_long_document_with_no_detections(self):
        _, rep = anonymize("parola " * 400)
        assert rep.risk >= 0.5

    def test_risk_does_not_flag_text_already_anonymized_at_source(self):
        # The older Cassazione feed ships initials and "(Omissis)". Finding nothing
        # there is correct, and flagging it buried the real cases in the triage queue.
        text = ("il Tribunale ha riconosciuto B.S.M. e Bu.Fr. responsabili; "
                "V.G. conveniva l'Ospedale in data (Omissis). " + "parola " * 400)
        _, rep = anonymize(text)
        assert rep.risk == 0.0


class TestIdempotence:
    """Running twice must be a no-op: batches get resumed and re-run after rule changes."""

    def test_running_twice_changes_nothing_more(self):
        once, _ = anonymize(DECISION)
        twice, rep = anonymize(once)
        assert twice == once, "a second pass rewrote already-pseudonymized text"

    def test_output_tags_are_never_detected_as_names(self):
        text = "rappresentato e difeso dagli Nominativo_1 (CF_2), Nominativo_2 (CF_3)"
        out, rep = anonymize(text)
        assert out == text
        assert rep.entities == 0

    def test_underscore_runs_survive(self):
        # Scan noise like "Rep. _____" was collapsed to "Rep. _" by the emphasis pass.
        text = "ha pronunciato la seguente Rep. _____ \nORDINANZA"
        assert "_____" in anonymize(text)[0]


class TestSharedFirstNames:
    def test_a_party_sharing_a_first_name_with_a_judge_is_still_removed(self):
        # "LUCA" from the Sostituto Procuratore used to veto the defendant outright.
        text = ("Presidente: CIAMPI FRANCESCO MARIA\n"
                "sul ricorso proposto da: \n"
                "APOLLONI GIAN LUCA nato a ROMA il 12/03/1974 \n"
                "udito il Sostituto Procuratore LUCA TAMPIERI\n"
                "RITENUTO IN FATTO\n"
                "la pena inflitta ad Apolloni Gian Luca è rideterminata.\n")
        out, _ = anonymize(text)
        assert "LUCA TAMPIERI" in out, "the prosecutor must stay in clear"
        assert "APOLLONI" not in out and "Apolloni" not in out


class TestQueryProfile:
    def test_short_query(self):
        q = "La Alfa S.r.l., P.IVA 01234567890, con l'avv. Laura Bianchi, ricorre"
        out, _ = anonymize(q, Config(profile="query", companies=True))
        assert "Laura Bianchi" not in out
        assert "01234567890" not in out


class TestSanitize:
    def test_angle_bracket_quotations_survive(self):
        from pseudonimizzatore_legale.text import sanitize
        text = "Il giudice osserva: <<la sentenza è corretta>> e prosegue.\n\nSecondo paragrafo."
        assert sanitize(text) == text

    def test_an_unclosed_quotation_does_not_swallow_paragraphs(self):
        from pseudonimizzatore_legale.text import sanitize
        text = "<<a tal fine il ricorrente deduce\n\nche l'atto è illegittimo>> e conclude."
        assert sanitize(text) == text

    def test_real_markup_is_still_flattened(self):
        from pseudonimizzatore_legale.text import sanitize
        assert sanitize("<b>Ma</b>rio <i>Rossi</i><br/>") == "Mario Rossi"


class TestAdministrativeParties:
    """Party blocks of first-instance administrative decisions. Every name is invented."""

    HEAD = ("sul ricorso numero di registro generale 100 del 2024, proposto da Giulia Balestri, "
            "Lucia Surpo, Maurita Perfetti e Anna Vezzi, rappresentate e difese dall'avvocato "
            "Carla Fenzi;\n\ncontro\n\nMinistero dell'Istruzione e del Merito;\n\n"
            "nei confronti\n\nDavide Fiorenzi, Pietro Salvo Rinaldi, non costituiti in "
            "giudizio;\n\nper l'annullamento\n\ndel provvedimento n. 12/2024.")

    def test_every_co_applicant_is_removed(self):
        out, report = anonymize(self.HEAD)
        for name in ("Giulia Balestri", "Lucia Surpo", "Maurita Perfetti", "Anna Vezzi"):
            assert name not in out
        applicants = sorted(t for t in report.mapping.values() if t.startswith("Ricorrente"))
        assert applicants == ["Ricorrente_1", "Ricorrente_2", "Ricorrente_3", "Ricorrente_4"]

    def test_counter_interested_parties_are_the_other_side(self):
        out, report = anonymize(self.HEAD)
        assert "Fiorenzi" not in out and "Rinaldi" not in out
        assert report.mapping["Davide Fiorenzi"].startswith("Resistente")

    def test_public_bodies_in_the_same_blocks_stay(self):
        out, _ = anonymize(self.HEAD)
        assert "Ministero dell'Istruzione e del Merito" in out and "n. 12/2024" in out

    def test_institutions_listed_as_parties_stay(self):
        text = "proposto da Regione Marche, Comune di Pesaro e Provincia di Ancona, rappresentati"
        assert anonymize(text)[0] == text

    def test_health_authority_is_not_a_person(self):
        text = ("nei confronti di Asur Marche Area Vasta n. 1, non costituita;\n\n"
                "La Regione Marche e l'Asur Marche resistono.")
        assert anonymize(text)[0] == text


class TestJudicialRanks:
    """TAR benches and the ways older decisions title a judge. Every name is invented."""

    def test_referendario_estensore_is_kept_everywhere(self):
        text = ("Relatore nella camera di consiglio del giorno 4 giugno 2024 la dott.ssa "
                "Anna Bianchi e uditi per le parti i difensori.\n\n"
                "Così deciso in Roma con l'intervento dei magistrati:\n\n"
                "Mario Rossi, Presidente\n\nAnna Bianchi, Referendario, Estensore")
        out, report = anonymize(text)
        assert out.count("Anna Bianchi") == 2 and "Anna Bianchi" not in report.mapping

    def test_a_title_alone_does_not_turn_a_judge_into_a_party(self):
        text = "Presidente: ROSSI MARIO\n\nIl dott. Mario Rossi dà lettura del dispositivo."
        out, report = anonymize(text)
        assert "Mario Rossi" in out and not report.mapping

    def test_a_title_still_marks_a_private_person(self):
        out, _ = anonymize("Presidente: ROSSI MARIO\n\nÈ comparso il dott. Luca Verdi.")
        assert "Luca Verdi" not in out

    def test_consigliere_avv_is_the_judge(self):
        text = ("Relatore alla camera di consiglio del 20 giugno 2006 il consigliere avv. "
                "Liana Tacchi; udito l'avv. Carla Fenzi per il ricorrente.")
        out, _ = anonymize(text)
        assert "Liana Tacchi" in out and "Carla Fenzi" not in out
