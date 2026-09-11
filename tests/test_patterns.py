"""One positive and one negative case per pattern.

The negative cases are not decoration: every one corresponds to a defect that actually
occurred on real documents, and a pattern that loses its negative test silently
re-opens that defect.
"""
import regex as re

from pseudonimizzatore_legale import patterns as P
from pseudonimizzatore_legale.seeds import SeedSet


class TestCaseSensitivity:
    """Capitalisation must stay case-sensitive.

    Making a whole pattern case-insensitive voids its `[A-Z]` constraints, and phrases
    like "tra questo tale soggetto, residente" start being captured as people.
    """

    def test_biografico_requires_a_capital(self):
        assert P.BIOGRAFICO.search("Mario Rossi, nato a Salerno")
        assert not P.BIOGRAFICO.search("il contratto tra questo tale soggetto, residente")

    def test_allcaps_name_does_not_match_lowercase(self):
        assert P.ALLCAPS_NAME.search("BENATTI ROSSELLA")
        assert not P.ALLCAPS_NAME.search("benatti rossella")

    def test_allcaps_name_cannot_start_with_a_two_letter_token(self):
        # "DI" starting a candidate produced the person "DI Chiti Paolo".
        m = P.ALLCAPS_NAME.search("DI CHITI PAOLO")
        assert m and not m.group(1).startswith("DI ")


class TestStructured:
    def test_codice_fiscale(self):
        assert P.CODICE_FISCALE.search("C.F. RSSMRA80A01H501U")
        # invalid month letter Q and day 99 must not match
        assert not P.CODICE_FISCALE.search("RSSMRA80Q99H501U")

    def test_partita_iva_requires_its_cue(self):
        assert P.PARTITA_IVA.search("P.IVA 01234567890").group(1) == "01234567890"
        # a bare 11-digit run is usually a protocol number
        assert not P.PARTITA_IVA.search("prot. 01234567890")

    def test_pec_before_email(self):
        assert P.PEC.search("mario@pec.avvocati.it")
        assert not P.PEC.search("mario@studio.it")

    def test_email(self):
        assert P.EMAIL.search("sandro.gallusi@ordineavvocati.it")
        assert not P.EMAIL.search("art. 36-ter del DPR 600/1973")

    def test_telefono_requires_its_cue(self):
        assert P.TELEFONO.search("tel. 06 1234567")
        # a case number must not read as a phone number
        assert not P.TELEFONO.search("n. 24009-2019 R.G.")

    def test_iban(self):
        assert P.IBAN.search("IT60X0542811101000000123456")
        assert not P.IBAN.search("IT60X05428111")

    def test_data_nascita_not_procedural_date(self):
        assert P.DATA_NASCITA.search("nato il 23 luglio 1968")
        assert not P.DATA_NASCITA.search("depositata il 24 febbraio 2023")


class TestJudicialEvidence:
    def test_judge_header_anchor_works_off_the_last_line(self):
        # A scoped (?m:…) left `$` meaning end-of-string, so this only matched when the
        # judge line happened to be the final line of the file.
        text = ("Civile Ord. Sez. 5 Num. 8903 Anno 2024\n"
                "Presidente: FEDERICI FRANCESCO\n"
                "Relatore: LUCIOTTI LUCIO\n"
                "Data pubblicazione: 04/04/2024\n")
        found = {m.group(1) for m in P.JUDGE_ANCHORS[0].finditer(text)}
        assert "FEDERICI FRANCESCO" in found
        assert "LUCIOTTI LUCIO" in found

    def test_consigliere_anchor_allows_a_second_role_word(self):
        text = "del 18/01/2024 dal Consigliere relatore dott. Lucio Luciotti;"
        assert any(p.search(text) for p in P.JUDGE_ANCHORS)

    def test_corte_conti_ref_judge_across_line_break(self):
        text = ("nella persona del Giudice unico\n"
                "Ref. Mastrogiacomo\n"
                " D'Oro\n"
                "ha pronunciato la seguente SENTENZA")
        found = {m.group(1) for pattern in P.JUDGE_ANCHORS
                 for m in pattern.finditer(text)}
        assert "Mastrogiacomo\n D'Oro" in found

    def test_institution_head_matches_prefixes(self):
        # Only a *leading* \b: a trailing one silently disabled every prefix
        # alternative, so "universit" stopped matching "UNIVERSITARIA" and the tail of
        # "AZIENDA OSPEDALIERA UNIVERSITARIA FEDERICO II" became a person.
        assert P.INSTITUTION_HEAD.search("AGENZIA DELLE ENTRATE")
        assert P.INSTITUTION_HEAD.search("Ag. Entrate Direzione Provinciale")
        assert P.INSTITUTION_HEAD.search("I.N.P.S.")
        assert P.INSTITUTION_HEAD.search("AZIENDA OSPEDALIERA UNIVERSITARIA")
        assert P.INSTITUTION_HEAD.search("DIREZIONE PROVINCIALE")
        assert not P.INSTITUTION_HEAD.search("Ferruccio Malaspina")

    def test_case_number(self):
        assert P.CASE_NUMBER.search("n. 274/2023")
        assert P.CASE_NUMBER.search("R.G. 17382/2023")
        assert not P.CASE_NUMBER.search("nato il 12/03/1974")


