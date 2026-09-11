"""Regex inventory for Italian legal documents.

Two conventions hold throughout, and both exist because breaking them caused real
bugs that took a corpus to find:

**Capitalisation is load-bearing, so it is case-sensitive.** Never make a whole
pattern case-insensitive to be forgiving: `[A-Z]` under `re.I` matches lowercase too,
which silently voids the "starts with a capital" constraint that separates a name from
a sentence. Wrap only the *cue* words in a scoped `(?i:…)` and leave the name classes
alone — that is why patterns here look like ``(?i:avv\\.)\\s+({FULL_NAME})`` rather
than carrying a global flag.

**Identifiers need their cue word.** A bare 11-digit run is a protocol number as often
as a P.IVA; a bare phone-shaped run is a case number. Anchoring on the cue costs a
little recall and buys a lot of precision, which is the right trade when a false
positive deletes real text.

Every pattern has at least one positive and one negative case in tests/test_patterns.py.
The negative cases are the important half.
"""
import regex as re

# ── building blocks ──────────────────────────────────────────────────────────

#: A capitalised name token: "Rossi", "D'Angelo", "Bellè", "MAROZZO", "AGRO'".
#: The optional trailing apostrophe is not punctuation — in ALL-CAPS Italian a final
#: accented vowel is conventionally typed as one ("AGRO'" = Agrò, "SALME'" = Salmè),
#: and requiring a letter last dropped those surnames outright. They are 3.9% of the
#: names in Cassazione header fields, so the bench went unprotected in all of them.
NAME_TOKEN = r"[\p{Lu}][\p{L}'’]*[\p{L}]['’]?"
#: Spaces/tabs but *not* a line break — keeps a name from spanning a paragraph.
SEP = r"[^\S\r\n]+"
#: Whitespace including a single line break — court text wraps names mid-line.
SEP_NL = r"[^\S\r\n]*\n?[^\S\r\n]*"
#: 2–4 capitalised tokens.
FULL_NAME = rf"{NAME_TOKEN}(?:{SEP}{NAME_TOKEN}){{1,3}}"
#: Same, tolerating one line break between tokens.
FULL_NAME_NL = rf"{NAME_TOKEN}(?:{SEP_NL}{NAME_TOKEN}){{1,3}}"

MONTHS = (r"gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|"
          r"ottobre|novembre|dicembre")

#: How counsel are introduced. `avv.to` and `avv.ti` are as common in Italian practice
#: as `avv.` itself, and matching only the latter loses a whole class of documents.
#: Not after a judicial role word: older decisions title the reporting judge "il
#: consigliere avv. X", and that X sits on the bench.
COUNSEL_CUE = (r"(?<!(?i:consiglier[ea]|referendari[oa]|relatore|presidente|giudice)\s+)"
               r"(?i:avvocat[oi]|avv\.?ti|avv\.?to|avv\.)")

COMPANY_SUFFIX = (r"S\.?\s?p\.?\s?A\.?|S\.?\s?r\.?\s?l\.?(?:\s?s\.?)?|S\.?\s?a\.?\s?s\.?|"
                  r"S\.?\s?n\.?\s?c\.?|S\.?c\.?a\.?r\.?l\.?|S\.?c\.?p\.?A\.?|"
                  r"S\.?S\.?D\.?|Soc\.\s?Coop\.|ONLUS|S\.?A\.?P\.?A\.?")

#: The same alternation, anchored. Always use this to ask "does this string carry a
#: legal form?" — the bare fragment above is a *substring* match, so unanchored it
#: finds "Spa" inside "Spadaccini" and refuses every surname containing spa/sas/srl/snc
#: (Spataro, Spagnuolo, Sassi, Sasso…) as if it were a company.
COMPANY_SUFFIX_RE = re.compile(rf"(?<![\p{{L}}])(?:{COMPANY_SUFFIX})(?![\p{{L}}])",
                               re.IGNORECASE)

