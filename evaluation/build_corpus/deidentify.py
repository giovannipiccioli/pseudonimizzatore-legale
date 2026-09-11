"""Replace every real person in a source document with an invented identity.

Used only to build fixtures — it is deliberately *not* the library. Its job is the
opposite of anonymization: it must find every real name so none reaches the repository,
and it may be as aggressive and as slow as it likes. Correctness is checked by
`check_fixtures.py`, which fails if any person-shaped name outside the namebank survives.

Names are clustered by their distinctive token, so "Vincenzo Di Maio" and a later bare
"Di Maio" become the same invented person and every surface form follows. Each cluster
is classified by the cue in front of its first mention: judicial cues make it a name the
fixture expects to *survive*, everything else a name the fixture expects to be *removed*.
"""
from dataclasses import dataclass, field

import regex as re

import namebank as NB
from pseudonimizzatore_legale.seeds import common_words

COMMON = common_words()

#: A person-shaped run, up to 6 tokens, allowing D'ALOISIO, DE ROSE, de la Tour, Bellè.
#: The run must be generous: capturing only the first four tokens of
#: "JEAN RICHARD DE LA TOUR" replaced the head and left "TOUR" stranded in the fixture.
_TOK = r"(?:[\p{Lu}][\p{L}'’]*[\p{L}]['’]?|[Dd]['’][\p{Lu}][\p{L}'’]*)"
_PARTICLE = r"(?:de|di|da|del|della|dello|dei|degli|delle|la|le|lo|van|von|der|den|y)"
NAME = re.compile(
    rf"(?<![\p{{L}}'’])({_TOK}(?:[^\S\r\n]+(?:{_TOK}|{_PARTICLE})){{1,5}})(?![\p{{L}}'’])")

#: Legal-form suffix — a run carrying one is a company, and companies are replaced
#: wholesale rather than treated as people.
COMPANY = re.compile(
    rf"(?<![\p{{L}}])((?:{_TOK}[^\S\r\n]+){{1,4}}"
    rf"(?i:s\.?\s?r\.?\s?l\.?|s\.?\s?p\.?\s?a\.?|s\.?\s?n\.?\s?c\.?|s\.?\s?a\.?\s?s\.?|"
    rf"soc\.?\s?coop\.?|onlus))(?![\p{{L}}])")

#: Cues that mark the *preceding* name as a member of the bench or the prosecution.
_ROLE = (r"Presidente(?:\s+Titolare)?|Relatore|Estensore|[Cc]onsiglier[ei]|Cons\.|"
         r"(?:[Pp]rimo\s+)?[Rr]eferendari[oa]|"
         r"[Gg]iudice|monocratic[oa]|AVVOCATO\s+GENERALE|[Ss]ostituto\s+[Pp]rocuratore|"
         r"[Pp]rocuratore\s+[Gg]enerale|\bP\.?\s?G\.?\b|[Cc]ancellier[ei]|"
         # "composta dai sigg.ri magistrati: dott. X" — without this the bench was
         # labelled as parties, and the gold then demanded the judges' removal.
         r"[Mm]agistrat[oi]|[Cc]ollegio|[Cc]omponente")