class TestSeeds:
    def test_a_short_ner_fragment_cannot_become_a_person(self):
        seeds = SeedSet(min_token_len=4)
        assert seeds.add("P", "Nominativo", allow_single=True,
                         require_distinctive=False) is None

    def test_counsel_across_a_line_break(self):
        text = "presso lo studio dell'avvocato GIORDANO \nVITTORIO (GRDVTR78P11C129P)"
        m = P.COUNSEL.search(text)
        assert m and "GIORDANO" in m.group(1) and "VITTORIO" in m.group(1)

    def test_cf_adjacency(self):
        m = P.CF_ADIACENTE.search("MEROLLE ANDREA (MRLNDR83H23D810S)")
        assert m and m.group(1) == "MEROLLE ANDREA"

    def test_company_suffix_matches_upper_case(self):
        # A case-sensitive test let "CANTINE SANREMESI SNC" through as a person.
        assert P.COMPANY_SUFFIX_RE.search("CANTINE SANREMESI SNC")
        assert P.COMPANY_SUFFIX_RE.search("Alfa Costruzioni S.r.l.")

    def test_company_suffix_does_not_match_inside_a_surname(self):
        # Unanchored, "S.p.A." matched the "Spa" inside "Spadaccini", so every surname
        # containing spa/sas/srl/snc was refused as a company and never pseudonymized.
        for surname in ("Spadaccini", "Spataro", "Spagnuolo", "Sassi", "Sasso",
                        "Snchez", "Srlvatore"):
            assert not P.COMPANY_SUFFIX_RE.search(surname), surname

    def test_person_named_company_family_marker(self):
        for name in (
            "F.lli Filippi",
            "F.LLI FUMAGALLI",
            "F LLI DE CECCO",
            "Fratelli Vignali",
            "Eredi Rossi",
        ):
            assert P.PERSON_NAMED_COMPANY_FAMILY.search(name), name
        for name in ("Filippi", "Fratellanza", "Eredit S.r.l."):
            assert not P.PERSON_NAMED_COMPANY_FAMILY.search(name), name

    def test_person_named_company_bridge_rejects_prose(self):
        assert P.PERSON_NAMED_COMPANY_BRIDGE.fullmatch(
            " DE CECCO DI FILIPPO FARA S. "
        )
        assert not P.PERSON_NAMED_COMPANY_BRIDGE.fullmatch(
            " Rossi hanno impugnato contro "
        )

    def test_person_named_company_pair_and_surname_shape(self):
        pair = P.PERSON_NAMED_COMPANY_PAIR.fullmatch("Mazzetti e Franchi")
        assert pair and all(
            P.PERSON_NAMED_COMPANY_SURNAME_END.search(part)
            for part in pair.groups()
        )
        assert not P.PERSON_NAMED_COMPANY_PAIR.fullmatch(
            "Mazzetti e Franchi e Rossi"
        )
        assert not P.PERSON_NAMED_COMPANY_SURNAME_END.search("Labium")

    def test_counsel_list(self):
        m = P.COUNSEL_LIST.search(
            "difesi dagli avvocati Anton Lana, Mario Melillo e Valentina Rao,")
        assert m
        parts = P.COUNSEL_LIST_SEP.split(m.group(1))
        assert parts == ["Anton Lana", "Mario Melillo", "Valentina Rao"]

    def test_street_head_is_not_a_person(self):
        # "VIA CESARE BECCARIA" and "PIAZZA BENEDETTO CAIROLI" were seeded as parties.
        assert P.STREET_HEAD.match("VIA CESARE BECCARIA")
        assert P.STREET_HEAD.match("Piazza Benedetto Cairoli")
        assert not P.STREET_HEAD.match("Ferruccio Malaspina")

    def test_qualifica(self):
        m = P.QUALIFICA.search("così come all'altro socio TAGLIAFERRI NICODEMO)")
        assert m and m.group(1) == "TAGLIAFERRI NICODEMO"
        assert not P.QUALIFICA.search("Sostituto Procuratore LUCA TAMPIERI")

    def test_advocate_general_is_a_judicial_role(self):
        text = "CONCLUSIONI DELL'AVVOCATO GENERALE\nMANUEL CAMPOS SANCHEZ\npresentate"
        assert any(p.search(text) for p in P.JUDGE_ANCHORS)

    def test_fragment_head_words(self):
        # Plural/prepositional connectors open an institution fragment, never a name…
        assert "delle" in P.FRAGMENT_HEAD
        # …but the singular forms open real Italian surnames and must stay allowed:
        # "Della Maggiora", "De Luca", "Lo Giudice", "Dal Lago".
        for particle in ("della", "de", "di", "dal", "lo", "la"):
            assert particle not in P.FRAGMENT_HEAD, particle