# Conservative signals for ``companies="person_named"``. They intentionally cover
# only clear family wording and simple two-surname names. Brand words can look like
# surnames, so broad title-case or dictionary-free name guessing is avoided.
PERSON_NAMED_COMPANY_FAMILY = re.compile(
    r"(?<!\p{L})(?i:f\s*\.?\s*lli\.?|fratelli|eredi)(?!\p{L})"
)
PERSON_NAMED_COMPANY_BRIDGE = re.compile(
    rf"^(?:{SEP}(?:{NAME_TOKEN}|[A-Z]\.|(?i:d(?:i|el|ella|ei|egli|elle)|e)|&))*"
    rf"{SEP}?$"
)
PERSON_NAMED_COMPANY_PREFIX = re.compile(rf"(?:{NAME_TOKEN}{SEP}){{1,3}}$")
PERSON_NAMED_COMPANY_PAIR = re.compile(
    rf"^({NAME_TOKEN}){SEP}(?i:e|&){SEP}({NAME_TOKEN})$"
)
PERSON_NAMED_COMPANY_SURNAME_END = re.compile(
    r"(?i:(?:etti|elli|ini|oni|ucci|acci|azzi|ezzi|izzi|ozzi|ardi|aldi|eri|ori|"
    r"esi|isi|chi|ghi|sca|sco|lino|nello))['’]?$"
)

# ── structured identifiers ───────────────────────────────────────────────────
# Case-sensitive: these are written in upper case in real documents, and making them
# case-insensitive turns ordinary words into matches.

#: Codice fiscale, validating the month letter and the day range (01–71, ≥32 = female).
CODICE_FISCALE = re.compile(
    r"\b[A-Z]{6}\d{2}[ABCDEHLMPRST](?:[0-6]\d|7[01])[A-Z]\d{3}[A-Z]\b")

#: Partita IVA — cue required. A bare 11-digit run is far more often a protocol number.
PARTITA_IVA = re.compile(
    r"(?i:p\.?\s?iva|partita\s+iva|c\.?f\.?\s?/\s?p\.?\s?iva|codice\s+iva)"
    r"[\s:.n°]*(\d{11})\b")

IBAN = re.compile(r"\bIT\d{2}[ ]?(?:[A-Z0-9][ ]?){23}\b")

#: PEC must be tried before EMAIL so a PEC address is labelled as such.
PEC = re.compile(
    r"\b[\w.%+\-]+@(?:pec\.|legalmail\.|postacert\.|[\w\-]*pec[\w\-]*\.)[\w.\-]+\.\w{2,}\b",
    re.I)
EMAIL = re.compile(r"\b[\w.%+\-]+@[\w.\-]+\.\w{2,}\b")

#: Phone — a cue is required, otherwise every case number reads as a number to remove.
#: The one exception is an explicit +39 country prefix, which nothing else in a decision
#: carries, so a bare "+39 011 4478230" in a contact block is still caught.
TELEFONO = re.compile(
    r"(?i:tel\.?|telefono|cell\.?|cellulare|fax|mobile)[\s:.n°]*"
    r"((?:\+39[\s.\-]?)?\d[\d\s.\-/]{6,13}\d)"
    r"|(\+39[\s.\-]?\d[\d\s.\-/]{6,13}\d)")

TARGA = re.compile(r"\b[A-Z]{2}\s?\d{3}\s?[A-Z]{2}\b")

#: Identity-document number, cue required.
NUMERO_DOCUMENTO = re.compile(
    r"(?i:carta\s+d[i']\s?identit[àa]|passaporto|patente|C\.I\.E?\.|"
    r"documento\s+d[i']\s?identit[àa])[\s:,n.°]*([A-Z]{2}\s?\d{5,7}[A-Z]?)\b")

#: Date of birth. Procedural dates are deliberately not matched.
DATA_NASCITA = re.compile(
    r"(?i:nat[oa]|nasc(?:it[ao])?|d\.d\.n\.)[\s,]*(?:a\s+\S+\s+)?"
    r"(?i:il|in\s+data|del)?\s*"
    r"(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}|\d{1,2}\s+(?i:" + MONTHS + r")\s+\d{4})\b")

STRUCTURED = [
    ("CF", CODICE_FISCALE, 0),
    ("IVA", PARTITA_IVA, 1),
    ("Iban", IBAN, 0),
    ("Pec", PEC, 0),
    ("Email", EMAIL, 0),
    ("Telefono", TELEFONO, 1),
    ("Documento", NUMERO_DOCUMENTO, 1),
    ("Targa", TARGA, 0),
    ("Data_nascita", DATA_NASCITA, 1),
]
"""(label, pattern, group) — group 0 means "the whole match is the value"."""

#: Residential address. Anchored on a *personal* residence cue only: "con sede" is
#: excluded on purpose, because an organisation's registered office stays in clear.
INDIRIZZO_RESIDENZA = re.compile(
    r"(?i:residente|domiciliat[oa]|abitante|dimorante)"
    r"(?:\s+(?i:attualmente|in|a|presso|nel|alla))*\s*:?\s+"
    r"((?i:via|viale|v\.le|piazza|p\.zza|largo|corso|c\.so|vicolo|str\.|strada|"
    r"loc\.|località|fraz\.|frazione|contrada|borgo)"
    r"[\p{L}\s0-9,.'’\-]{3,60}?\d{1,4}[\p{L}\s,.'’\-]{0,30}?\b\d{5}\b)")

