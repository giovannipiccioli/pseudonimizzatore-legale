"""Fail if any real person's name survived into the committed fixtures.

The fixtures are built from real court documents, so this is the gate that keeps real
personal data out of the repository. It flags every person-shaped run of capitalised
words that is neither in the invented namebank nor ordinary corpus vocabulary, and every
codice fiscale or personal e-mail address that is not an invented one.

    python check_fixtures.py          # exit 1 on any suspect name

Expect a handful of legitimate hits (foreign court names, place names the common-word
list does not cover); add those to ALLOWED after checking them by eye.
"""
import sys
from pathlib import Path

import regex as re

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))
import namebank as NB
from pseudonimizzatore_legale.seeds import common_words

FIXTURES = HERE.parent / "corpus"

COMMON = common_words()

#: Reviewed by hand: place names, institutions and foreign-court wording that look like
#: personal names to the heuristic but are not.
ALLOWED = {
    "santa maria capua vetere", "torre annunziata", "reggio nell'emilia",
    "corte d'appello", "cour d'appel", "bruxelles", "belgio", "campania",
    "emilia-romagna", "federico ii", "guardia di finanza", "croce rossa",
    "repubblica italiana", "popolo italiano", "consiglio di stato", "unione europea",
    "commissione europea", "corte dei conti", "regno unito", "stati uniti",
    "santa maria", "capua vetere", "carpeneto", "alessandria", "avellino",
    "sant'agata", "san giorgio", "san giovanni", "lazio", "campobasso",
    "dei monopoli", "delle dogane", "premi inail", "maria capua vetere",
    "societa cooperativa", "società cooperativa", "capua vetere",
    "secondo grado dell'emilia", "primo grado", "secondo grado",
    "degli studi di", "studi di napoli",
    "corso garibaldi", "via roma", "corso italia", "piazza garibaldi",
    "vittorio emanuele", "cesare beccaria", "dei portoghesi",
    "studi napoli federico", "infortuni sul", "l'assicurazione contro gli",
    "marchés financiers", "services et des", "azienda ospedaliera universitaria",
    "questura agrigento", "universita' degli studi", "reggio emilia",
    "servizi tecnici", "ambiti territoriali provinciali", "garanzia inps",
}

INVENTED = set()
for _s, _f in NB.PEOPLE + NB.COUNSEL + NB.JUDGES:
    INVENTED |= {t.lower() for t in _s.split()} | {t.lower() for t in _f.split()}
for _c in NB.COMPANIES:
    INVENTED |= {t.lower() for t in _c.split()}
SURNAMES = {_s.lower().replace(" ", "") for _s, _f in NB.PEOPLE + NB.COUNSEL + NB.JUDGES}

TOK = r"(?:[\p{Lu}][\p{L}'’]*[\p{L}]['’]?|[Dd]['’][\p{Lu}][\p{L}'’]*)"
NAME = re.compile(rf"(?<![\p{{L}}'’])({TOK}(?:[^\S\r\n]+{TOK}){{1,2}})(?![\p{{L}}'’])")
CUE = re.compile(r"(?:Presidente|Relatore|[Cc]onsiglier|Cons\.|[Gg]iudice|avv\.|"
                 r"avvocat|AVVOCATO|difes|rappresent|proposto da|contro|sig\.|dott\.|"
                 r"nato a|monocratic|[Pp]rocuratore)")


#: A name that directly follows "Word, " is a member of a list. Long lists of parties
#: (mass appeals) put most names far from any cue, so without this the check never saw
#: them; flagging too much here only drops a fixture, flagging too little leaks a name.
LIST_MEMBER = re.compile(r"[\p{Lu}][\p{L}'’.]+\s*[,;]\s*$")
#: Cues *after* a name ("X, rappresentata e difesa"), and the judge a monocratic decree
#: prints alone under its heading — both shapes a real name reached a fixture through.
AFTER_CUE = re.compile(r"^[\s,]*(?i:rappresentat|difes|assistit|nat[oaie]\s|residente|in\s+proprio)")
UNDER_HEADING = re.compile(r"(?:SENTENZA|ORDINANZA|DECRETO)[^\S\n]*\n\s*$")