class TestJudgeProtectionAtScale:
    """Found by widening the fixture corpus past Cassazione to five more archives —
    every case here is a real judge that was being pseudonymized in breach of the
    keep-judges guideline before the fix next to it landed.
    """

    def test_biografico_cue_does_not_glue_onto_a_surname_ending_in_the_cue_word(self):
        # A zero-width gap let "nat[oa]\b" match as the literal tail of a surname: with
        # no separator required, "Ornella Trevisanato" (a judge) was read as the name
        # "Ornella Trevisa" followed by its own biographic cue "nato", pseudonymizing
        # four-fifths of a judge's surname. "Trevisanato" itself must not be captured.
        assert not P.BIOGRAFICO.search("Ornella Trevisanato, Consigliere")
        # the genuine case must still fire, with a real separator before the cue
        m = P.BIOGRAFICO.search("Mario Rossi, nato a Salerno")
        assert m and m.group(1) == "Mario Rossi"

    def test_judge_after_comma_no_line_start_required(self):
        # "Letta la requisitoria del dott. X, Sostituto Procuratore generale" — the
        # role follows the name after a comma, mid-sentence. The pre-existing anchor
        # only recognised this shape at the start of a line.
        text = ("Letta la requisitoria del dott. Augusto Corbellini, Sostituto "
                "Procuratore generale della Repubblica")
        assert any(m.group(1) == "Augusto Corbellini"
                  for p in P.JUDGE_ANCHORS for m in [p.search(text)] if m)

    def test_judge_role_word_at_a_distance_with_title(self):
        # "Il Procuratore generale, Dott. X, nella requisitoria" — role and title are
        # both present but separated by a comma, with no line start involved.
        text = "Il Procuratore generale, Dott. Nicodemo Tagliaferri, nella requisitoria"
        assert any(m.group(1) == "Nicodemo Tagliaferri"
                  for p in P.JUDGE_ANCHORS for m in [p.search(text)] if m)

    def test_judge_list_cue_matches_common_phrasings(self):
        for phrase in ("composta dai magistrati", "composta dai seguenti magistrati:",
                      "composta dai sigg.ri magistrati:", "composta dal magistrato:"):
            assert P.JUDGE_LIST_CUE.search(phrase), phrase

    def test_judge_list_end_stops_at_the_case_narrative(self):
        # Without an end marker, a short bench list on a document with little text
        # between the cue and the party block let the window reach past the panel
        # into "SENTENZA nel giudizio … nei confronti di X" and protect the party.
        for phrase in ("ha pronunciato la seguente", "SENTENZA", "nel giudizio",
                      "nei confronti di"):
            assert P.JUDGE_LIST_END.search(phrase), phrase

    def test_judicial_role_excludes_bare_magistrato(self):
        # A bare "magistrato/i" (no "composta da…" in front, which JUDGE_LIST_CUE
        # requires separately) is too common outside a bench-composition context — an
        # HTML export's metadata trailer carried it as a literal Windows folder name
        # ("U:\DocumentiGA\Magistrati\769…"), which pulled a nearby party into the
        # role-word-then-title anchors.
        assert not re.search(P.JUDICIAL_ROLE, "Magistrati", re.I)
