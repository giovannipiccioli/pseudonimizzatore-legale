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
#: The same, but at least one character: after a list's "e".
SEP_NL1 = r"(?=\s)[^\S\r\n]*\n?[^\S\r\n]*"
#: 2–4 capitalised tokens.
FULL_NAME = rf"{NAME_TOKEN}(?:{SEP}{NAME_TOKEN}){{1,3}}"
#: Same, tolerating one line break between tokens.
FULL_NAME_NL = rf"{NAME_TOKEN}(?:{SEP_NL}{NAME_TOKEN}){{1,3}}"

MONTHS = (r"gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|"
          r"ottobre|novembre|dicembre")

#: How counsel are introduced. `avv.to` and `avv.ti` are as common in Italian practice
#: as `avv.` itself, and matching only the latter loses a whole class of documents.
#: Not after a judicial role word: older decisions title the reporting judge "il
#: consigliere avv. X", and that X sits on the bench. The same holds for a header field
#: ("Giudice: avv. Biagio Stomeo"): a tax court's lay judge is often a lawyer.
COUNSEL_CUE = (r"(?<!(?i:consiglier[ea]|referendari[oa]|relatore|presidente|giudice)"
               r"(?:\s+|[^\S\n]*:[^\S\n]*))"
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
# case-insensitive turns ordinary words into matches. The codice fiscale is the one
# exception, because its check character can tell a code from a word.

#: A codice fiscale digit, or the letter that replaces it under omocodia: when two
#: people would share a code, digits become L M N P Q R S T U V (0–9), rightmost first.
_CF_DIGIT = "[0-9LMNPQRSTUV]"
_CF_CHARS = (["[A-Z]"] * 6 + [_CF_DIGIT] * 2 + ["[ABCDEHLMPRST]"] + [_CF_DIGIT] * 2
             + ["[A-Z]"] + [_CF_DIGIT] * 3 + ["[A-Z]"])

#: Codice fiscale, validating the month letter. It also reads omocodia, lower case and
#: characters typed one by one ("R S S M R A 8 0 …"); `codice_fiscale_ok` checks the day
#: range and, for the looser forms, the check character.
CODICE_FISCALE = re.compile(r"\b(?i:" + "[ ]?".join(_CF_CHARS) + r")\b")

_OMOCODIA = str.maketrans("LMNPQRSTUV", "0123456789")
_CF_ODD = dict(zip("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                   (1, 0, 5, 7, 9, 13, 15, 17, 19, 21) * 2
                   + (2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23)))
_CF_EVEN = {c: int(c) if c.isdigit() else ord(c) - ord("A")
            for c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"}


def codice_fiscale_ok(value: str) -> bool:
    """Whether a CODICE_FISCALE match is a codice fiscale.

    The usual form, upper case, unbroken and with digits, is accepted without the check
    character, as it always was: a typo in the last letter leaves it just as
    identifying. Lower case and spaced forms must carry a valid check character.
    """
    cf = value.replace(" ", "").upper()
    if int(cf[9:11].translate(_OMOCODIA)) > 71:      # day, +40 for women
        return False
    if value == cf and re.search(r"\d", cf):
        return True
    total = sum((_CF_ODD if i % 2 == 0 else _CF_EVEN)[c] for i, c in enumerate(cf[:15]))
    return cf[15] == chr(ord("A") + total % 26)

#: Partita IVA — cue required. A bare 11-digit run is far more often a protocol number.
PARTITA_IVA = re.compile(
    r"(?i:p\.?\s?iva|partita\s+iva|c\.?f\.?\s?/\s?p\.?\s?iva|codice\s+iva)"
    r"[\s:.n°]*(\d{11})\b")

#: IBAN: the Italian form, and any other country's (SM, DE…), which must pass the
#: mod-97 check in `iban_ok` because its looser shape also fits act numbers. A foreign
#: IBAN is read unbroken or in the printed groups of four, never with a space anywhere:
#: that would let it run on into "… BIC COBADEFF" and then fail its check. An Italian
#: one may also be typed with a space after the country code and irregular groups
#: ("IT 77 A 01030 03400 000063241578"); that form must pass the check as well.
IBAN = re.compile(r"\bIT[ ]?\d{2}(?:[ ]?[A-Z0-9]){23}\b"
                  r"|\b(?!IT)[A-Z]{2}\d{2}"
                  r"(?:[A-Z0-9]{11,30}|(?: [A-Z0-9]{4}){2,7}(?: [A-Z0-9]{1,4})?)\b")


def iban_ok(value: str) -> bool:
    """Whether an IBAN match is one: Italian as before, any other by its mod-97 check."""
    iban = value.replace(" ", "")
    if value.startswith("IT") and value[2:3] != " ":
        return True
    return int("".join(str(int(c, 36)) for c in iban[4:] + iban[:4])) % 97 == 1

#: PEC must be tried before EMAIL so a PEC address is labelled as such.
PEC = re.compile(
    r"\b[\w.%+\-]+@(?:pec\.|legalmail\.|postacert\.|[\w\-]*pec[\w\-]*\.)[\w.\-]+\.\w{2,}\b",
    re.I)
EMAIL = re.compile(r"\b[\w.%+\-]+@[\w.\-]+\.\w{2,}\b")

#: Mail domains of Italian public administrations. An office mailbox there
#: (``dp.treviso@pce.agenziaentrate.it``, ``protocollo@pec.comune.verona.it``) names a
#: public body, not a person, and a request to the Agency is unusable without it. Only a
#: registered domain counts: a lawyer's PEC at the bar association
#: (``…@pec.ordineavvocatitreviso.it``) is personal. ``gov.it`` is reserved to public
#: administrations.
PUBLIC_MAIL_DOMAIN = re.compile(
    r"@(?:[\w\-]+\.)*(?:agenziaentrate\.it|gov\.it|inps\.it|inail\.it|giustizia\.it|"
    r"giustiziacert\.it|ga-cert\.it|giustizia-amministrativa\.it|corteconti\.it|"
    r"avvocaturastato\.it|(?:comune|provincia|regione)\.[\w\-]+\.it)$", re.I)


def public_mailbox(value: str) -> bool:
    """Whether an e-mail or PEC address is a public office's mailbox.

    The domain must be a public administration's and the mailbox must not carry a first
    name: ``mario.rossi@agenziaentrate.it`` belongs to an official, who is a person.
    """
    if not PUBLIC_MAIL_DOMAIN.search(value):
        return False
    from .seeds import first_names
    local = value.split("@", 1)[0]
    return not any(token.casefold() in first_names()
                   for token in re.findall(r"\p{L}+", local))


#: Phone — a cue is required, otherwise every case number reads as a number to remove.
#: The one exception is an explicit +39 country prefix, which nothing else in a decision
#: carries, so a bare "+39 011 4478230" in a contact block is still caught. The digits
#: stay on one line: a number may not run on into the next line's date or case number.
TELEFONO = re.compile(
    r"(?i:tel\.?|telefono|cell\.?|cellulare|fax|mobile)[\s:.n°]*"
    r"((?:\+39[\t .\-]?)?\d[\d\t .\-/]{6,13}\d)"
    r"|(\+39[\t .\-]?\d[\d\t .\-/]{6,13}\d)")

TARGA = re.compile(r"\b[A-Z]{2}\s?\d{3}\s?[A-Z]{2}\b")

#: Identity-document number, cue required: identity card (paper ``AY 4571203`` or
#: electronic ``CA12345AB``), passport, driving licence. The cue may carry a nationality
#: ("passaporto tedesco n.") and the number may sit in brackets ("passport (n. …)"). A
#: passport number is any 8–10 capitals and digits with at least one of each
#: (``C7HN4R2T9``, ``YA1234567``); requiring both keeps an ALL-CAPS word out.
NUMERO_DOCUMENTO = re.compile(
    r"(?:(?i:carta\s+d[i']\s?identit[àa](?:\s+elettronica)?|passaport[oi]|passport|"
    r"patente(?:\s+di\s+guida)?|documento\s+d[i']\s?(?:identit[àa]|riconoscimento))|"
    r"\bC\.I\.(?:E\.)?|\bCIE\b)"
    r"(?:[^\S\n]+\p{Ll}{4,12}(?=[^\S\n]*(?i:n\.|n°|numero)))?[\s:,(n.°]*"
    r"([A-Z]{2}[ ]?\d{5,7}[A-Z]{0,2}|(?=\d*[A-Z])(?=[A-Z]*\d)[A-Z0-9]{8,10})(?![A-Z0-9])")

#: Bank account number, cue required: "conto corrente n. 000012345678", "c/c 123456".
CONTO_CORRENTE = re.compile(
    r"(?i:conto\s+corrente|c/c)(?:\s+(?i:bancario|postale))?[^\S\n]*"
    r"(?:(?i:n\.|n°|nr\.?|numero)[^\S\n]*)?(\d{6,15})(?![\d/])")

#: A registration number in a professional register identifies the professional as
#: surely as a codice fiscale: "iscritto all'Albo dei Dottori Commercialisti … di Prato
#: al n. 412/A", "Ordine degli Ingegneri della Provincia di Padova n. 3471", "Registro
#: dei Revisori Legali al n. 158243", "REA … al n. FO-312456". The cue is the register's
#: name; the clause between it and the number may not mention an act ("Ordine degli
#: Avvocati, delibera n. 12") nor end a sentence (only an initial's stop, as in
#: "C.C.I.A.A.", is crossed), and a number followed by a year is a case number.
_REGISTER = (r"(?i:albo|ordine|collegio)[^\S\n]+(?i:degli|dei|delle|nazionale|speciale|"
             r"unico|professionale)\b|(?i:registro[^\S\n]+(?:dei|degli)[^\S\n]+revisori)|"
             r"\bREA\b|(?i:r\.e\.a\.)")
NUMERO_ALBO = re.compile(
    rf"(?<![\p{{L}}])(?:{_REGISTER})"
    r"(?:(?!(?i:delibera|provvediment|decret|sentenz|ordinanz|protocoll|prot\.|"
    r"circolar|verbale|nota\b))[^.;\n\d]|(?<=(?<![\p{L}])\p{L})\.){0,140}?"
    r"(?i:n\.|n°|nr\.?|numero|matricola)[^\S\n]*"
    r"([A-Z]{0,3}-?\d{1,7}(?:/[A-Z0-9]{1,3})?)(?![\d/]|[.,]\d)")

#: Day and year written out, as notarial deeds do: "quindici marzo
#: millenovecentoquaranta".
_DAY_WORDS = (r"primo|uno|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|undici|dodici|"
              r"tredici|quattordici|quindici|sedici|diciassette|diciotto|diciannove|"
              r"venti|ventuno|ventidue|ventitr[eéè]|ventiquattro|venticinque|ventisei|"
              r"ventisette|ventotto|ventinove|trenta|trentuno")
_DATE_NUMERIC = (r"\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}|\d{1,2}°?\s+(?i:" + MONTHS +
                 r")\s+\d{4}")
_DATE_WORDS = (rf"(?i:{_DAY_WORDS})\s+(?i:{MONTHS})\s+(?i:mille\p{{L}}+|duemila\p{{L}}*)"
               rf"(?:[^\S\n]*\((?:{_DATE_NUMERIC})\))?")
#: Birthplace between the birth cue and the date: one to four words, then the province
#: or the country in brackets ("Lugo (RA)", "Monaco di Baviera (Germania)") or a form's
#: "Prov. TV".
_BIRTH_TOWN = (r"(?i:a|ad|in)\s+\p{Lu}[\p{L}'’.\-]*(?:[^\S\n]+[\p{L}'’\-]+){0,3}?"
               r"(?:\s*\([^()\n]{2,40}\))?(?:\s+(?i:prov\.?)\s+\p{Lu}{2})?\s+")

#: Date of birth. Procedural dates are deliberately not matched: the date must follow a
#: birth cue, possibly through the birthplace and "il", "l'" or "il giorno".
DATA_NASCITA = re.compile(
    rf"(?<![\p{{L}}])(?i:nat[oa](?:/[ao])?|nasc(?:it[ao])?|d\.d\.n\.)[\s,:]*"
    rf"(?:{_BIRTH_TOWN})?"
    r"(?i:il\s+giorno|il|l['’]|in\s+data|del)?\s*"
    rf"({_DATE_NUMERIC}|{_DATE_WORDS})(?![\p{{L}}\d])")

STRUCTURED = [
    ("CF", CODICE_FISCALE, 0),
    ("IVA", PARTITA_IVA, 1),
    ("Iban", IBAN, 0),
    ("Pec", PEC, 0),
    ("Email", EMAIL, 0),
    ("Telefono", TELEFONO, 1),
    ("Documento", NUMERO_DOCUMENTO, 1),
    ("Conto", CONTO_CORRENTE, 1),
    ("Albo", NUMERO_ALBO, 1),
    ("Targa", TARGA, 0),
    ("Data_nascita", DATA_NASCITA, 1),
]
"""(label, pattern, group) — group 0 means "the whole match is the value"."""

#: Checks a STRUCTURED value must pass beyond its pattern, by label.
STRUCTURED_CHECKS = {
    "CF": codice_fiscale_ok,
    "Iban": iban_ok,
    "Pec": lambda value: not public_mailbox(value),
    "Email": lambda value: not public_mailbox(value),
}

#: Street-type words that open an Italian address.
STREET_TYPE = (r"via|viale|v\.le|piazza|p\.zza|piazzale|piazzetta|largo|corso|c\.so|"
               r"vicolo|vico|str\.|strada|stradone|stradella|loc\.|località|fraz\.|"
               r"frazione|contrada|c\.da|borgo|lungotevere|lungomare|lungarno|riviera|"
               r"parco|salita|calle|traversa|circonvallazione|rampa")

#: An Italian street address: the street word, the street's name, the house number
#: ("38", "n. 42", "112/B", "154/7") and an optional CAP after a comma. What keeps prose
#: out is the street itself: a capital or a digit after the street word ("in via
#: preliminare", "nel corso del giudizio" have neither) and a house number. Every
#: address detector shares it; what differs between them is the evidence that the
#: address is a private one.
STREET_ADDRESS = (
    rf"(?i:{STREET_TYPE})"
    r"[^\S\n]+(?:(?i:d(?:i|el|ella|ello|ei|egli|elle|ell['’]))[^\S\n]*)?"
    r"(?:\d{1,2}°?[^\S\n]+)?\p{Lu}[\p{L}\d'’_\-]*\.?"
    r"(?:[^\S\n]+(?:\p{L}\.|[\p{L}\d'’_\-]+)){0,6}?"
    r"[^\S\n]*,?[^\S\n]*(?:(?i:n\.|n°|nr\.?|civ\.)[^\S\n]*)?"
    r"\d{1,4}(?:/\d{1,3}|/?[A-Za-z])?(?![\p{L}\d/])"
    r"(?:[^\S\n]*,?[^\S\n]*\d{5}(?!\d))?")

#: German and French street forms, number after ("Sendlinger Straße 15",
#: "Leopoldstraße 112") or before ("14 rue des Martyrs", which ends at its comma or CAP).
FOREIGN_STREET_ADDRESS = (
    r"(?:\p{Lu}[\p{L}\-]*[^\S\n]+)?(?:\p{Lu}[\p{L}\-]*(?:straße|strasse|weg|platz|gasse|allee)"
    r"|Straße|Strasse|Weg|Platz|Gasse|Allee)[^\S\n]+\d{1,4}[a-z]?(?![\p{L}\d])"
    r"|\d{1,4}(?:[^\S\n]?(?:bis|ter))?,?[^\S\n]+(?i:rue|avenue|boulevard|place|chemin|"
    r"allée|impasse|quai)(?:[^\S\n]+[\p{L}'’\-]+){1,5}?(?=[^\S\n]*,|[^\S\n]+\d{5})")

#: Residential, elective-domicile, studio or property address. Anchored on a *personal*
#: cue: where someone lives or is domiciled, where a professional has a studio
#: ("con studio in", "presso il suo studio in"), where a dwelling or a leased or sold
#: property is ("unità immobiliare sita in", "abitazione in"). "con sede" is excluded on
#: purpose, because an organisation's registered office stays in clear, and so is
#: "domiciliata ex lege", the Avvocatura dello Stato's.
#:
#: The street need not follow the cue: a town, a province or a "presso lo studio
#: dell'avv. X" may sit between them ("residente in Pratovecchio (AR), loc. Casalino 4").
#: That gap stops at a semicolon, at the word "sede" and at a full stop, unless the stop
#: closes a short abbreviation ("avv.", "n."), and at a blank line: the next paragraph
#: may be a public body's letterhead. The CAP is optional.
_ADDRESS_GAP = (r"(?:(?!(?i:sede)\b|\n[^\S\n]*\n)[^.;]"
                r"|(?<=(?<![\p{L}])\p{L}{1,4})\.)")
#: Cues naming a property rather than a person; the caller refuses them after a public
#: body ("il Tribunale, sito in …").
PROPERTY_CUE = re.compile(r"(?i:sit[oaie]|ubicat[oaie]|abitazione|abitativ[oa])\b")
INDIRIZZO_RESIDENZA = re.compile(
    r"(?<![\p{L}])(?:(?i:resident[ei]|domiciliat[oaie]|abitante|dimorante|studio)|"
    rf"{PROPERTY_CUE.pattern})\b(?!\s+ex\s+(?:lege|art))"
    rf"{_ADDRESS_GAP}{{0,100}}?(?<![\p{{L}}.\d])"
    rf"({STREET_ADDRESS}|{FOREIGN_STREET_ADDRESS})")

#: An address alone on its line: a letterhead, a signature block, an addressee block
#: ("Spett.le⏎Sig. X⏎Via Lorenteggio, 157⏎20146 MILANO"). The line holds the street,
#: and at most a dash or comma, the CAP and the town. A block that names a public body
#: or a company is theirs, and the caller keeps it.
INDIRIZZO_RIGA = re.compile(
    rf"^[^\S\n]*({STREET_ADDRESS}|{FOREIGN_STREET_ADDRESS})"
    r"(?=[^\S\n]*(?:[,–\-][^\S\n]*\d{5}(?!\d)[^\n]*)?$)", re.M)

#: The notarial deed's opening: "in Treviso, Via Indipendenza n. 7, nel mio studio".
INDIRIZZO_STUDIO_DOPO = re.compile(
    rf"({STREET_ADDRESS})(?=[^\S\n]*,?[^\S\n]*(?i:nel|presso\s+il)\s+"
    r"(?i:mio|suo|proprio)\s+studio)")

#: A birthplace or residence town, read only in its biographic slot: "nato a Stia",
#: "nato il 3.4.1960 a Stia", "residente a Pratovecchio". The capture runs to five words
#: and the caller keeps its longest prefix that is an ISTAT comune, so "Stia il 3 aprile"
#: gives "Stia", while a country ("nato in Romania") or a street ("residente in Via Roma
#: 12") gives nothing. Court seats and other mentions of a town are not slots and stay.
#: A foreign birthplace is no comune, but is followed by its country in brackets ("nato
#: a Wenzhou (Repubblica Popolare Cinese)"): group 2 captures the bracket.
LUOGO_BIOGRAFICO = re.compile(
    r"(?<![\p{L}])(?i:nat[oa](?:/[ao])?(?:\s+il\s+[\d./\-]+)?|residente|dimorante)\s+"
    r"(?i:a|ad|in)\s+"
    r"(\p{Lu}[\p{L}'’\-]*(?:[^\S\n]+[\p{L}'’\-]+){0,4})(?:[^\S\n]*\(([^()\n]{3,40})\))?")

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
    # A minute lists the panel the same way, with a title: "Giudice: avv. Biagio
    # Stomeo", "Presidente: dott. Ettore Mangialardo".
    re.compile(rf"\b(?i:presidente|relatore|estensore|giudice)"
               rf"[^\S\r\n]*:[^\S\r\n]*"
               rf"(?:(?i:dott\.?(?:ssa)?|dr\.?(?:ssa)?|avv\.|prof\.(?:ssa)?)[^\S\r\n]*)?"
               rf"({FULL_NAME})"
               rf"(?=[^\S\r\n]*(?:$|{HEADER_FIELD}))", re.M),
    # Abbreviated roles in a heading or a citation: "R.G. n. 4512/2025 – G.I. dott.ssa
    # Maria Luisa Cavazzuti" (giudice istruttore), "(Pres. ed Est. dott. Aurelio
    # Bortolami)", "Rel. dott. X". "G.I." is matched in capitals only.
    re.compile(rf"(?<![\p{{L}}.])(?:G\.[^\S\n]?I\.|(?i:pres\.|est\.|rel\.)"
               rf"(?:[^\S\n]+(?i:ed?)[^\S\n]+(?i:est\.|rel\.))?)[^\S\n]+"
               rf"(?:(?i:dott\.?(?:ssa)?|dr\.?(?:ssa)?|avv\.|prof\.(?:ssa)?)[^\S\n]*)?"
               rf"({FULL_NAME})"),
    # "dal Consigliere CHIECA Danilo" / "dal consigliere dott. Alberto Crivelli"
    re.compile(rf"(?i:d(?:al|a|el)\s+(?:{JUDICIAL_ROLE})\s+"
               rf"(?:dott\.?(?:ssa)?\s+|avv\.?\s+)?)({FULL_NAME})"),
    # "il consigliere\nrelatore Arcangelo Monteleone" — this narrow form covers a
    # wrapped secondary role without treating every role word in running text as a
    # new bench declaration.
    re.compile(rf"(?i:(?:il|la)\s+)?(?i:consiglier[ea])\s+"
               rf"(?i:relatore|estensore)\s+"
               rf"(?:(?i:dott\.?(?:ssa)?|dr\.?(?:ssa)?|avv\.)\s*)?({FULL_NAME})"),
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
    r"azienda\s+(?:ospedaliera|sanitaria|unit[àa])|a\.?s\.?l\.?|equitalia|riscossione|ader|"
    # health authorities by acronym ("Asur Marche Area Vasta n. 1", "ASP di Catania");
    # word-bounded, so the surname Aspesi is not one
    r"(?:asur|asp|ausl|usl|ulss|asst|ats|aou|irccs)\b|area\s+vasta|"
    r"presidenza|consiglio|procura|pretura|tribunale|corte|commissione\s+tributaria|"
    r"prefettura|questura|camera\s+di\s+commercio|poste\s+italiane|ferrovie|"
    r"direzione\s+(?:provinciale|regionale|centrale)|ufficio|ente|croce\s+rossa|"
    r"guardia\s+di\s+finanza|polizia|carabinieri|repubblica|stato|governo|senato|"
    r"parlamento|demanio|dogan|monopoli|finanz|erario|tesoro|assessorat|"
    r"soprintendenz|motorizzazione|ispettorat|sovrintendenz|"
    r"fallimento|curatela|condominio|parrocchia|diocesi|catast[oa]|"
    # bodies that stand after "contro" in administrative headings: "Autorità Garante della
    # Concorrenza e del Mercato", "Parco Regionale dei Castelli Romani", "Unione dei Comuni"
    # and its CUC; word-bounded, so the surname Cucchi is not one
    r"autorit[àa]|parco\s+(?:regionale|nazionale|naturale)|unione\s+(?:dei\s+)?comuni|cuc\b)")
# NOTE: leading \b only. A trailing \b silently disabled every *prefix* alternative —
# "universit" no longer matched "UNIVERSITARIA", so "AZIENDA OSPEDALIERA UNIVERSITARIA
# FEDERICO II" was cut into the "person" FEDERICO II. Over-matching is safe here because
# this is a rejection rule for candidates, not a shield over spans of text.

#: Street and place prefixes. An address in a party block is an elective domicile, not
#: a person: "VIA CESARE BECCARIA" and "PIAZZA BENEDETTO CAIROLI" were both seeded as
#: parties and pseudonymized out of the document.
STREET_HEAD = re.compile(
    r"^(?i:via|viale|v\.le|vle|piazza|p\.zza|piazzale|piazzetta|largo|corso|c\.so|vicolo|"
    r"strada|stradone|str\.|lungotevere|lungomare|lungarno|località|loc\.|frazione|fraz\.|"
    r"contrada|borgo|riviera|salita|calle|campo|traversa|circonvallazione)\b")

#: A street word or a saint right before a name: the name is the street's, the
#: church's or the town's, not a person's ("Viale Pietro Pietramellara", "Via Ippolito
#: Nievo", "San Giorgio"). Searched up to the start of a candidate.
NAMED_PLACE_BEFORE = re.compile(
    rf"(?<![\p{{L}}])(?:(?i:{STREET_TYPE})[^\S\n]+"
    r"(?:(?i:d(?:i|el|ella|ello|ei|egli|elle)\b|dell['’])[^\S\n]*)?"
    r"|(?i:san|santo|santa|ss\.|s\.)[^\S\n]+|(?i:sant)['’][^\S\n]*)$")

#: Head words of organisations that are not public bodies but are not people either.
#: A candidate containing one of these is a company or an association, never a person,
#: whatever its capitalisation looks like.
ORG_HEAD = re.compile(
    r"\b(?i:banc[ao]|banche|cassa|credito|cooperativa|coop|consorzio|società|societa|"
    r"associazione|fondazione|assicurazion[ei]|autostrade|immobiliare|costruzioni|"
    r"impresa|ditta|studio|segreteria|holding|group|gruppo|s\.?p\.?a|s\.?r\.?l|"
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
segretario
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
#: Items may wrap onto the next line, but a list does not run on past a blank line:
#: "Avv. Paolo Righetti,⏎⏎Caro Paolo," made the salutation a second counsel.
COUNSEL_LIST = re.compile(
    rf"{COUNSEL_CUE}\s+"
    rf"({FULL_NAME}(?:{SEP_NL},{SEP_NL}{FULL_NAME})*"
    rf"(?:{SEP_NL},?{SEP_NL}(?i:ed?){SEP_NL1}{FULL_NAME})?)")

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
TITLE_CUE = (r"(?i:dott\.(?:ssa)?|dr\.(?:ssa)?|sig\.(?:ra)?|signor(?:a)?|ing\.|"
             r"prof\.(?:ssa)?|geom\.|arch\.|rag\.|not(?:aio|\.))")
TITOLO = re.compile(rf"{TITLE_CUE}\s*({FULL_NAME})")

#: A surname alone after a courtesy title, for documents that never give the full name:
#: "il sig. Malaspina". As with COUNSEL_SOLO, the common-word guard downstream is what
#: makes one token safe. "dott." and "prof." are left out: judges carry them, and a
#: judge named by surname alone has no judicial anchor to protect them.
#: SURNAME_AFTER is shared with PARTY_ROLE_SOLO: the token must not be a title itself
#: ("il ricorrente Prof. Rossi"), another abbreviation ("dal ricorrente Prot. n. 1234")
#: or open a longer name, which TITOLO and PARTY_ROLE read.
SURNAME_AFTER = (rf"(?!{TITLE_CUE}|{COUNSEL_CUE})({NAME_TOKEN})"
                 rf"(?![\p{{L}}'’]|{SEP}\p{{Lu}}|\.\s*[\p{{Ll}}\d])")
TITOLO_SOLO = re.compile(
    rf"(?<![\p{{L}}])(?i:sig\.(?:ra)?|signor(?:a)?|ing\.|geom\.|arch\.|rag\.)\s*"
    rf"{SURNAME_AFTER}")

#: Name immediately followed by biographic or fiscal detail, or by the "rappresentato e
#: difeso" that follows a party named in a heading. The separator tolerates a
#: line break and an adverb ("CAVALCANTI SERAFINA\n, ivi residente"), which is how these
#: clauses wrap in converted court text — but it must be **at least one real character**
#: (whitespace or a comma). Allow a zero-width gap and the cue `nat[oa]\b` matches the
#: literal tail of any surname ending in "-nato": "Ornella Trevisanato" reads as the
#: name "Ornella Trevisa" followed by its own cue, and four-fifths of a surname is
#: pseudonymized out of the document. "domiciliata ex lege" is not a person's domicile but
#: the Avvocatura dello Stato's, and follows a place: "…dello Stato di Reggio Calabria,
#: domiciliata ex lege" made the court's own seat a person.
#: A bare name with its own partita IVA is a sole trader, who is a person: "DI BENEDETTO
#: OSVALDO - P.IVA 02956140374". A company keeps its legal form before the P.IVA and is
#: refused downstream.
BIOGRAFICO = re.compile(
    rf"(?<![\p{{L}}])({FULL_NAME})(?:\s*,\s*|\s*[-–]\s*|\s+)"
    rf"(?:(?i:ivi|già|quivi|attualmente)\s+)?"
    rf"(?i:nat[oa]\b|residente\b|domiciliat[oa]\b(?!\s+ex\s+lege)|dimorante\b|c\.?f\.?\b|"
    rf"codice\s+fiscale\b|p\.?\s?iva\b|partita\s+iva\b|in\s+proprio\b|quale\s+erede\b|"
    rf"in\s+qualità\s+di\b|rappresentat[oaie]\s+e\s+difes[oaie]\b)")

#: Name adjacent to a codice fiscale — the strongest anchor there is.
CF_ADIACENTE = re.compile(
    rf"({FULL_NAME_NL})\s*[(\[]?\s*"
    rf"(?:(?i:c\.?f\.?|codice\s+fiscale)[\s:.]*)?"
    rf"([A-Z]{{6}}\d{{2}}[ABCDEHLMPRST](?:[0-6]\d|7[01])[A-Z]\d{{3}}[A-Z])\b")

#: Digital-signature block left in converted PDFs.
PKI_FIRMA = re.compile(rf"(?i:firmato\s+da)\s*:\s*({FULL_NAME_NL})\s+(?i:emesso)")

#: The display name of an e-mail header: "Mittente: Giorgia Esposito <g.esposito@…>",
#: "From: francesca granfione <…>". Only on a header line (From, To, Cc, Da, A,
#: Mittente, Destinatario), where it may be typed in lower case.
EMAIL_DISPLAY_NAME = re.compile(
    r"^[^\S\n]*(?i:from|to|cc|da|a|mittente|destinatari[oa]|inviato\s+da)[^\S\n]*:[^\S\n]*"
    r"(\p{L}[\p{L}'’\-]+(?:[^\S\n]+\p{L}[\p{L}'’\-]+){1,3})[^\S\n]*<[^<>\s]+@", re.M)

#: A relative named by kinship, as family members usually are, by first name alone:
#: "il figlio minore Tommaso", "suo marito Jacopo", "mio figlio gabriele", "my brother
#: Jens". The caller accepts a lower-case or common-word name only if it is a listed
#: first name.
PARENTELA = re.compile(
    r"(?<![\p{L}])(?i:figli[oa]|fratello|sorella|marito|moglie|nipote|cugin[oa]|"
    r"my[^\S\n]+(?:brother|sister|son|daughter|husband|wife))"
    r"(?:[^\S\n]+(?i:minore|minorenne|maggiore|primogenit[oa]))?[^\S\n]+"
    r"(\p{L}[\p{L}'’]+(?:[^\S\n]+\p{Lu}[\p{L}'’]+){0,2})(?![\p{L}'’])")

#: A letter's salutations: "Caro Paolo,", "Gentile Marta," at the top; "Un caro
#: saluto,⏎Luca" or "grazie, francesca" at the bottom. The name must be a listed first
#: name, which the caller checks; a title after the salutation ("Gentile Sig.ra X") is
#: left to TITOLO.
SALUTO = re.compile(
    rf"(?<![\p{{L}}])(?i:car[oa]|carissim[oa]|gentil(?:e|issim[oa])|ciao|dear|hi)[^\S\n]+"
    rf"(?!{TITLE_CUE}|{COUNSEL_CUE})(\p{{Lu}}[\p{{L}}'’]+)[^\S\n]*[,!:]"
    rf"|(?i:saluti|salutoni|un[^\S\n]+(?:caro[^\S\n]+)?saluto|cordialmente|un[^\S\n]+abbraccio|"
    rf"a[^\S\n]+presto|grazie|regards|best)[^\S\n]*[,!.]?"
    rf"(?:[^\S\n]*\n(?:[^\S\n]*\n)?[^\S\n]*|[^\S\n]+)(\p{{L}}[\p{{L}}'’]+)[^\S\n]*$", re.M)

#: Party roles used to label a seed, and to find one in prose.
PARTY_ROLE_WORD = (r"(?i:ricorrent[ei]|resistent[ei]|controricorrent[ei]|"
                   r"appellant[ei]|appellat[oi]|intimat[oi]|opponent[ei]|opposto|attor[ei]|"
                   r"convenut[oi]|contribuent[ei]|istant[ei])")
PARTY_ROLE = re.compile(rf"(?i:il\s+|la\s+|i\s+|le\s+)?{PARTY_ROLE_WORD}[:\s,]+({FULL_NAME})")
#: …and a surname alone after one: "il ricorrente Malaspina".
PARTY_ROLE_SOLO = re.compile(rf"(?<![\p{{L}}]){PARTY_ROLE_WORD}[:\s,]+{SURNAME_AFTER}")

#: The commonest way an Italian decision names a party: "proposto da <Name>, …".
#: Cassazione writes it in the ALL-CAPS party block, but the administrative and civil
#: courts write it in ordinary case inline, which the block scan never sees.
#: Institutions and companies following the same cue are refused downstream.
APPLICANT_CUE = (r"(?i:proposto\s+da(?:l(?:la)?|i|gli|lle)?|ricorso\s+di|promoss[oa]\s+da)"
                 r"(?:\s+(?i:i\s+)?(?i:signori|sigg?\.\s?(?:ri|re)|sig\.(?:ra)?))?")
#: …and the other side: "nei confronti di X" in running text, or a heading that ends its
#: line with the parties below it: the administrative courts' "nei confronti", or the
#: "contro" before the respondents. A "contro" inside a line is prose ("ricorso contro la
#: sentenza") and stays out.
COUNTERPARTY_CUE = (r"(?i:nei\s+confronti(?:\s+di\b|(?=[^\S\n]*\n))|"
                    r"\bcontro(?=[^\S\n]*:?[^\S\n]*\n))")
PROPOSTO_DA = re.compile(rf"{APPLICANT_CUE}\s*:?\s*({FULL_NAME})")
NEI_CONFRONTI = re.compile(rf"{COUNTERPARTY_CUE}\s*:?\s*({FULL_NAME})")

#: A *list* of parties at one cue. Mass appeals name dozens of applicants, and the
#: counter-interested parties of a public competition come in lists as well:
#:   "proposto da Giulia Balestri, Lucia Surpo, Maurita Perfetti e Anna Vezzi, …"
#: As with counsel, the single-name anchors above only ever see the first of them.
#: Party lists are also written with semicolons: "nei confronti di A; B; C;".
PARTY_LIST = re.compile(
    rf"(?:{APPLICANT_CUE}|{COUNTERPARTY_CUE})\s*:?\s*"
    rf"({FULL_NAME}(?:{SEP_NL}[,;]{SEP_NL}{FULL_NAME})*"
    rf"(?:{SEP_NL}[,;]?{SEP_NL}(?i:ed?){SEP_NL1}{FULL_NAME})?)")

#: What makes a party cue's capture part of an organisation rather than a person: a legal
#: form right after it ("Rosalinda Pizzigoni S.r.l."), or a capitalised word and a
#: preposition right before it ("Comune di Fonte Nuova, rappresentato e difeso",
#: "Istituto Nazionale della Previdenza Sociale, rappresentato e difeso").
ORG_SUFFIX_AFTER = re.compile(rf"[^\S\n]*(?:{COMPANY_SUFFIX})(?![\p{{L}}])", re.I)
ORG_NAME_BEFORE = re.compile(
    r"[\p{Lu}][\p{L}'’.]*[^\S\n]+(?i:di|del|della|dello|dei|degli|delle|dell['’]|d['’])"
    r"[^\S\n]*$")

#: Civil-law capacities that introduce a named individual in the body of a decision:
#: "all'altro socio TAGLIAFERRI NICODEMO", "la ditta di PICCININI GUALTIERO". A sole
#: trader and a law firm named after its lawyer are people too: "ditta individuale HU
#: XIAOMING", "studio legale Mirandolina Zangheratti".
QUALIFICA = re.compile(
    rf"(?<![\p{{L}}])(?i:soci[oa]|amministrator[ei]|titolar[ei]|legale\s+rappresentante|"
    rf"erede|eredi|coniuge|curator[ei]|liquidator[ei]|tutor[ei]|"
    rf"(?:s\.?a\.?s\.?|s\.?n\.?c\.?|ditta|impresa|società)\s+di|"
    rf"(?:ditta|impresa)\s+individuale(?:\s+di)?|studio\s+legale)"
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