#: Words the de-identifier treats as places but that are also names or surnames
#: ("Annunziata D'Amelia", "Maria Filomena Puglia"). They must not spare a run from this
#: check — genuine place names belong in ALLOWED, reviewed.
PLACE_OR_NAME = re.compile(
    r"\b(?i:santa|santo|san|vetere|annunziata|capua|grado|emilia|romagna|lombardia|"
    r"veneto|piemonte|toscana|liguria|puglia|calabria|sicilia|sardegna|umbria|marche|"
    r"abruzzo|molise|basilicata|friuli|trentino|valle|aosta|lazio|campania)\b")

#: Streets and squares carry capitalised proper nouns but are not people.
STREET = re.compile(r"^(?i:via|viale|v\.le|corso|c\.so|piazza|p\.zza|largo|vicolo|"
                    r"strada|località|loc\.|frazione|fraz\.|contrada|borgo|lungo)\b")

#: A name is not the only identifier. Real codici fiscali and a counsel's e-mail address
#: reached committed fixtures beside names that had been replaced, because nothing
#: looked for them.
CODICE_FISCALE = re.compile(
    r"(?<![A-Za-z0-9])[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z](?![A-Za-z0-9])")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
#: Offices, not people. An address whose local part carries an invented surname is the
#: builder's own rewrite ("s.pizzigoni@…") and passes too.
INSTITUTIONAL_MAIL = re.compile(r"agenziaentrate|inps|inail|avvocaturastato|giustizia|"
                                r"\.gov\.|comune\.|regione\.")


def suspects(text):
    from deidentify import NOT_A_PERSON        # institutions, regions, court wording
    out = {}
    for m in NAME.finditer(text):
        name = re.sub(r"\s+", " ", m.group(1))
        low = name.lower()
        # Only a run that *starts* like an institution is spared: in "Alessia L'Erario"
        # and "Maria Filomena Puglia" the institution or place word is a surname.
        if low in ALLOWED or STREET.match(name) or \
                NOT_A_PERSON.match(PLACE_OR_NAME.sub(" ", name).strip()):
            continue
        # a fragment of a longer institution name: look at what precedes it. The cue may
        # carry a colon — "SENTENZA sul ricorso … proposto da: SPALLONE DARIO" was
        # waved through as a fragment of "SENTENZA".
        lead = text[max(0, m.start() - 60):m.start()]
        if NOT_A_PERSON.search(lead) and not re.search(
                r"(?i:avv\.|avvocat|dott\.|sig\.|nato a|proposto da)\s*:?\s*$", lead):
            continue
        toks = low.split()
        if all(t in INVENTED or t in COMMON or t in ALLOWED for t in toks):
            continue
        if not any(len(t) >= 4 and t not in COMMON for t in toks):
            continue
        ctx = text[max(0, m.start() - 80):m.start()]
        if (CUE.search(ctx) or LIST_MEMBER.search(ctx) or UNDER_HEADING.search(ctx)
                or AFTER_CUE.match(text[m.end():m.end() + 30])):
            out.setdefault(name, ctx[-50:].replace("\n", " ").strip())
    for cf in CODICE_FISCALE.findall(text):
        if cf not in NB.CODICI_FISCALI:
            out.setdefault(cf, "(codice fiscale)")
    for mail in EMAIL.findall(text):
        local, domain = mail.lower().split("@", 1)
        if (mail not in NB.EMAILS + NB.PEC and not INSTITUTIONAL_MAIL.search(domain)
                and not any(s in local for s in SURNAMES)):
            out.setdefault(mail, "(e-mail)")
    return out


def main():
    bad = 0
    for path in sorted(FIXTURES.rglob("*.txt")):
        found = suspects(path.read_text(encoding="utf-8"))
        if found:
            bad += len(found)
            print(f"\n{path.relative_to(FIXTURES)}")
            for name, ctx in sorted(found.items()):
                print(f"   {name:34s} after: …{ctx}")
    total = len(list(FIXTURES.rglob('*.txt')))
    if bad:
        print(f"\n{bad} suspect name(s) across {total} fixtures — review each, then "
              f"either fix build_fixtures.py or add it to ALLOWED.")
        return 1
    print(f"clean: no real names found across {total} fixtures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