# ── judicial-role evidence ───────────────────────────────────────────────────
# Case-sensitive on the name, case-insensitive on the role word.

#: A judicial role word, optionally followed by a second one ("Consigliere relatore").
#: Deliberately *excludes* bare "magistrato/i", which only counts as a judicial cue when
#: JUDGE_LIST_CUE sees "composta da…" in front of it. On its own it appears in contexts
#: that have nothing to do with a bench — an HTML export's metadata trailer carries it
#: as a literal Windows folder name (``U:\DocumentiGA\Magistrati\769…``) — and would
#: then hand a nearby party to the role-plus-title anchors below. `referendario` is the
#: TAR's junior rank, and very often the judge who drafts the decision.
JUDICIAL_ROLE = (r"(?:presidente|consigliere|rel\.?\s*consigliere|giudice|"
                 r"(?:primo\s+)?referendari[oa]|"
                 r"sostituto\s+procuratore|procuratore\s+generale|\bp\.?\s?g\.?\b|"
                 r"cancelliere|segretario|relatore|estensore|componente)"
                 r"(?:\s+(?:relatore|estensore|monocratico|istruttore|generale|"
                 r"delegato|unico|e\s+relatore))?")

#: Field labels of the Cassazione header block. Used as a *terminator*: whatever
#: follows one of these is a new field, not more of the current name.
HEADER_FIELD = (r"(?i:relatore|estensore|presidente|"
                r"data\s+(?:pubblicazione|udienza|decisione))[^\S\r\n]*:")

