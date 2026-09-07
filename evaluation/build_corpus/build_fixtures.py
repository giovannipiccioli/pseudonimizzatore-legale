"""Build the fixture corpus from the real archives.

Regenerates `evaluation/corpus/`. The generated `.txt` files are committed,
so the test suite runs without access to the archives; this script only needs to run when
adding or refreshing fixtures.

**Every fixture carries invented names**, including those built from Cassazione, which
ships real ones. Two passes do it:

1. sources that are already pseudonymized (BDGT role tags, `-OMISSIS-`, `(OMISSIS)`) get
   their placeholders filled with invented identities — this is what makes the gold
   exact, since we know precisely what we injected;
2. every document then goes through `deidentify`, which finds any remaining real person
   and replaces them cluster by cluster, preserving each surface form.

`check_fixtures.py` fails the build if any person-shaped name outside the namebank
survives.

Source archive locations are read from the ``PSEUDONIMIZZATORE_LEGALE_*_ROOT`` environment
variables documented by ``python build_fixtures.py --help``.
"""
import html
import json
import os
import sys
from pathlib import Path

import regex as re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", ".."))

import namebank as NB
from deidentify import deidentify


def _root(variable: str, child: str = "") -> Path:
    value = os.environ.get(variable)
    base = Path(value).expanduser() if value else Path(".missing-sources") / variable
    return base / child if child else base


CASS = _root("PSEUDONIMIZZATORE_LEGALE_CASSAZIONE_ROOT")
BDGT_ROOT = _root("PSEUDONIMIZZATORE_LEGALE_BDGT_ROOT")
BDGT = BDGT_ROOT / "scraping_bdgt_2025_txt_norm"
CDS_ROOT = _root("PSEUDONIMIZZATORE_LEGALE_GIUSTIZIA_AMMINISTRATIVA_ROOT")
CDS = CDS_ROOT / "2025/html"
CGUE = _root("PSEUDONIMIZZATORE_LEGALE_CGUE_ROOT")
CONTI_ROOT = _root("PSEUDONIMIZZATORE_LEGALE_CORTE_CONTI_ROOT")
CONTI = CONTI_ROOT / "2022/pdf"

OUT = Path(__file__).resolve().parent.parent / "corpus"


# ── helpers ──────────────────────────────────────────────────────────────────

