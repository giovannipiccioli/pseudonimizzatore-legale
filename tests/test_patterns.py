"""One positive and one negative case per pattern.

The negative cases are not decoration: every one corresponds to a defect that actually
occurred on real documents, and a pattern that loses its negative test silently
re-opens that defect.
"""
import regex as re

from pseudonimizzatore_legale import patterns as P
from pseudonimizzatore_legale import protect, seeds as seeds_mod
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

    def test_codice_fiscale_loose_forms(self):
        def found(text):
            return [m.group() for m in P.CODICE_FISCALE.finditer(text)
                    if P.codice_fiscale_ok(m.group())]
        # omocodia: digits replaced by L M N P Q R S T U V, from the right
        assert found("c.f. RSSMRA80A01H50MV") == ["RSSMRA80A01H50MV"]
        # one character at a time, and lower case: accepted with a valid check letter
        assert found("codice fiscale R S S M R A 8 0 A 0 1 H 5 0 1 U)") == [
            "R S S M R A 8 0 A 0 1 H 5 0 1 U"]
        assert found("c.f. rssmra80a01h501u.") == ["rssmra80a01h501u"]
        # …and refused without one, so a looser pattern costs no precision
        assert found("c.f. rssmra80a01h501x, R S S M R A 8 0 A 0 1 H 5 0 1 X") == []
        # the usual upper-case form keeps working with a mistyped check letter, as before
        assert found("C.F. RSSMRA80A01H501X") == ["RSSMRA80A01H501X"]
        assert found("RSSMRA80A99H501U") == []          # day 99 does not exist

    def test_iban(self):
        assert P.IBAN.search("IT60X0542811101000000123456")
        assert not P.IBAN.search("IT60X05428111")
        # The match must not take the space after it, or "Iban_1e" glues to the next word.
        assert P.IBAN.search("IT60X0542811101000000123456 e").group() == (
            "IT60X0542811101000000123456")

    def test_foreign_iban_needs_its_mod_97_check(self):
        def found(text):
            return [m.group() for m in P.IBAN.finditer(text) if P.iban_ok(m.group())]
        assert found("IBAN SM86U0322509800000000270100 e DE89 3704 0044 0532 0130 00.") == [
            "SM86U0322509800000000270100", "DE89 3704 0044 0532 0130 00"]
        # one digit off, and an act number of the same shape
        assert found("IBAN DE89370400440532013001") == []
        assert found("avviso n. TD7030604428 IRAP 2013") == []

    def test_electronic_identity_card(self):
        for text in ("carta d'identità n. CA12345AB rilasciata",
                     "carta d'identità elettronica CA12345AB", "CIE n. CA12345AB"):
            assert P.NUMERO_DOCUMENTO.search(text).group(1) == "CA12345AB", text
        assert P.NUMERO_DOCUMENTO.search("passaporto n. YA1234567").group(1) == "YA1234567"
        # the cue is still required
        assert not P.NUMERO_DOCUMENTO.search("protocollo CA12345AB")

    def test_residential_address_without_cap(self):
        for text, street in (
                ("residente in Roma, Via Cola di Rienzo 12, ricorre", "Via Cola di Rienzo 12"),
                ("residente a Roma in Via Cola di Rienzo n. 12", "Via Cola di Rienzo n. 12"),
                ("residente in Pratovecchio (AR), loc. Casalino 4", "loc. Casalino 4"),
                ("elettivamente domiciliato presso lo studio dell'avv. Mario Malaspina, "
                 "Via Po 3, che lo difende", "Via Po 3"),
                ("domiciliato in Ancona, al Corso Garibaldi, n. 124;", "Corso Garibaldi, n. 124"),
                ("residente in Via Ippolito Nievo n. 47, 44121 Ferrara",
                 "Via Ippolito Nievo n. 47, 44121")):
            assert P.INDIRIZZO_RESIDENZA.search(text).group(1) == street, text

    def test_residential_address_needs_a_personal_cue_and_a_street(self):
        for text in (
                "La Alfa S.r.l., con sede in Roma, Via Cola di Rienzo 12",
                "residente in Roma e socio della Alfa s.r.l., con sede in Via Po 3",
                "domiciliata ex lege in Roma, via dei Portoghesi 12",
                "domiciliato in Italia, in via preliminare eccepisce il ricorso n. 12",
                "residente nel Comune, nel corso di 12 mesi",
                "residente in Roma, via Garibaldi. Con ricorso n. 1234/2020 impugna"):
            assert not P.INDIRIZZO_RESIDENZA.search(text), text

    def test_birthplace_is_read_only_in_its_slot(self):
        assert P.LUOGO_BIOGRAFICO.search("nato a Stia il 03/04/1960").group(1) == "Stia il"
        assert P.LUOGO_BIOGRAFICO.search("nato il 6.5.1980 a Madaripur").group(1) == (
            "Madaripur")
        assert P.LUOGO_BIOGRAFICO.search("e residente a Pratovecchio,").group(1) == (
            "Pratovecchio")
        for text in ("il Tribunale di Stia", "nato a seguito del ricorso",
                     "domiciliato in Roma"):
            assert not P.LUOGO_BIOGRAFICO.search(text), text

    def test_comuni_are_istat_names_old_and_new(self):
        comuni = seeds_mod.comuni()
        # Stia and Pratovecchio merged in 2014; a birthplace still names the old comune
        for name in ("Stia", "Pratovecchio", "Pratovecchio Stia", "Bozen", "Reggio Emilia"):
            assert seeds_mod.place_key(name) in comuni, name
        assert seeds_mod.place_key("FORLI'") == seeds_mod.place_key("Forlì")
        for name in ("Romania", "Italia", "Via Roma"):
            assert seeds_mod.place_key(name) not in comuni, name

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

    def test_sole_trader_and_law_firm_are_people(self):
        for text, name in (("La ditta individuale di HU XIAOMING, con", "HU XIAOMING"),
                           ("l'impresa individuale Ferruccio Malaspina", "Ferruccio Malaspina"),
                           ("(studio legale Mirandolina Zangheratti);", "Mirandolina Zangheratti")):
            assert P.QUALIFICA.search(text).group(1) == name, text
        # a firm named by one surname has no full name to read
        assert not P.QUALIFICA.search("presso lo studio legale Rossi e Associati")

    def test_biographic_partita_iva(self):
        m = P.BIOGRAFICO.search("DI BENEDETTO OSVALDO - P.IVA 02956140374")
        assert m and m.group(1) == "DI BENEDETTO OSVALDO"
        # "eccepiva" ends in the letters of the cue, and is not one
        assert not P.BIOGRAFICO.search("Mario Rossi eccepiva la nullità")

    def test_surname_alone_after_a_courtesy_title(self):
        assert P.TITOLO_SOLO.search("Il sig. Malaspina ha presentato").group(1) == "Malaspina"
        assert P.TITOLO_SOLO.search("la sig.ra Malaspina.").group(1) == "Malaspina"
        # a full name is TITOLO's; "dott." is a judge's title too and stays out
        assert not P.TITOLO_SOLO.search("il sig. Ferruccio Malaspina")
        assert not P.TITOLO_SOLO.search("il dott. Malaspina")

    def test_surname_alone_after_a_party_role(self):
        assert P.PARTY_ROLE_SOLO.search("Il ricorrente Malaspina insiste").group(1) == (
            "Malaspina")
        for text in ("il ricorrente Ferruccio Malaspina",   # a full name is PARTY_ROLE's
                     "il ricorrente Prof. Rossi",           # a title, not a surname
                     "inoltrata dal ricorrente Prot. n. 1234"):  # an abbreviation
            assert not P.PARTY_ROLE_SOLO.search(text), text

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