# NOTE ON FLAGS: the cue words are wrapped in a scoped `(?i:…)` so that the *name*
# stays case-sensitive — making the whole pattern case-insensitive is exactly the
# defect these patterns were ported to fix. `re.M` must be a compile flag, not a
# scoped one: a scoped `(?m:…)` around the cue leaves `$` meaning end-of-string, which
# silently reduced this anchor to "only matches on the last line of the file".
JUDGE_ANCHORS = [
    # The Cassazione header, in both the layouts the corpus actually contains:
    #
    #     Presidente: CATALDI MICHELE                     ← one field per line (23%)
    #     … Num. 14112 Anno 2014 Presidente: STILE PAOLO Relatore: NAPOLETANO GIUSEPPE
    #                                                     ← whole header flattened (17%)
    #
    # Anchoring the cue to `^` and the name to `$` read only the first layout, which
    # left the bench unprotected in roughly a sixth of the corpus. So the name ends at
    # a line break *or* at the next field label instead. FULL_NAME is greedy and
    # "Relatore" is capitalised, so it would happily swallow the label — the lookahead
    # is what forces the backtrack that stops the name before it.
    re.compile(rf"\b(?i:presidente|relatore|estensore|giudice)"
               rf"[^\S\r\n]*:[^\S\r\n]*({FULL_NAME})"
               rf"(?=[^\S\r\n]*(?:$|{HEADER_FIELD}))", re.M),
    # "dal Consigliere CHIECA Danilo" / "dal consigliere dott. Alberto Crivelli"
    re.compile(rf"(?i:d(?:al|a|el)\s+(?:{JUDICIAL_ROLE})\s+"
               rf"(?:dott\.?(?:ssa)?\s+|avv\.?\s+)?)({FULL_NAME})"),
    # "Sostituto procuratore generale Tommaso Basile"
    re.compile(rf"(?i:sostituto\s+procuratore(?:\s+generale)?\s+"
               rf"(?:dott\.?(?:ssa)?\s+)?)({FULL_NAME})"),
    # "MAROZZO ANTONIO, Presidente e Relatore"  (CGT merito header)
    # The optional single letter is a middle initial the court's own records carry
    # ("TREVISANATO ORNELLA A, Giudice"). NAME_TOKEN needs two characters, so without
    # this the comma never follows the name and the whole anchor fails — losing the
    # judge, not just the initial. It stays outside the capture group: the initial is
    # not part of how the name is written anywhere else in the document.
    re.compile(rf"^[^\S\r\n]*({FULL_NAME})(?:[^\S\r\n]+\p{{Lu}}\.?)?"
               rf"[^\S\r\n]*,[^\S\r\n]*(?i:{JUDICIAL_ROLE})\b", re.M),
    # "Mario Rossi - Presidente -"
    re.compile(rf"({FULL_NAME})\s*[-–]\s*(?i:{JUDICIAL_ROLE})\s*[-–]"),
    # "il Presidente dott. Mario Rossi"
    re.compile(rf"(?i:(?:il|la)\s+(?:{JUDICIAL_ROLE})\s+"
               rf"(?:dott\.?(?:ssa)?\s+))({FULL_NAME})"),
    # "CONCLUSIONI DELL'AVVOCATO GENERALE\nMANUEL CAMPOS SÁNCHEZ-BORDONA" — the EU
    # Advocate General signs on the line below the heading, and is a judicial figure.
    re.compile(rf"(?i:avvocat[oa]\s+general[ei])\s*[:\n]\s*({FULL_NAME_NL})"),
    # The signature block that closes a decision — the role stands alone on its line
    # and the name follows on the next non-empty one:
    #
    #     Il Presidente
    #
    #     Federico Maria Sbaraglia
    #
    # Requiring the role to occupy the *whole* line is what makes this safe to stretch
    # across the blank lines. A bare role word with a name somewhere after it would
    # reach straight into the parties, which is why the anchors below all need a title.
    re.compile(rf"^[^\S\r\n]*(?i:(?:il|la)\s+|l['’]\s*)?(?i:{JUDICIAL_ROLE})[^\S\r\n]*"
               rf"(?:\n[^\S\r\n]*){{1,4}}({FULL_NAME})[^\S\r\n]*$", re.M),
    # "il Cons. Nicola D'Angelo" / "il consigliere Nicola D'Angelo" (Consiglio di Stato),
    # "il referendario Anna Bianchi", and the older "il consigliere avv. Liana Tacchi"
    re.compile(rf"(?i:il\s+)?(?i:cons\.|consiglier[ea]|(?:primo\s+)?referendari[oa])\s+"
               rf"(?:(?i:avv\.|dott\.?(?:ssa)?|dr\.?(?:ssa)?)\s*)?({FULL_NAME})"),
    # Corte dei Conti sometimes prints the judge after a formal "nella persona"
    # clause, with the unexplained title "Ref." and even a line break inside the
    # surname:
    #   nella persona del Giudice unico
    #   Ref. Mastrogiacomo
    #    D'Oro
    re.compile(rf"(?i:nella\s+persona\s+del(?:la)?\s+{JUDICIAL_ROLE})\s+"
               rf"(?:(?i:ref\.|dott\.?(?:ssa)?|dr\.?(?:ssa)?)\s+)?"
               rf"({FULL_NAME_NL})"),
    # A role word and the name are often separated by a clause:
    #   "Relatore nella camera di consiglio del giorno 5 novembre 2025 la dott.ssa X"
    #   "In persona del Giudice monocratico Consigliere\ndott.ssa Y"
    # The title is what makes this safe to stretch — a bare role word plus 90 characters
    # of slack would swallow the parties.
    re.compile(rf"(?i:{JUDICIAL_ROLE}|magistrat[oi])"
               rf"(?:[^\n]|\n(?!\n)){{0,90}}?"
               rf"(?i:dott\.?(?:ssa)?|dr\.?(?:ssa)?)\s*({FULL_NAME})"),
    # …and the mirror image, where the role follows the name in a tabular header:
    #   "composta dai magistrati dr. Clotilde Pontremoli        Presidente"
    # …or in running prose, comma-separated:
    #   "la requisitoria del dott. Augusto Corbellini, Sostituto Procuratore generale"
    re.compile(rf"(?i:dott\.?(?:ssa)?|dr\.?(?:ssa)?)\s*({FULL_NAME})"
               rf"(?:[^\S\r\n]{{2,}}|\s*\n\s*|\s*,\s*)(?i:{JUDICIAL_ROLE})\b"),
]

#: Opens a bench list where names run one per line — often with a title, blank lines,
#: and stray punctuation between them, and role words ("Presidente", "Consigliere")
#: trail one or more names later rather than sitting next to each one:
#:   "composta dai Magistrati:\nDott. X\n\nPresidente - relatore\nY\n\nDott.ssa Z\n…"
#: A strict per-line grammar (title? + name + nothing else) breaks the moment one line
#: doesn't fit that shape — a role-only line, a blank line, a name with a title where
#: its neighbours have none. `protect.py` instead reads a bounded character *window*
#: after this cue and treats every plausible name inside it as a judge, which tolerates
#: that layout noise instead of trying to parse it exactly.
JUDGE_LIST_CUE = re.compile(
    r"(?i:composta\s+da[ilgh]{1,3}\s+(?:seguenti\s+)?"
    r"(?:sigg\.?ri\s+|signori\s+)?magistrat[oi]\s*:?)")