# Case-insensitive, like PERSON_CUE, which carries the same role words: a lowercase
# "il consigliere relatore X" or "il cons. X" was a person cue but not a judge cue, so the
# gold called the judge a party.
JUDGE_CUE = re.compile(rf"(?:{_ROLE})[\s:,.\-–]*$", re.I)
#: …and the same cues *after* the name, which is how BDGT and CGT headers are written
#: ("MAROZZO ANTONIO, Presidente e Relatore").
#: Tabular headers put the role after the name, separated by runs of spaces and often
#: by leftover masking: "dott. Adelasia Scaramuzza  F___  PRESIDENTE". Without the slack
#: the whole bench was labelled as parties and the gold demanded the judges' removal.
JUDGE_CUE_AFTER = re.compile(rf"^[^\n]{{0,8}}?[\s,.\-–]*(?:e\s+)?(?:{_ROLE})")
# A role may precede a courtesy title ("Procuratore generale, Dott. X"), so the
# end-anchored cue above cannot see it immediately beside the name.
JUDGE_CUE_CONTEXT = re.compile(
    r"(?i:\b(?:procuratore\s+generale|sostituto\s+procuratore)\b[^\n]{0,35}$)"
)
#: The reporting judge is introduced by the role, a clause, then a title — "Relatore
#: nell'udienza pubblica del giorno 4 ottobre 2023 il dott. X", "il consigliere avv. X".
#: Mirrors the engine's role-plus-title anchor; without it the only cue next to the name
#: was the title, and the gold called the relatore a party.
JUDGE_CUE_TITLE = re.compile(
    r"(?i:\b(?:relatore|estensore|presidente|consiglier[ea]|referendari[oa]|giudice)\b"
    r"[^\n]{0,90}?\b(?:dott\.?(?:ssa)?|dr\.?(?:ssa)?|avv\.)\s*$)")

#: Cues that mark a run as a *person* at all. A cluster with no cue anywhere is left
#: untouched: without this gate the builder rewrote "Comune di Carpeneto" into "Comune
#: di Sanseverino" and "Agenzia delle Entrate" into "Agenzia delle Ermenegildo
#: Trentacoste", quietly destroying the documents it was supposed to prepare.
PERSON_CUE = re.compile(
    rf"(?:{_ROLE}|avv\.ti|avv\.|avvocat[oi]|difensor|difes[oa]|rappresentat[oa]|"
    r"assistit[oa]|"
    # `contro` on its own line opens the respondent block of every Italian decision, and
    # without it the respondent was left in clear — a real party name reached a committed
    # fixture. Institutions and companies that follow it are filtered separately.
    r"proposto\s+da|nei\s+confronti(?:\s+di)?|\bcontro\b|\bavverso\b|"
    # "presso lo studio Flaviano Lai" names counsel as surely as "studio legale" does
    r"\bstudio(?:\s+legale)?|ad\s+(?:opponendum|adiuvandum)|\bminori\b|"
    r"sig\.?r?a?\.?|signor[ae]?|dott\.(?:ssa)?|"
    r"nat[oa]\s+a|residente|domiciliat[oa]|ricorrent|resistent|appellant|appellat|"
    r"intimat|controricorrent|imputat|contribuent|militare|erede|paziente|"
    r"C\.?T\.?U\.?|perito|notaio|prof\.|ing\.|geom\.|rag\.)"
    # opening quotes too: "proposto da:\n\n“Alessandra Palese”" stayed real without them
    r"[\s:,.\-–'\"“«]*$",
    re.I)
PERSON_CUE_ANY = re.compile(PERSON_CUE.pattern.rstrip("$"), re.I)
#: A courtesy title or a role word says that a person is named, not which side they are
#: on — the runtime treats a title as neutral too. Only the rest of PERSON_CUE (party,
#: counsel and biographical cues, or a list one of them opens) is private-role evidence
#: for the conflict rule: counting "dott." made a judge also written "dott. X", or listed
#: in a bench after "dott.", a conflict, and the gold removed the judge.
NEUTRAL_CUE = re.compile(
    rf"(?:{_ROLE}|dott\.(?:ssa)?|prof\.|ing\.|geom\.|rag\.)[\s:,.\-–'\"“«]*$", re.I)
#: …and the same kind of cue *after* the name: "De Martino Giuseppina, rappresentata e
#: difesa", "Mario Rossi, nato a". A party introduced by an unusual phrase ("ad
#: opponendum:") is still followed by one of these.
PERSON_CUE_AFTER = re.compile(
    r"^[\s,\"”»]*(?i:rappresentat[oaie]|difes[oaie]|assistit[oaie]|nat[oaie]\s+(?:a|il)\b|"
    r"residente|in\s+proprio|in\s+qualità)")