def strip_html(raw):
    # Some giustizia amministrativa exports (TAR first-instance decisions, not the
    # Consiglio di Stato appellate ones) carry an XML metadata preamble ahead of the
    # actual decision — file paths, signing timestamps, a `<firmaEstensore>` field that
    # is genuinely the drafting judge's name. Generic tag-stripping flattens it into
    # text that reads like noise ("U:\DocumentiGA\Magistrati\769 X\ Sentenza 00:00:00
    # Y…") with the one cue that identified Y as a judge (the tag name) discarded. It
    # is not decision prose either way, so it is dropped whole rather than parsed.
    t = re.sub(r"<descrittori>.*?</descrittori>", " ", raw, flags=re.S | re.I)
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>|</p>|</div>|</tr>|</h\d>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t\xa0]+", " ", t)
    t = re.sub(r" ?\n ?", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def pdf_text(path):
    import fitz
    with fitz.open(path) as doc:
        return "\n".join(p.get_text() for p in doc)


def truncate(text, limit):
    if len(text) <= limit:
        return text
    cut = text.rfind("\n", 0, limit)
    return text[: cut if cut > limit // 2 else limit].rstrip() + "\n"


def present(needle, text):
    """Word-boundary containment — the same test the fixture runner applies."""
    return bool(re.search(rf"(?<![\p{{L}}\p{{N}}]){re.escape(needle)}"
                          rf"(?![\p{{L}}\p{{N}}])", text))


def keep_present(text, candidates):
    return sorted({c for c in candidates if present(c, text)})


INSTITUTIONS = [
    "AGENZIA DELLE ENTRATE", "Agenzia delle Entrate", "Ag. Entrate",
    "AGENZIA DELLE DOGANE E DEI MONOPOLI", "Avvocatura Generale dello Stato",
    "AVVOCATURA GENERALE DELLO STATO", "Ministero della Salute",
    "MINISTERO DELLA GIUSTIZIA", "Consiglio di Stato", "Commissione europea",
    "I.N.P.S.", "INPS", "ISTITUTO NAZIONALE DELLA PREVIDENZA SOCIALE",
    "CORTE DEI CONTI", "Guardia di Finanza", "Comune di Carpeneto",
    "AZIENDA OSPEDALIERA UNIVERSITARIA FEDERICO II", "BANCA NAZIONALE DEL LAVORO",
    "UNIVERSITA' DEGLI STUDI DI NAPOLI FEDERICO II", "Università degli Studi di Napoli",
    "Roma", "ROMA", "Napoli", "NAPOLI", "Milano", "Avellino", "Alessandria",
    "ALESSANDRIA", "Firenze", "Bruxelles", "IRPEF", "IMU", "IVA",
]


def write(source, name, body, note, src_label, must_remove, must_keep,
          config=None):
    # Safety net. `deidentify` is a heuristic and will always meet a shape it does not
    # know; rather than grow it a special case per document, any document that still
    # trips the leak checker is simply dropped. Losing a fixture costs nothing — shipping
    # a real party's name would cost a great deal.
    from check_fixtures import suspects
    found = suspects(body)
    if found:
        print(f"  DROP {source}/{name}: real name(s) survived "
              f"{sorted(found)[:3]}")
        return None

    d = OUT / source
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.txt").write_text(body, encoding="utf-8")
    gold = {
        "source": src_label,
        "note": note,
        "config": config or {},
        # A name carrying a legal form is a company, and companies are kept by default
        # — demanding its removal would be asserting the opposite of the policy.
        "must_remove": sorted(set(
            x for x in must_remove
            if x and present(x, body) and not re.search(
                rf"{re.escape(x)}\s+(?i:s\.?\s?r\.?\s?l\.?|s\.?\s?p\.?\s?a\.?|"
                rf"s\.?\s?a\.?\s?s\.?|s\.?\s?n\.?\s?c\.?|onlus|soc)", body))),
        "must_keep": sorted(set(x for x in must_keep if x and present(x, body))),
    }
    (d / f"{name}.gold.json").write_text(
        json.dumps(gold, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"  {source}/{name}.txt  {len(body):>6,} chars  "
          f"-{len(gold['must_remove']):<2d} +{len(gold['must_keep']):<2d}")
    return gold


# ── source specs ─────────────────────────────────────────────────────────────

CASSAZIONE = [
    ("2025/ECLI_IT_CASS_2025_15211CIV.txt", "01_tributario_persona_fisica", 4200,
     "IRPEF detrazioni. The party is named ALL-CAPS surname-first in the header, "
     "mixed-case reversed in the body, and by bare surname alone. The core "
     "local-consistency case."),
    ("2024/ECLI_IT_CASS_2024_24464CIV.txt", "02_tributario_due_difensori_cf", 3000,
     "Two counsel, each followed by a codice fiscale in brackets — the CF-adjacency "
     "anchor. A bank is a party and must survive (companies are opt-out)."),
    ("2024/ECLI_IT_CASS_2024_21034PEN.txt", "03_penale_nome_condiviso_col_pm", 3200,
     "Criminal decision: the defendant shares a first name with the Sostituto "
     "Procuratore, plus 'nato a … il …' and counsel introduced with 'l'avvocato'."),
    ("2025/ECLI_IT_CASS_2025_14726CIV.txt", "04_lavoro_enti_pubblici", 3400,
     "INPS against a public university and hospital, four counsel listed after "
     "'avvocati'. Institutions dominate; only natural persons may be touched."),
    ("2025/ECLI_IT_CASS_2025_14077CIV.txt", "05_decreto_estinzione_societa", 2600,
     "Short decree, no named judges, a company as respondent — a near no-op that must "
     "not invent detections."),
    ("2024/ECLI_IT_CASS_2024_13040CIV.txt", "06_indirizzi_e_domicilio", 3400,
     "Elective domicile addresses in the party block: street names and CAPs that are "
     "office addresses, not residences, and must survive."),
]

BDGT_DOCS = [
    ("Sentenza_U01_101_2025.txt", "01_imu_ruralita_monocratico", 3800,
     "CGT first instance, single judge, one party and one counsel, Comune as "
     "respondent."),
    ("Sentenza_U01_120_2025.txt", "02_due_difensori_recapiti", 3800,
     "Two counsel with codici fiscali, e-mail, telephone and an address."),
    ("Sentenza_U01_100_2025.txt", "03_societa_e_soci", 3800,
     "Collegiate panel, a company party and a second shareholder named in the body."),
    ("Sentenza_U01_122_2025.txt", "04_ricorrente_unico", 4200,
     "Minimal shape: one applicant, one counsel, one e-mail."),
]

CDS_DOCS = [
    ("ECLI_IT_CDS_2025_10000SENT.html", "01_equa_riparazione_omissis", 4200,
     "Consiglio di Stato appeal. Parties are -OMISSIS- in the source; counsel and the "
     "relatore are named in clear, so both roles are exercised in one document."),
    ("ECLI_IT_CDS_2025_10003SENT.html", "02_appello_amministrativo", 3800, ""),
    ("ECLI_IT_CDS_2025_10001SENT.html", "03_appello_amministrativo_bis", 4200, ""),
]

CGUE_DOCS = [
    ("2024/62024CC0376_IT.txt", "01_conclusioni_avvocato_generale", 4000,
     "Opinion of an Advocate General: the party is a two-letter initialism, the AG is "
     "named in clear, the referring court is foreign. Only the injected natural person "
     "may be removed."),
    ("2024/62024CC0790_IT.txt", "02_impugnazione_organizzazione", 3800,
     "EU appeal between two organisations — the run must be a near no-op."),
]

CONTI_DOCS = [
    ("ECLI_IT_CONT_2022_1000SGCAM.pdf", "01_pensionistico_omissis_e_leak", 4200,
     "Pension case. The PDF extractor letter-spaces the headings "
     "('S E N T E N Z A'), the party is (OMISSIS) in the header, and the source leaks a "
     "full name in the body — the leak is the point."),
    ("ECLI_IT_CONT_2022_1001SGCAM.pdf", "02_pensionistico_secondo", 4200, ""),
    ("ECLI_IT_CONT_2022_1010SGCAM.pdf", "03_pensionistico_terzo", 4200, ""),
]


# ── placeholder fillers (run before deidentify) ──────────────────────────────

def fill_bdgt(text):
    """Fill the official BDGT role tags with invented identities."""
    removed, seen = [], {}

    def idx(key):
        return seen.setdefault(key, len(seen))

    def cf(m):
        v = NB.CODICI_FISCALI[idx(m.group(0)) % len(NB.CODICI_FISCALI)]
        removed.append(v)
        return v

    text = re.sub(r"\bCF_(?:\w+_)?\d+\b", cf, text)

    def iva(m):
        v = NB.PARTITE_IVA[idx(m.group(0)) % len(NB.PARTITE_IVA)]
        removed.append(v)
        return f"IVA {v}"          # the source writes "P.IVA_1"; keep the cue readable

    text = re.sub(r"\bIVA_(?:\w+_)?\d+\b", iva, text)

    def person(m):
        role = m.group(1)
        i = idx(m.group(0))
        s, f = NB.counsel(i) if role == "Difensore" else NB.person(i + 4)
        removed.extend([f"{s} {f}", s.title()])
        return f"{s} {f}"

    text = re.sub(r"\b(Ricorrente|Resistente|Difensore|Rappresentante|Nominativo|Terzo)"
                  r"_\d+\b", person, text)

    def email(m):
        v = NB.EMAILS[idx(m.group(0)) % len(NB.EMAILS)]
        removed.append(v)
        return v

    text = re.sub(r"\b(?:Email|Pec|Pec_Difensore)_\d+\b", email, text)

    def phone(m):
        v = NB.PHONES[idx(m.group(0)) % len(NB.PHONES)]
        removed.append(v)
        return f"tel. {v}"         # a bare number in a contact line is our artifact

    text = re.sub(r"\bTelefono_\d+\b", phone, text)

    def addr(m):
        v = NB.ADDRESSES[idx(m.group(0)) % len(NB.ADDRESSES)]
        removed.append(v)
        return "residente in " + v

    text = re.sub(r"\bV?[Ii]ndirizzo_\d+\b", addr, text)
    text = re.sub(r"\b(?:Società|Societa|Associazione|Consorzio|Banca|Ditta)_\d+\b",
                  lambda m: NB.COMPANIES[idx(m.group(0)) % len(NB.COMPANIES)], text)
    text = re.sub(r"\b(?:Numero|Num|Dati_catastali|Conto_Corrente|Targa|Data|Luogo|"
                  r"Tipologia|Progetto|Marchio|Soggetto|Nom|Ric|Soc|Nomin)_\d+\b",
                  "[dato]", text)
    return text, removed


#: merito_civile masks names as initials followed by underscores: "d.ssa L___ S___",
#: "dall'avv. I___ A___", "Di M___ M___". Each distinct run is one person.
INITIALS_RUN = re.compile(
    r"(?<![\p{L}_])((?:(?:[A-ZÀ-Ü][a-zà-ü]{1,3}\s+)?[A-ZÀ-Ü]\.?_{2,})"
    r"(?:[^\S\r\n]+[A-ZÀ-Ü]\.?_{2,}){0,2})")


def fill_initials(text, seed):
    """Replace initials runs with invented people, judges kept apart from the rest.

    Runs are keyed on their literal text, so "L___ S___" is one person wherever it
    appears. Documents where every party is masked to the same placeholder (a whole
    decision of "X___ X___") are skipped by the caller — collapsing two spouses into one
    invented person would make the fixture assert something untrue.
    """
    from deidentify import JUDGE_CUE, PERSON_CUE

    # Only runs that something introduces as a person are filled. Without this gate the
    # builder wrote people into street and date positions — "in Ancona, Ortensia
    # Vimercati, n. 43" was a street, "Ferruccio Malaspina del 18.10.2018" a hearing
    # date — and then demanded their removal, so the fixture asserted nonsense.
    runs, order = {}, []
    for m in INITIALS_RUN.finditer(text):
        key = re.sub(r"\s+", " ", m.group(1)).strip()
        before = text[max(0, m.start() - 60):m.start()]
        if not (JUDGE_CUE.search(before) or PERSON_CUE.search(before)):
            continue
        if key not in runs:
            runs[key] = bool(JUDGE_CUE.search(before))
            order.append(key)
        elif JUDGE_CUE.search(before):
            runs[key] = True

    removed, kept = [], []
    j = p = 0
    for key in sorted(order, key=len, reverse=True):
        if runs[key]:
            s, f = NB.judge(seed + j); j += 1
            kept.append(f"{f.title()} {s.title()}")
        else:
            s, f = (NB.counsel(seed + p) if p % 2 else NB.person(seed + p)); p += 1
            removed += [f"{f.title()} {s.title()}", s.title()]
        text = text.replace(key, f"{f.title()} {s.title()}")
    return text, removed, kept


def fill_omissis(text, person_idx):
    """Replace -OMISSIS-/(OMISSIS) with an invented person; numbers stay numbers."""
    s, f = NB.person(person_idx)
    full = f"{f.title()} {s.title()}"
    text = re.sub(r"(?<=prot\.\s?n\.\s?)-?\(?[Oo][Mm][Ii][Ss][Ss][Ii][Ss]\)?-?",
                  "884213/2022", text)
    text = re.sub(r"(?<=n\.\s)-?\(?[Oo][Mm][Ii][Ss][Ss][Ii][Ss]\)?-?", "884213/2022", text)
    text = re.sub(r"-?\(\s*[Oo][Mm][Ii][Ss][Ss][Ii][Ss]\s*\)-?", full, text)
    text = re.sub(r"-OMISSIS-", full, text)
    return text, [full, s.title()]


# ── builders ─────────────────────────────────────────────────────────────────

def _emit(source, name, text, limit, note, src_label, extra_remove=(), seed=0,
          config=None):
    text, removed, kept = deidentify(text, seed=seed)
    text = truncate(text, limit)
    return write(source, name, text, note, src_label,
                 list(extra_remove) + removed,
                 kept + keep_present(text, INSTITUTIONS)
                 + re.findall(r"\bn\.\s?\d{1,6}/\d{2,4}\b", text)[:3]
                 + re.findall(r"\bC-\d+/\d+(?:\s?P)?\b", text)[:2],
                 config=config)


#: How many extra documents to auto-select per source, beyond the curated ones. The
#: curated fixtures pin the shapes we reason about; the extras are there so the suite
#: keeps meeting documents nobody chose, which is where new failure modes come from.
#: Deliberately generous — a wider corpus is what actually finds new failure modes, and
#: a dropped/failing fixture costs nothing (see `write`'s leak-checker gate and
#: fixture safety gate).
EXTRAS = {"cassazione": 24, "bdgt": 20, "consiglio_stato": 16, "corte_conti": 18,
          "cgue": 14}


def _auto_pick(candidates, used, count):
    """Deterministic spread over a sorted listing, skipping already-curated files."""
    pool = [c for c in sorted(candidates) if c not in used]
    if not pool or count <= 0:
        return []
    step = max(1, len(pool) // count)
    return pool[::step][:count]


def build_cassazione():
    used = set()
    for i, (rel, name, limit, note) in enumerate(CASSAZIONE):
        src = CASS / rel
        used.add(rel)
        if not src.exists():
            print(f"  SKIP {name}: not found")
            continue
        _emit("cassazione", name, src.read_text(encoding="utf-8", errors="replace"),
              limit, note, f"cassazione/{rel} (all real names replaced with invented ones)",
              seed=i * 2)

    # Spread across seven decades so the suite meets shapes the curated fixtures never
    # see: pre-1990s decisions carry no "Presidente:"/"Relatore:" header at all, and
    # some already abbreviate parties to bare initials in the published text itself
    # ("D.F. convenne...", a much older and looser convention than BDGT's underscored
    # placeholders). Recent years still dominate the count, since that is the shape a
    # real batch job mostly sees.
    pool = []
    for year in ("1965", "1978", "1990", "2001", "2008", "2014", "2018", "2019",
                 "2020", "2021", "2022", "2023", "2024", "2025"):
        d = CASS / year
        if d.is_dir():
            pool += [f"{year}/{f.name}" for f in d.iterdir() if f.suffix == ".txt"]
    for k, rel in enumerate(_auto_pick(pool, used, EXTRAS["cassazione"])):
        raw = (CASS / rel).read_text(encoding="utf-8", errors="replace")
        if len(raw) < 1200 or "Server Error" in raw[:200]:
            continue
        _emit("cassazione", f"{10 + k}_auto_{rel.split('/')[0]}_{rel.split('_')[-1][:-4]}",
              raw, 3600, "Auto-selected for shape variety.",
              f"cassazione/{rel} (all real names replaced with invented ones)",
              seed=40 + k * 3)


def build_bdgt():
    used = set()
    for i, (fname, name, limit, note) in enumerate(BDGT_DOCS):
        used.add(fname)
        src = BDGT / fname
        if not src.exists():
            print(f"  SKIP {name}: not found")
            continue
        text, removed = fill_bdgt(src.read_text(encoding="utf-8", errors="replace"))
        _emit("bdgt", name, text, limit, note,
              f"bdgt/{fname} (official role tags filled with invented identities, "
              f"then de-identified)", extra_remove=removed, seed=i * 3 + 1)

    # BDGT's official scraping runs cover 2021-2026; the role-tag convention is stable
    # across years, but the underlying court and matter mix varies, which is worth
    # meeting even though the masking scheme itself does not change.
    pool = []
    for year in ("2021", "2022", "2023", "2024", "2025", "2026"):
        d = BDGT_ROOT / f"scraping_bdgt_{year}_txt_norm"
        if d.is_dir():
            pool += [(year, f.name) for f in d.iterdir() if f.suffix == ".txt"]
    picked = _auto_pick(pool, {("2025", f) for f in used}, EXTRAS["bdgt"])
    for k, (year, fname) in enumerate(picked):
        src = BDGT_ROOT / f"scraping_bdgt_{year}_txt_norm" / fname
        raw = src.read_text(encoding="utf-8", errors="replace")
        if len(raw) < 1200:
            continue
        text, removed = fill_bdgt(raw)
        _emit("bdgt", f"{10 + k}_auto_{year}_{fname[:-4].lower()[-12:]}", text, 3800,
              "Auto-selected for shape variety.",
              f"bdgt/{year}/{fname} (official role tags filled, then de-identified)",
              extra_remove=removed, seed=60 + k * 3)


def build_cds():
    used = set()
    for i, (fname, name, limit, note) in enumerate(CDS_DOCS):
        used.add(fname)
        src = CDS / fname
        if not src.exists():
            print(f"  SKIP {name}: not found")
            continue
        text = strip_html(src.read_text(encoding="utf-8", errors="replace"))
        text, removed = fill_omissis(text, i * 4)
        _emit("consiglio_stato", name, text, limit,
              note or "Administrative appeal, for header variety.",
              f"giustizia_amministrativa/{fname} (HTML stripped, -OMISSIS- filled, "
              f"then de-identified)", extra_remove=removed, seed=i * 3 + 2)

    pool = []
    for year in ("2025", "2026"):
        d = CDS_ROOT / year / "html"
        if d.is_dir():
            pool += [(year, f.name) for f in d.iterdir() if f.suffix == ".html"]
    picked = _auto_pick(pool, {("2025", f) for f in used}, EXTRAS["consiglio_stato"])
    for k, (year, fname) in enumerate(picked):
        src = CDS_ROOT / year / "html" / fname
        text = strip_html(src.read_text(encoding="utf-8", errors="replace"))
        if len(text) < 1200:
            continue
        text, removed = fill_omissis(text, 20 + k * 2)
        _emit("consiglio_stato", f"{10 + k}_auto_{year}_{fname[:-5].lower()[-10:]}", text,
              3800, "Auto-selected for shape variety.",
              f"giustizia_amministrativa/{year}/{fname} (HTML stripped, -OMISSIS- "
              f"filled, then de-identified)", extra_remove=removed, seed=80 + k * 3)


def build_cgue():
    used = {r for r, _, _, _ in CGUE_DOCS}
    # CGUE's Italian translations lag the newest decisions, and older ones are sparser
    # (some cases skip a year entirely), so the pool is built from whichever of these
    # years actually has an "_IT" folder rather than assumed to exist.
    pool = []
    for year in ("2004", "2010", "2015", "2019", "2021", "2022", "2023", "2024"):
        d = CGUE / year
        if d.is_dir():
            pool += [f"{year}/{f.name}" for f in d.iterdir() if f.name.endswith("_IT.txt")]
    extra = [(r, f"{10 + k}_auto_{r.split('/')[0]}_{r.split('/')[-1][:-7].lower()}", 3800,
              "Auto-selected for shape variety.")
             for k, r in enumerate(_auto_pick(pool, used, EXTRAS["cgue"]))]
    for i, (rel, name, limit, note) in enumerate(CGUE_DOCS + extra):
        src = CGUE / rel
        if not src.exists():
            print(f"  SKIP {name}: not found")
            continue
        text = src.read_text(encoding="utf-8", errors="replace")
        removed = []
        # CGUE's own convention for a personal-data case: the party is reduced to a
        # bare 1-3 letter initialism on its own line ("MT", "GQ"). Most cases instead
        # name an organisation, so this simply does not fire for them — expected, not
        # a gap, since there is then no natural person in the document to remove.
        # Roman numerals, country/currency codes and section labels that legitimately
        # sit alone on a line and are not a pseudonymized party.
        _not_a_party = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
                        "EU", "UE", "IT", "EN", "FR", "DE", "ES"}
        m = re.search(r"^([A-Z]{1,3})$", text, re.M)
        if m and m.group(1) not in _not_a_party:
            code = m.group(1)
            s, f = NB.person(i * 4 + 3)
            text = re.sub(rf"^{code}$", f"{f.title()} {s.title()}", text, count=1,
                          flags=re.M)
            text = re.sub(rf"(?<![\w]){code}(?![\w])", s.title(), text)
            removed = [f"{f.title()} {s.title()}", s.title()]
        _emit("cgue", name, text, limit, note,
              f"CGUE/cgue_txt_ita/{rel} (party initialism filled, then de-identified)",
              extra_remove=removed, seed=i * 3 + 3)


#: (year, how many documents to take from that year's zip). Spread across three
#: decades: the Corte dei Conti's pension and accounting caseload changes shape only
#: slowly, but scan quality and header formatting drift enough across decades to be
#: worth meeting (see the letter-spaced-heading fixture, which is itself from an old
#: scan pipeline).
CONTI_YEARS = [("1995", 2), ("2003", 2), ("2010", 3), ("2016", 3), ("2019", 3),
              ("2022", 0), ("2024", 4)]  # 2022 handled by the curated docs above


def build_conti():
    used = {f for f, _, _, _ in CONTI_DOCS}
    for i, (fname, name, limit, note) in enumerate(CONTI_DOCS):
        src = CONTI / fname
        if not src.exists():
            print(f"  SKIP {name}: not found")
            continue
        text, removed = fill_omissis(pdf_text(src), i * 5 + 2)
        _emit("corte_conti", name, text, limit,
              note or "Pension case before the Corte dei Conti.",
              f"corte_conti/2022/pdf/{fname} (PyMuPDF text, (OMISSIS) filled, "
              f"then de-identified)", extra_remove=removed, seed=i * 3 + 4)

    import io
    import zipfile

    import fitz

    k = 0
    for year, want in CONTI_YEARS:
        if want <= 0:
            continue
        zpath = CONTI_ROOT / year / "pdf.zip"
        if not zpath.exists():
            print(f"  SKIP corte_conti {year}: {zpath} not found")
            continue
        with zipfile.ZipFile(zpath) as z:
            names = sorted(n for n in z.namelist()
                           if n.lower().endswith(".pdf") and "__MACOSX" not in n)
            names = names[::max(1, len(names) // (want * 8))] if names else []
            taken = 0
            for entry in names:
                if taken >= want:
                    break
                base = entry.rsplit("/", 1)[-1]
                if base in used:
                    continue
                try:
                    with fitz.open(stream=io.BytesIO(z.read(entry)),
                                   filetype="pdf") as doc:
                        raw = "\n".join(p.get_text() for p in doc)
                except Exception:
                    continue
                if len(raw) < 800:
                    continue
                taken += 1
                k += 1
                text, removed = fill_omissis(raw, 100 + k * 5)
                _emit("corte_conti", f"{10 + k}_auto_{year}_{base[:-4].lower()[-10:]}",
                      text, 4000, "Auto-selected for shape variety.",
                      f"corte_conti/{year}/pdf.zip::{base[:60]} (PyMuPDF text, "
                      f"(OMISSIS) filled, then de-identified)",
                      extra_remove=removed, seed=100 + k * 5)


MERITO = _root("PSEUDONIMIZZATORE_LEGALE_MERITO_CIVILE_ROOT")

#: (year, how many documents to take from that year's zip)
MERITO_YEARS = [("2017", 3), ("2019", 4), ("2020", 4), ("2022", 5), ("2023", 4),
                ("2024", 5), ("2025", 4)]


def build_merito():
    """Civil first-instance and appeal decisions, extracted from the yearly zips.

    The archives are ~1 GB each, so entries are read straight out of the zip rather than
    unpacked. Documents whose parties are all masked to the same placeholder (a whole
    decision of "X___ X___") are skipped: collapsing two people into one invented
    identity would make the fixture assert something untrue.
    """
    import io
    import zipfile

    import fitz

    for year, want in MERITO_YEARS:
        zpath = MERITO / year / "pdf.zip"
        if not zpath.exists():
            print(f"  SKIP merito {year}: {zpath} not found")
            continue
        with zipfile.ZipFile(zpath) as z:
            names = sorted(n for n in z.namelist()
                           if n.startswith("pdf/") and n.endswith(".pdf"))
            # Entries are sorted by court, so taking the first N would give N documents
            # from one tribunal. Step through the listing instead.
            names = names[::max(1, len(names) // (want * 12))] if names else []
            taken = 0
            for entry in names:
                if taken >= want:
                    break
                try:
                    with fitz.open(stream=io.BytesIO(z.read(entry)),
                                   filetype="pdf") as doc:
                        text = "\n".join(p.get_text() for p in doc)
                except Exception:
                    continue
                if len(text) < 1500 or not INITIALS_RUN.search(text):
                    continue
                distinct = {re.sub(r"\s+", " ", m.group(1))
                            for m in INITIALS_RUN.finditer(text)}
                if len(distinct) < 3:
                    continue                      # everything masked the same way
                taken += 1
                court = re.sub(r"[^A-Za-z]+", "_",
                               entry.split("__")[1] if "__" in entry else "merito"
                               ).strip("_").lower()[:28]
                name = f"{taken:02d}_{year}_{court}"
                text, removed, kept = fill_initials(text, seed=taken * 3)
                _emit("merito_civile", name, text, 4200,
                      f"Civil decision, {year}. Names are masked as initials in the "
                      f"source and filled with invented identities here.",
                      f"merito_civile/{year}/pdf.zip::{entry.split('/')[-1][:60]} "
                      f"(PyMuPDF text, initials filled, then de-identified)",
                      extra_remove=removed, seed=taken * 7)


BUILDERS = {"cassazione": build_cassazione, "bdgt": build_bdgt,
            "consiglio_stato": build_cds, "cgue": build_cgue,
            "corte_conti": build_conti, "merito_civile": build_merito}


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Rebuild privacy-safe evaluation fixtures from local archives.",
        epilog=(
            "Configure archive roots with PSEUDONIMIZZATORE_LEGALE_CASSAZIONE_ROOT, "
            "PSEUDONIMIZZATORE_LEGALE_BDGT_ROOT, "
            "PSEUDONIMIZZATORE_LEGALE_GIUSTIZIA_AMMINISTRATIVA_ROOT, "
            "PSEUDONIMIZZATORE_LEGALE_CGUE_ROOT, "
            "PSEUDONIMIZZATORE_LEGALE_CORTE_CONTI_ROOT and "
            "PSEUDONIMIZZATORE_LEGALE_MERITO_CIVILE_ROOT."
        ),
    )
    parser.add_argument("sources", nargs="*", choices=sorted(BUILDERS))
    args = parser.parse_args()
    for key in (args.sources or list(BUILDERS)):
        print(f"\n[{key}]")
        BUILDERS[key]()
    print(f"\nfixtures written to {OUT}")


if __name__ == "__main__":
    main()