#: The outer bound on how far past the cue a name still counts as bench membership —
#: `protect.py` also stops at the first clear sign the bench list has ended (see
#: JUDGE_LIST_END below), so this is a backstop, not the primary control. Generous
#: enough for a five-person panel with titles and blank lines between them.
JUDGE_LIST_WINDOW = 400
#: Marks the end of a bench list: the decision's own heading, or the phrase that opens
#: the case narrative. Without this, "composta dai magistrati: …" on a short panel
#: could reach past the panel into "SENTENZA nel giudizio … nei confronti di X" and
#: protect the very party the panel is about to judge.
JUDGE_LIST_END = re.compile(
    r"(?i:ha\s+pronunciato|\bSENTENZA\b|\bORDINANZA\b|\bDECRETO\b|"
    r"nel\s+giudizio|promosso\s+da|proposto\s+da|nei\s+confronti\s+di)")

#: The administrative courts announce their panel *after* the verb, inline:
#:
#:   "…per le Marche (Sezione Seconda) ha pronunciato la presente SENTENZA Osvaldo Di
#:    Benedetto, Presidente, Federico Maria Sbaraglia, Ornella Trevisanato, Consigliere"
#:
#: Only the first and last member carry a role word, so the per-name anchors reach the
#: ends of the panel and miss everyone in the middle. Read as a window instead.
#: The lookahead is the safety catch: the same phrase introduces the *case* when the
#: panel sits on its own lines ("…la presente SENTENZA\nsul ricorso proposto da X"),
#: and without it that party would be protected as if they were a judge.
JUDGE_INLINE_CUE = re.compile(
    rf"(?i:ha\s+pronunciato\s+la\s+presente\s+(?:sentenza|ordinanza|decreto))"
    rf"(?=[^\n]*\b(?i:{JUDICIAL_ROLE})\b)")

#: Bench-list cues paired with the terminator that fits each one. The block layouts run
#: over several lines and stop at the decision's heading; the inline layout is confined
#: to the cue's own line, so the line break *is* the terminator.
JUDGE_LISTS = [
    (JUDGE_LIST_CUE, JUDGE_LIST_END),
    (JUDGE_INLINE_CUE, re.compile(r"\n")),
]

#: Head words of public bodies, courts and agencies — never pseudonymized.
#: Word-bounded: without `\b` this matched "avvocatura" inside the domain of
#: `ags.rm@mailcert.avvocaturastato.it` and shielded a real e-mail from substitution.
INSTITUTION_HEAD = re.compile(
    r"\b(?i:agenzi[ae]|ag\.?\s+entrat|minister[oi]|ministro|i\.?n\.?p\.?s\.?|"
    r"inail|inpgi|inpdap|istitut[oi]|"
    r"avvocatura|generale\s+dello\b|roma\s+capitale\b|comune|regione|provincia|città\s+metropolitana|universit|"
    r"azienda\s+(?:ospedaliera|sanitaria)|a\.?s\.?l\.?|equitalia|riscossione|ader|"
    # health authorities by acronym ("Asur Marche Area Vasta n. 1", "ASP di Catania");
    # word-bounded, so the surname Aspesi is not one
    r"(?:asur|asp|ausl|usl|ulss|asst|ats|aou|irccs)\b|area\s+vasta|"
    r"presidenza|consiglio|procura|pretura|tribunale|corte|commissione\s+tributaria|"
    r"prefettura|questura|camera\s+di\s+commercio|poste\s+italiane|ferrovie|"
    r"direzione\s+(?:provinciale|regionale|centrale)|ufficio|ente|croce\s+rossa|"
    r"guardia\s+di\s+finanza|polizia|carabinieri|repubblica|stato|governo|senato|"
    r"parlamento|demanio|dogan|monopoli|finanz|erario|tesoro|assessorat|"
    r"soprintendenz|motorizzazione|ispettorat|sovrintendenz|"
    r"fallimento|curatela|condominio|parrocchia|diocesi)")
# NOTE: leading \b only. A trailing \b silently disabled every *prefix* alternative —
# "universit" no longer matched "UNIVERSITARIA", so "AZIENDA OSPEDALIERA UNIVERSITARIA
# FEDERICO II" was cut into the "person" FEDERICO II. Over-matching is safe here because
# this is a rejection rule for candidates, not a shield over spans of text.