class TestAdministrativeLayouts:
    """Shapes of first-instance administrative decisions. Every name is invented."""

    def test_party_list_captures_every_name(self):
        m = P.PARTY_LIST.search("proposto da Giulia Balestri, Lucia Surpo, Maurita Perfetti "
                                "e Anna Vezzi, rappresentate e difese")
        assert P.COUNSEL_LIST_SEP.split(m.group(1)) == [
            "Giulia Balestri", "Lucia Surpo", "Maurita Perfetti", "Anna Vezzi"]

    def test_party_list_accepts_semicolons(self):
        m = P.PARTY_LIST.search("nei confronti di\n\nDavide Fiorenzi; Teodoro Vezzani;\n\nper")
        assert P.COUNSEL_LIST_SEP.split(m.group(1)) == ["Davide Fiorenzi", "Teodoro Vezzani"]

    def test_party_list_stops_at_the_first_non_name(self):
        m = P.PARTY_LIST.search("proposto da Giulia Balestri, rappresentata dall'avv. X")
        assert m.group(1) == "Giulia Balestri"

    def test_standalone_nei_confronti_label_is_a_cue(self):
        assert P.NEI_CONFRONTI.search(
            "nei confronti\n\nDavide Fiorenzi, non costituito").group(1) == "Davide Fiorenzi"
        assert P.NEI_CONFRONTI.search(
            "nei confronti di Davide Fiorenzi").group(1) == "Davide Fiorenzi"

    def test_nei_confronti_in_prose_is_not_a_person(self):
        assert P.NEI_CONFRONTI.search("ha agito nei confronti della Regione Marche") is None
        assert P.NEI_CONFRONTI.search("nei confronti\n\ndell'amministrazione") is None

    def test_referendario_is_a_judicial_role(self):
        for line in ("Anna Bianchi, Referendario, Estensore", "Anna Bianchi, Primo Referendario"):
            assert "Anna Bianchi" in protect.collect(line).names

    def test_consigliere_avv_is_a_judge_not_counsel(self):
        text = "il consigliere avv. Liana Tacchi"
        assert P.COUNSEL.search(text) is None
        assert "Liana Tacchi" in protect.collect(text).names
        assert P.COUNSEL.search("difeso dall'avv. Liana Tacchi").group(1) == "Liana Tacchi"

    def test_health_authority_acronyms_are_institutions(self):
        for name in ("Asur Marche Area Vasta", "ASP di Catania", "Ausl Romagna", "Ulss Dolomiti"):
            assert P.INSTITUTION_HEAD.search(name)
        assert not P.INSTITUTION_HEAD.search("Mario Aspesi")

    def test_statutory_domicile_is_not_biographic(self):
        assert P.BIOGRAFICO.search(
            "Stato di Reggio Calabria, domiciliata ex lege in Reggio Calabria") is None
        assert P.BIOGRAFICO.search("Mario Rossi, domiciliato in Roma").group(1) == "Mario Rossi"