#: A monocratic decree prints its judge alone on the line under the heading:
#: "ha pronunciato il presente\n\nDECRETO\n\nCarlo Testori\n\nsul ricorso…".
JUDGE_UNDER_HEADING = re.compile(r"(?:SENTENZA|ORDINANZA|DECRETO)[^\S\n]*\n\s*$")

#: Words that make a capitalised run an organisation or a place, never a person here.
NOT_A_PERSON = re.compile(
    r"\b(?i:agenzi|minister|inps|inail|istitut|avvocatura|comune|region|provinc|"
    r"universit|azienda|equitalia|riscossione|presidenza|consiglio|procura|tribunal|"
    r"corte|commission|prefettur|questur|camera|poste|ferrovie|direzion|ufficio|ente|"
    r"croce|guardia|polizia|carabinier|repubblica|stato|govern|senato|parlamento|"
    r"demanio|dogan|monopoli|finanz|erario|tesoro|assessorat|banca|banco|cassa|credito|"
    r"cooperativ|consorzi|societ|associazion|fondazion|assicurazion|autostrad|"
    r"s\.?p\.?a|s\.?r\.?l|s\.?n\.?c|s\.?a\.?s|onlus|"
    r"asur|asp|ausl|usl|ulss|asst|irccs|area\s+vasta|"
    r"sezione|udienza|camera|ricorso|sentenza|ordinanza|decreto|appello|cassazione|"
    r"giustizia|popolo|italiano|italiana|nome|fatto|diritto|motivi|causa|processo|"
    r"santa|santo|san|vetere|annunziata|capua|grado|"
    # Italian regions: "SECONDO GRADO DELL'EMILIA-ROMAGNA" was being read as a person
    r"emilia|romagna|lombardia|veneto|piemonte|toscana|liguria|puglia|calabria|"
    r"sicilia|sardegna|umbria|marche|abruzzo|molise|basilicata|friuli|trentino|"
    r"valle|aosta|lazio|campania)\b")


#: Between a cue and a later name in the same list there may only be other names,
#: commas and "e"/"ed" — "avvocati A B, C D, E F e G H" cues every one of them.
#: Lists are not typed cleanly: a stray full stop ("…Rossi., Anna …"), a lowercase
#: particle ("Maria de Santis") or counsel's codice fiscale in brackets ("Guido Ciccarelli
#: (C.F. …), Stefano Russo") must not end the list, or every later name stays real.
_LIST_GAP = re.compile(
    r"^[\s,;.]*(?:(?:[\p{Lu}][\p{L}'’.]*|[Dd]['’][\p{Lu}][\p{L}'’]*|\([^()\n]{0,40}\)|"
    r"e|ed|d[aei]|de[il]|dell[aoe']|degli|dei|la|le|lo|,|;|\.)[\s,;.]*)*$")


def _in_name_list(text, pos):
    """The person cue opening the comma-separated list that `pos` continues, or None.

    The look-back covers the current paragraph and the one before it: a mass appeal
    lists dozens of applicants after one "proposto da", often on the next line
    ("proposto da\n\nA, B, C, …"), and a fixed window left the later ones real.
    """
    paragraph = text.rfind("\n\n", 0, pos)
    start = text.rfind("\n\n", 0, paragraph) if paragraph > 0 else 0
    window = text[max(0, pos - 8000, start):pos]
    last = None
    for m in PERSON_CUE_ANY.finditer(window):
        last = m
    if last is None or not _LIST_GAP.match(window[last.end():]):
        return None
    return last.group(0)


#: "composta dai (seguenti) (sigg.ri) magistrati:" opens a bench list where names run
#: one per line, often with a title and blank lines between them, and the role words
#: ("Presidente", "Consigliere") trail one or more names later rather than sitting next
#: to each — the mirror-image gap of `_in_name_list` above. Must match the engine's own
#: `patterns.JUDGE_LIST`, or the gold calls a judge a party wherever the two diverge.
JUDGE_LIST_CUE = re.compile(
    r"(?i:composta\s+da[ilgh]{1,3}\s+(?:seguenti\s+)?(?:sigg\.ri\s+)?magistrat[oi]\s*:?)")