#: Street and place prefixes. An address in a party block is an elective domicile, not
#: a person: "VIA CESARE BECCARIA" and "PIAZZA BENEDETTO CAIROLI" were both seeded as
#: parties and pseudonymized out of the document.
STREET_HEAD = re.compile(
    r"^(?i:via|viale|v\.le|vle|piazza|p\.zza|piazzale|largo|corso|c\.so|vicolo|"
    r"strada|str\.|lungotevere|lungomare|località|loc\.|frazione|fraz\.|contrada|"
    r"borgo|salita|calle|campo|traversa|circonvallazione)\b")

#: Head words of organisations that are not public bodies but are not people either.
#: A candidate containing one of these is a company or an association, never a person,
#: whatever its capitalisation looks like.
ORG_HEAD = re.compile(
    r"\b(?i:banc[ao]|banche|cassa|credito|cooperativa|coop|consorzio|società|societa|"
    r"associazione|fondazione|assicurazion[ei]|autostrade|immobiliare|costruzioni|"
    r"impresa|ditta|studio\s+legale|holding|group|gruppo|s\.?p\.?a|s\.?r\.?l|"
    r"editrice|editoriale|industri[ae]|trasporti|servizi|energia|petrol|farmaceutic|"
    r"agricola|agriturismo|vivai|cantine|tenuta|hotel|albergo|clinica|"
    r"casa\s+di\s+cura)\b")

#: Connectors that never start a personal name, so a candidate beginning with one is a
#: broken slice of a longer institution name ("DELLE FINANZE", "PER L'ITALIA"). The
#: singular forms are deliberately absent: "De Luca", "Della Maggiora" and "Lo Giudice"
#: are ordinary Italian surnames.
FRAGMENT_HEAD = frozenset(
    "delle degli dei per con su in ed e al alla ai agli nel nella sul sulla tra fra "
    "che non ha".split())

#: Words that end a name capture. Two kinds, for the same reason — a capture allowed to
#: run past the person swallows the next word and deletes it from the document:
#:   * section headings, hit when a name-with-line-break capture runs onto the next line
#:     ("dall'avv. Gallusi Sandro\nFATTI DI CAUSA" → the "person" "Gallusi Sandro FATTI DI");
#:   * role words, which follow a name as often as they precede it ("MALINVERNI ISOTTA
#:     Avvocato" → the "person" "MALINVERNI ISOTTA Avvocato", and "Avvocato" vanishes).
SECTION_HEADING_TOKENS = frozenset("""
fatti fatto causa diritto ritenuto rilevato considerato osserva svolgimento processo
motivi motivazione decisione dispositivo conclusioni premesso premessa massima
ordinanza sentenza decreto p.q.m. pqm epigrafe udienza adunanza camera consiglio
ricorrente controricorrente resistente intimato appellante appellato
avvocato avvocati avvocatessa difensore difensori presidente giudice relatore
consigliere consiglieri procuratore rappresentante magistrato magistrati cancelliere
perito consulente contribuente imputato convenuto attore erede notaio
""".split())

#: Procedural identifiers kept in clear when Config.keep_case_numbers is on. A bare
#: value is accepted only with a four-digit year and cannot start after another slash;
#: this prevents ``12/03/1974`` from being mistaken for case ``03/1974``.
CASE_NUMBER = re.compile(
    r"(?i:n\.?|numero|nn\.|n°)\s*\d{1,6}\s?/\s?\d{2,4}\b"
    r"|(?<![\d/])\d{1,6}\s?/\s?(?:19|20)\d{2}\b"
    r"|(?i:r\.?\s?g\.?(?:\s?n\.?)?|ruolo\s+generale)[\s.:n°]*\d{1,6}\s?/\s?\d{2,4}"
    r"|(?i:ecli):[A-Z]{2}:[A-Z]+:\d{4}:\w+")

# ── person seeds ─────────────────────────────────────────────────────────────

#: Defence counsel. Tolerates a line break inside the name, and the ALL-CAPS form.
COUNSEL = re.compile(
    rf"(?:{COUNSEL_CUE}|(?i:difensor[ei]|procuratore\s+(?:speciale|domiciliatario)))"
    rf"\s+(?:(?i:dell[ao'’]|di|del)\s+)?({FULL_NAME_NL})")

#: A *list* of counsel: "difesi dagli avvocati A B, C D, E F e G H".
#: Court documents name several lawyers at once far more often than one, so matching
#: only the first name after the cue halves recall on any collegiate appeal.
COUNSEL_LIST = re.compile(
    rf"{COUNSEL_CUE}\s+"
    rf"({FULL_NAME}(?:\s*,\s*{FULL_NAME})*(?:\s*,?\s*(?i:ed?)\s+{FULL_NAME})?)")

#: Splits a captured list — of counsel, or of parties (PARTY_LIST) — back into names.
COUNSEL_LIST_SEP = re.compile(r"\s*[,;]\s*|\s+(?i:ed?)\s+")

#: Counsel named by surname alone: "per l'Inps l'avv. Scaramuzza". Very common in
#: hearing minutes, and counsel must always be pseudonymized. Safe only because the
#: single token still has to clear the corpus common-word guard downstream.
COUNSEL_SOLO = re.compile(rf"{COUNSEL_CUE}\s+({NAME_TOKEN})(?![\p{{L}}])")

#: "difeso/rappresentato/assistito da(ll'avv.) X"
DIFESO_DA = re.compile(
    rf"(?i:dife[sn][oa]|rappresentat[oa]|assistit[oa]|patrocinat[oa])\s+"
    rf"(?i:e\s+(?:dife[sn]|rappresentat|assistit)[oa]\s+)?"
    rf"(?i:dall?[i'’]?|da)\s*(?:{COUNSEL_CUE}|(?i:procuratore))?\s*({FULL_NAME_NL})")

#: Professional or courtesy title + name.
TITOLO = re.compile(
    rf"(?i:dott\.(?:ssa)?|dr\.(?:ssa)?|sig\.(?:ra)?|signor(?:a)?|ing\.|prof\.(?:ssa)?|"
    rf"geom\.|arch\.|rag\.|not(?:aio|\.))\s*({FULL_NAME})")

#: Name immediately followed by biographic or fiscal detail. The separator tolerates a
#: line break and an adverb ("CAVALCANTI SERAFINA\n, ivi residente"), which is how these
#: clauses wrap in converted court text — but it must be **at least one real character**
#: (whitespace or a comma). Allow a zero-width gap and the cue `nat[oa]\b` matches the
#: literal tail of any surname ending in "-nato": "Ornella Trevisanato" reads as the
#: name "Ornella Trevisa" followed by its own cue, and four-fifths of a surname is
#: pseudonymized out of the document. "domiciliata ex lege" is not a person's domicile but
#: the Avvocatura dello Stato's, and follows a place: "…dello Stato di Reggio Calabria,
#: domiciliata ex lege" made the court's own seat a person.
BIOGRAFICO = re.compile(
    rf"(?<![\p{{L}}])({FULL_NAME})(?:\s*,\s*|\s+)"
    rf"(?:(?i:ivi|già|quivi|attualmente)\s+)?"
    rf"(?i:nat[oa]\b|residente\b|domiciliat[oa]\b(?!\s+ex\s+lege)|dimorante\b|c\.?f\.?\b|"
    rf"codice\s+fiscale\b|in\s+proprio\b|quale\s+erede\b|in\s+qualità\s+di\b)")

#: Name adjacent to a codice fiscale — the strongest anchor there is.
CF_ADIACENTE = re.compile(
    rf"({FULL_NAME_NL})\s*[(\[]?\s*"
    rf"(?:(?i:c\.?f\.?|codice\s+fiscale)[\s:.]*)?"
    rf"([A-Z]{{6}}\d{{2}}[ABCDEHLMPRST](?:[0-6]\d|7[01])[A-Z]\d{{3}}[A-Z])\b")

#: Digital-signature block left in converted PDFs.
PKI_FIRMA = re.compile(rf"(?i:firmato\s+da)\s*:\s*({FULL_NAME_NL})\s+(?i:emesso)")

#: Party roles used to label a seed, and to find one in prose.
PARTY_ROLE = re.compile(
    rf"(?i:il\s+|la\s+|i\s+|le\s+)?(?i:ricorrent[ei]|resistent[ei]|controricorrent[ei]|"
    rf"appellant[ei]|appellat[oi]|intimat[oi]|opponent[ei]|opposto|attor[ei]|"
    rf"convenut[oi]|contribuent[ei]|istant[ei])[:\s,]+({FULL_NAME})")

#: The commonest way an Italian decision names a party: "proposto da <Name>, …".
#: Cassazione writes it in the ALL-CAPS party block, but the administrative and civil
#: courts write it in ordinary case inline, which the block scan never sees.
#: Institutions and companies following the same cue are refused downstream.
APPLICANT_CUE = (r"(?i:proposto\s+da(?:l(?:la)?|i|gli|lle)?|ricorso\s+di|promoss[oa]\s+da)"
                 r"(?:\s+(?i:i\s+)?(?i:signori|sigg?\.\s?(?:ri|re)|sig\.(?:ra)?))?")