#: Between a bench-list cue and a later name there may only be other names, titles,
#: blank lines and stray punctuation — never prose.
_JUDGE_LIST_GAP = re.compile(
    r"^(?:[\s,;.\-–]*(?:[\p{Lu}][\p{L}'’.]*|dott\.?|dr\.?|ssa)[\s,;.\-–]*)*$", re.I)


#: Mirrors the engine's patterns.JUDGE_LIST_END: the heading or narrative-opening
#: phrase that ends a bench list. Must match, or the builder protects (or fails to
#: protect) a different stretch of text than the engine actually will, and the gold
#: it writes stops describing what the engine does.
_JUDGE_LIST_END = re.compile(
    r"(?i:ha\s+pronunciato|\bSENTENZA\b|\bORDINANZA\b|\bDECRETO\b|"
    r"nel\s+giudizio|promosso\s+da|proposto\s+da|nei\s+confronti\s+di)")


def _in_judge_list(text, pos):
    """True if `pos` continues a bench list opened by JUDGE_LIST_CUE."""
    window = text[max(0, pos - 260):pos]
    last = None
    for m in JUDGE_LIST_CUE.finditer(window):
        last = m
    if last is None:
        return False
    tail = window[last.end():]
    stop = _JUDGE_LIST_END.search(tail)
    if stop:
        return False           # `pos` falls after where the bench list actually ends
    return bool(_JUDGE_LIST_GAP.match(tail))


def _rare(tokens):
    return [t for t in tokens
            if len(t) >= 4 and t.lower() not in COMMON and not re.search(r"\d", t)]


@dataclass
class Cluster:
    key: str
    variants: set = field(default_factory=set)
    judge: bool = False
    private: bool = False
    first: int = 10 ** 9
    cued: bool = False
    tokens: set = field(default_factory=set)


def _collect(text):
    """Group every mention of the same person, however they are spelled.

    Mentions are unioned on *shared rare tokens*, not on a single chosen key. Picking
    "the longest rare token" split "BENATTI ROSSELLA" (longest: ROSSELLA) from the later
    bare "Benatti" into two people, so the header and the body of the same document got
    different invented identities — destroying the very local-consistency case the
    fixture exists to test.
    """
    mentions = []
    for m in NAME.finditer(text):
        name = re.sub(r"\s+", " ", m.group(1)).strip()
        toks = name.split()
        if NOT_A_PERSON.search(name):
            continue
        before = text[max(0, m.start() - 60):m.start()]
        judge = bool(JUDGE_CUE.search(before)
                     or JUDGE_CUE_CONTEXT.search(before)
                     or JUDGE_CUE_TITLE.search(text[max(0, m.start() - 140):m.start()])
                     or JUDGE_CUE_AFTER.match(text[m.end():m.end() + 40])
                     or JUDGE_UNDER_HEADING.search(before)
                     or _in_judge_list(text, m.start()))
        cue = PERSON_CUE.search(before)
        list_cue = _in_name_list(text, m.start())
        after = bool(PERSON_CUE_AFTER.match(text[m.end():m.end() + 40]))
        cued = judge or bool(cue) or after or bool(list_cue)
        private = after or any(c and not NEUTRAL_CUE.search(c)
                               for c in (cue and cue.group(0), list_cue))
        rare = [t.lower() for t in _rare(toks)]
        if not rare or all(t.lower() in COMMON for t in toks):
            # "Ugo De Carlo" has no rare token to cluster on, but a cue still makes it a
            # real person: key it on the whole name rather than leave it in the fixture.
            if not cued:
                continue
            rare = [name.lower()]
        mentions.append((name, rare, m.start(), judge, cued, private))

    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for _, rare, *_ in mentions:
        for t in rare[1:]:
            union(rare[0], t)

    clusters: dict[str, Cluster] = {}
    for name, rare, pos, judge, cued, private in mentions:
        root = find(rare[0])
        c = clusters.setdefault(root, Cluster(key=root))
        c.variants.add(name)
        c.first = min(c.first, pos)
        c.judge = c.judge or judge
        c.private = c.private or (private and not judge)
        c.cued = c.cued or cued
        c.tokens |= set(rare)
    for c in clusters.values():
        c.key = max(c.tokens, key=len)
    # a run nobody ever introduces as a person is a place, a court or a subject heading
    return {k: c for k, c in clusters.items() if c.cued}


def _replace_companies(text, seed):
    """Swap real company names for invented ones before people are looked for.

    Done first because an organisation caught by the person heuristic produces a
    half-replaced mess like "Gervasio Spadaccini Onlus Società Cooperativa".
    """
    seen = {}
    for m in COMPANY.finditer(text):
        name = re.sub(r"\s+", " ", m.group(1)).strip()
        if NOT_A_PERSON.search(re.sub(r"(?i:s\.?\s?r\.?\s?l\.?|s\.?\s?p\.?\s?a\.?|"
                                      r"onlus|soc\.?\s?coop\.?)", "", name)):
            continue                      # a public body, leave it alone
        seen.setdefault(name, NB.COMPANIES[(seed + len(seen)) % len(NB.COMPANIES)])
    for src, dst in sorted(seen.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"(?<![\p{{L}}]){re.escape(src)}(?![\p{{L}}])", dst, text)
    return text


def deidentify(text, seed=0):
    """Return (text, must_remove, must_keep) with every real person replaced."""
    text = _replace_companies(text, seed)
    clusters = sorted(_collect(text).values(), key=lambda c: c.first)
    must_remove, must_keep = [], []
    replacements: list[tuple[str, str]] = []

    j = p = 0

    def pick(bank, i):
        """Next identity whose surname is not already used in this document.

        Reusing one produced self-contradictory gold — "Rocchetti Rocchetti", or a
        surname that is a judge in the header and a party in the body — so the fixture
        asserted both that a string must go and that it must stay.
        """
        for step in range(40):
            s_, f_ = bank(i + step)
            if s_.title() not in text and s_.upper() not in text:
                return s_, f_
        return bank(i)

    for c in clusters:
        if c.judge:
            surname, first = pick(NB.judge, seed + j)
            j += 1
        else:
            surname, first = pick(NB.counsel if p % 2 else NB.person, seed + p)
            p += 1
        # every variant of this person → the invented pair, in the variant's own order
        for v in sorted(c.variants, key=len, reverse=True):
            toks = [t for t in v.split() if t.lower() not in ("la", "il", "lo", "de",
                                                              "di", "del", "della")]
            # one distinctive token → a bare-surname mention; keep it bare, otherwise
            # "La Benatti" would become a full name and the test case would disappear
            if len(toks) <= 1:
                new = surname if v.isupper() else surname.title()
            elif v.isupper():
                new = f"{surname} {first}"
            else:
                new = f"{first.title()} {surname.title()}"
            replacements.append((v, new))
        replacements.append((c.key, surname))          # bare distinctive token
        # If the same extracted identity carries both judicial and private-role
        # evidence, the evaluation follows the runtime's privacy-first conflict rule.
        target = must_keep if c.judge and not c.private else must_remove
        target += [f"{surname} {first}", f"{first.title()} {surname.title()}",
                   surname.title()]

    for src, dst in sorted(replacements, key=lambda r: -len(r[0])):
        pattern = re.compile(rf"(?<![\p{{L}}'’]){re.escape(src)}(?![\p{{L}}'’])", re.I)
        text = pattern.sub(lambda m, d=dst: _match_case(m.group(0), d), text)

    return text, sorted(set(must_remove)), sorted(set(must_keep))


def _match_case(template: str, replacement: str) -> str:
    if template.isupper():
        return replacement.upper()
    if template.islower():
        return replacement.lower()
    return " ".join(w.title() if w.isalpha() or "'" in w else w
                    for w in replacement.split())