#: …and the other side: "nei confronti di X" in running text, or the administrative
#: courts' label "nei confronti" alone on its line, with the parties below it.
COUNTERPARTY_CUE = r"(?i:nei\s+confronti(?:\s+di\b|(?=[^\S\n]*\n)))"
PROPOSTO_DA = re.compile(rf"{APPLICANT_CUE}\s*:?\s*({FULL_NAME})")
NEI_CONFRONTI = re.compile(rf"{COUNTERPARTY_CUE}\s*:?\s*({FULL_NAME})")

#: A *list* of parties at one cue. Mass appeals name dozens of applicants, and the
#: counter-interested parties of a public competition come in lists as well:
#:   "proposto da Giulia Balestri, Lucia Surpo, Maurita Perfetti e Anna Vezzi, …"
#: As with counsel, the single-name anchors above only ever see the first of them.
#: Party lists are also written with semicolons: "nei confronti di A; B; C;".
PARTY_LIST = re.compile(
    rf"(?:{APPLICANT_CUE}|{COUNTERPARTY_CUE})\s*:?\s*"
    rf"({FULL_NAME}(?:\s*[,;]\s*{FULL_NAME})*(?:\s*[,;]?\s*(?i:ed?)\s+{FULL_NAME})?)")

#: Civil-law capacities that introduce a named individual in the body of a decision:
#: "all'altro socio TAGLIAFERRI NICODEMO", "la ditta di PICCININI GUALTIERO".
QUALIFICA = re.compile(
    rf"(?<![\p{{L}}])(?i:soci[oa]|amministrator[ei]|titolar[ei]|legale\s+rappresentante|"
    rf"erede|eredi|coniuge|curator[ei]|liquidator[ei]|tutor[ei]|"
    rf"(?:s\.?a\.?s\.?|s\.?n\.?c\.?|ditta|impresa|società)\s+di)"
    rf"[\s:,]+({FULL_NAME})")

#: The Cassazione party block: everything between "proposto da" / "contro" and the
#: next structural marker. Names inside it are parties or their counsel.
PARTY_BLOCK = re.compile(
    r"(?i:(?:ricorso\s+)?proposto\s+da|nei\s+confronti\s+di|^\s*contro\s*$|"
    r"\bcontro\b)\s*:?\s*"
    r"(.{0,700}?)"
    r"(?=\n\s*[-–]\s*(?i:ricorrent|controricorrent|resistent|intimat|appellant|appellat)"
    r"|(?i:\bavverso\b|\bFATTI\s+DI\s+CAUSA\b|\bRILEVATO\b|\bRITENUTO\b|\bSVOLGIMENTO\b|"
    r"\bMOTIVI\b|\bVista\s+la\s+proposta\b|\budita\s+la\s+relazione\b)|\Z)",
    re.S | re.M)

#: A *maximal* run of upper-case words. Candidates are cut from a run only after the
#: whole run has been cleared, because a fixed-width name window slices long
#: institution names into innocent-looking fragments: "PROCURA GENERALE PRESSO LA
#: SUPREMA CORTE D'APPELLO DI TRIESTE" yielded the "person" "D'APPELLO DI TRIESTE"
#: once the head words had been consumed by the preceding window.
ALLCAPS_RUN = re.compile(
    r"(?<![\p{L}])\p{Lu}[\p{Lu}'’]+(?:[^\S\r\n]+\p{Lu}[\p{Lu}'’.&]+)*(?![\p{L}])")

#: An ALL-CAPS run inside the party block — how Cassazione writes party names.
#: Tokens of two letters are allowed only in the middle of a run, so "DI" cannot start
#: a candidate and turn "CHITI PAOLO ... DI" into the person "DI Chiti Paolo".
ALLCAPS_NAME = re.compile(
    r"(?<![\p{L}])(\p{Lu}[\p{Lu}'’]{2,}(?:\s+\p{Lu}[\p{Lu}'’]+){1,3})(?![\p{L}])")

#: Private company with a legal-form suffix (only used when Config.companies is on).
SOCIETA = re.compile(
    rf"(?<![\p{{L}}])((?:{NAME_TOKEN}|d(?:i|el|ella|ei|egli|elle)|e|&)"
    rf"(?:{SEP}(?:{NAME_TOKEN}|d(?:i|el|ella|ei|egli|elle)|e|&)){{0,6}}"
    rf"{SEP}(?i:{COMPANY_SUFFIX}))(?![\p{{L}}])")
