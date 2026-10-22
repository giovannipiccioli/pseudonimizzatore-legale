"""Find people from high-precision anchors, then propagate local variants.

The obvious way to find names — match name-*shaped* strings — forces a choice between
recall and precision that has no good answer. Loosen it and ordinary Italian gets
deleted; tighten it and the party is still readable three lines down.

So the two concerns are separated, and pull in opposite directions on purpose:

**Seeding is conservative.** A name is accepted where surrounding text identifies a
person — a professional title, adjacency to a codice fiscale, a biographic clause, the
party block of a decision — or where a listed first name forms a complete multi-token
name. A listed word is never accepted alone. Precision still matters here, because a
bad seed does not stay local: propagation then hunts that mistake through the whole
document.

**Propagation is aggressive.** Once a person is known, every surface form of them is
hunted: reversed token order (headers write SURNAME NAME, prose writes Name Surname),
the surname alone ("la Benatti"), ALL-CAPS versus mixed case, a name split by a line
break. This is what stops a party who is pseudonymized in the header from being
perfectly readable in the body.

The rail that makes aggressive propagation tolerable is `rare_tokens`: a token may
become a propagation key only if it is long enough and absent from the corpus-derived
common-word set. Ambiguous tokens are handled after all entities are known. Without
these guards, propagating a name whose surname is "Del" replaces every "del" in the
document.
"""
import unicodedata
from functools import lru_cache
from importlib.resources import files

import regex as re

from . import patterns as P
from .labels import RESERVED
from .model import Entity


@lru_cache(maxsize=1)
def common_words() -> frozenset[str]:
    """Corpus-common words which are unsafe as document-wide alias keys."""
    import json
    data = files(__package__).joinpath("resources/common_words.json").read_text("utf-8")
    return frozenset(json.loads(data))


@lru_cache(maxsize=1)
def first_names() -> frozenset[str]:
    """Names registered in Italy, used only as weak, multi-token seeds."""
    import json
    data = files(__package__).joinpath("resources/first_names.json").read_text("utf-8")
    return frozenset(json.loads(data)["names"])


def place_key(name: str) -> str:
    """A town name compared without case, accents or the ALL-CAPS accent apostrophe."""
    name = unicodedata.normalize("NFKD", name.replace("’", "'").casefold())
    name = "".join(c for c in name if not unicodedata.combining(c))
    return " ".join(name.split()).rstrip("'")


@lru_cache(maxsize=1)
def comuni() -> frozenset[str]:
    """ISTAT comuni, current and suppressed, as `place_key`s, plus the everyday names of
    two whose official ones differ ("Reggio di Calabria", "Reggio nell'Emilia")."""
    import json
    data = files(__package__).joinpath("resources/comuni.json").read_text("utf-8")
    return frozenset(place_key(n) for n in json.loads(data)["names"]) | {
        "reggio calabria", "reggio emilia"}


#: Roles in priority order — a person seen both as party and as counsel is a party.
_ROLE_RANK = {"Ricorrente": 0, "Resistente": 1, "Difensore": 2, "Nominativo": 3}


def _clean(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip(" .,;:-–'’\n\t")


def _truncate_at_heading(name: str) -> str:
    """Cut a candidate at the first section-heading word after its first token.

    Patterns that tolerate a line break inside a name (court text wraps names all the
    time) otherwise run into the heading on the following line. The first token is
    exempt because "DI", "LO" and "LA" legitimately open Italian surnames.
    """
    toks = [t for t in re.split(r"\s+", name) if t]
    for i, tok in enumerate(toks[1:], start=1):
        if tok.lower().strip(".,;:") in P.SECTION_HEADING_TOKENS:
            return " ".join(toks[:i])
    return name


def rare_tokens(name: str, min_len: int) -> list[str]:
    """Tokens of `name` distinctive enough to hunt on their own.

    A token qualifies when it is long enough, absent from the corpus common-word set,
    and free of digits. "Benatti" qualifies; "del", "causa" and "Roma" do not.

    Judicial surnames are deliberately not excluded. Protection applies to exact
    judicial-role spans later; globally blocking a surname loses unrelated parties
    who happen to share it.
    """
    common = common_words()
    out = []
    for tok in re.split(r"[\s\-]+", name):
        tok = tok.strip(".,;:()'’")
        if len(tok) < min_len or re.search(r"\d", tok):
            continue
        if tok.lower() in common:
            continue
        if tok in RESERVED:
            continue
        out.append(tok)
    return out


class SeedSet:
    """Accumulates seeds, keyed so that spelling variants merge into one person."""

    def __init__(self, min_token_len: int):
        self._by_key: dict[tuple[str, ...], Entity] = {}
        self._min_len = min_token_len

    def add(self, raw: str, role: str, allow_single: bool = False,
            require_distinctive: bool = True, source: str = "regex",
            trusted: bool = False, given_name: bool = False) -> Entity | None:
        """Register `raw` as a person, unless one of the guards refuses it.

        `require_distinctive` asks whether the name must contain a corpus-rare token.
        For a regex hit the answer is yes — a candidate made entirely of common words is
        far more likely to be a phrase than a person, and there would be nothing safe to
        propagate anyway. A NER mention is different: the model has read the sentence,
        so "Giovanni Esposito" is a person even though both halves are common Italian
        names. Such a seed still replaces its exact spellings; it just contributes no
        bare token to propagate, which `variant_patterns` handles by emitting none.

        `trusted` skips the guards and lets `role` override the detected one: a
        reviewer who adds a name has read the document.

        `given_name` lets a single listed first name through even when it is a common
        word ("Luca", "Paolo"): a salutation or a kinship cue has said it is a person.
        Such a seed folds into the one full name it belongs to, if there is one, and
        is propagated only by `core`'s case-sensitive given-name pass.
        """
        name = _clean(raw)
        if trusted and name:
            return self._register(name, role, source, trusted=True)
        name = _truncate_at_heading(name)
        toks = [t for t in re.split(r"\s+", name) if t]
        if not ((1 if allow_single else 2) <= len(toks) <= 4):
            return None
        # `search`, not `match`: "MINISTERO DELL'ECONOMIA E DELLE FINANZE" is scanned in
        # ALL-CAPS slices, and the slice "DELLE FINANZE" does not *start* with the head
        # word even though it is plainly part of an institution.
        if P.INSTITUTION_HEAD.search(name) or P.ORG_HEAD.search(name):
            return None
        # Anchored: the unanchored fragment matched "Spa" inside "Spadaccini".
        if P.COMPANY_SUFFIX_RE.search(name):
            return None
        if P.STREET_HEAD.match(name):
            return None                      # an address, not a person
        if toks[0].lower() in P.FRAGMENT_HEAD:
            return None                      # a slice of a longer name, not a name
        if any(t.strip("_0123456789") in RESERVED for t in toks):
            return None                      # our own output, not a person
        distinctive = rare_tokens(name, self._min_len)
        # A model can emit a one-character fragment with very high confidence (XLM-R
        # has labelled the "P" in "PICCININI" as a person). Propagating that exact
        # one-token seed then removes the P from the protected public body "I.N.P.S.".
        # Multi-token NER candidates may be made entirely of common names and still be
        # useful, but a singleton has to be distinctive enough to stand on its own.
        if len(toks) == 1 and not distinctive and not (
                given_name and toks[0].casefold() in first_names()):
            return None
        if require_distinctive and not distinctive:
            return None                      # nothing distinctive to key on
        return self._register(name, role, source)

    def _register(self, name: str, role: str, source: str,
                  trusted: bool = False) -> Entity:
        entity = Entity(display=name, role=role)
        entity.sources.add(source)
        existing = self._by_key.get(entity.key)
        if existing is None:
            entity.variants.add(name)
            self._by_key[entity.key] = entity
            return entity
        existing.variants.add(name)
        existing.sources.add(source)
        if trusted or _ROLE_RANK.get(role, 9) < _ROLE_RANK.get(existing.role, 9):
            existing.role = role
        # Prefer the longer spelling as the canonical display form.
        if len(name) > len(existing.display):
            existing.display = name
        return existing

    def all(self) -> list[Entity]:
        """Every distinct person, with partial-name seeds folded into their full name.

        Detectors disagree about how much of a name they see: "dall'avv. Gallusi Sandro"
        is caught whole by COUNSEL and its surname alone by COUNSEL_SOLO, and a NER
        model reading a document will happily report both "Antonio De Luca" and a later
        bare "De Luca". Keyed on their tokens those are different seeds, so one person
        would be issued `Difensore_1` where written in full and `Difensore_2` where
        written short — the exact local inconsistency this library exists to prevent.

        A seed folds into another when its tokens are a strict subset of the other's,
        which covers a bare surname of either length. Shortest first, so a chain
        ("Luca" → "De Luca" → "Antonio De Luca") collapses in one pass.

        Ambiguity is left alone deliberately. If "De Luca" could belong to either
        "Antonio De Luca" or "Maria De Luca" there is no evidence here to choose, and
        guessing would attribute one person's words to another; two tags is the honest
        answer. Nesting is not ambiguity, so only the *smallest* candidates compete.

        Folding happens here rather than in `add` so it cannot depend on which detector
        ran first.
        """
        for key in sorted(self._by_key, key=len):
            seed = self._by_key.get(key)
            if seed is None:
                continue
            tokens = set(key)
            hosts = [s for k, s in self._by_key.items() if tokens < set(k)]
            if not hosts:
                continue
            shortest = min(len(s.key) for s in hosts)
            finalists = [s for s in hosts if len(s.key) == shortest]
            if len(finalists) == 1:
                finalists[0].variants |= seed.variants
                del self._by_key[key]
        return list(self._by_key.values())


def _party_role(block_start_text: str) -> str:
    """Whether a party block introduces the applicant or the respondent."""
    head = block_start_text[:40].lower()
    if "contro" in head or "confronti" in head:
        return "Resistente"
    return "Ricorrente"


#: (pattern, role) for every anchor whose capture group 1 is a plain single name.
#: Order matters only for the role a person ends up with when two anchors find the same
#: name — `SeedSet.add` keeps the strongest role, so the listing order here is
#: readability, not precedence. `CF_ADIACENTE` leads because adjacency to a codice
#: fiscale is the one anchor that cannot be anything but a person.
_SIMPLE_ANCHORS = (
    ("CF_ADIACENTE", "Nominativo"),
    ("COUNSEL", "Difensore"),
    ("DIFESO_DA", "Difensore"),
    ("TITOLO", "Nominativo"),
    ("BIOGRAFICO", "Nominativo"),
    ("PKI_FIRMA", "Nominativo"),
    ("PARTY_ROLE", "Ricorrente"),
    ("QUALIFICA", "Nominativo"),
    ("PROPOSTO_DA", "Ricorrente"),
    ("NEI_CONFRONTI", "Resistente"),
    ("EMAIL_DISPLAY_NAME", "Nominativo"),
)

#: Anchors whose name may wrap onto the next line (they read FULL_NAME_NL), and
#: whether the name stands *before* the evidence: CF_ADIACENTE reads the name that
#: precedes a codice fiscale, the others the name after their cue.
_WRAPPING_ANCHORS = {"COUNSEL": False, "DIFESO_DA": False, "PKI_FIRMA": False,
                     "CF_ADIACENTE": True}

# These cues identify a private person strongly enough that an all-common name such as
# ``Antonio De Luca`` is still useful as an exact full-name seed. It contributes no
# unsafe bare-token propagation because ``rare_tokens`` remains empty.
_ALLOW_COMMON_NAME = frozenset({
    "CF_ADIACENTE",
    "COUNSEL",
    "DIFESO_DA",
    "TITOLO",
    "BIOGRAFICO",
    "PKI_FIRMA",
    "PARTY_ROLE",
    "QUALIFICA",
    "PROPOSTO_DA",
    "NEI_CONFRONTI",
    "EMAIL_DISPLAY_NAME",
})

#: Anchors whose cue is followed by organisations as often as by people: the "contro"
#: heading of NEI_CONFRONTI, and BIOGRAFICO's "rappresentato e difeso", which follows a
#: company or a public body just as it follows a party.
_ORGANISATION_PRONE = frozenset({"BIOGRAFICO", "NEI_CONFRONTI"})

# Italian surname particles accepted between a listed first name and a distinctive
# surname. Keeping this deliberately small avoids turning ordinary phrases into names.
_SURNAME_PARTICLES = frozenset({
    "da", "dal", "dalla", "de", "dei", "del", "della", "di", "la", "lo",
})


def _in_organisation(text: str, start: int, end: int) -> bool:
    """True if the text continues the name at `start:end` into an organisation's name."""
    return bool(P.ORG_SUFFIX_AFTER.match(text, end)
                or P.ORG_NAME_BEFORE.search(text, max(0, start - 60), start))


def _continues_name(text: str, start: int, end: int) -> bool:
    """Whether the line segment ``text[start:end]`` reads as the wrapped rest of a name.

    It does if every token is name-shaped, none is a heading or role word, none is a
    common word unless it is a listed first name, and the segment is not a field label
    (a colon follows it).
    """
    tokens = re.findall(P.NAME_TOKEN, text[start:end])
    if not tokens or re.match(r"[^\S\n]*:", text[end:end + 40]):
        return False
    common, listed = common_words(), first_names()
    return not any(
        token.casefold() in P.SECTION_HEADING_TOKENS
        or (token.casefold() in common and token.casefold() not in listed)
        for token in tokens)


def _one_name(text: str, start: int, end: int, before: bool = False) -> tuple[int, int]:
    """Trim a name capture that crosses line breaks to the lines that hold one name.

    Court text wraps names, so several anchors read a name across a line break
    ("dall'avv. Gallusi⏎Sandro"). Past the break the capture is part of the name only
    if it reads as its rest (`_continues_name`); otherwise it is the next line's first
    words, and replacing them deletes those words and the break: "Giudice: avv. Biagio
    Stomeo⏎Segretario: …" was one person "Biagio Stomeo Segretario", and "difeso
    dall'avv. Mario Malaspina⏎Il ricorrente" took the "Il". The line next to the
    evidence is always kept: the one after the cue, or, with `before`, the one before
    the codice fiscale.
    """
    breaks = [start + i for i, char in enumerate(text[start:end]) if char == "\n"]
    if not breaks:
        return start, end
    if before:
        kept = breaks[-1] + 1
        for i in reversed(range(len(breaks))):
            segment_start = breaks[i - 1] + 1 if i else start
            if not _continues_name(text, segment_start, breaks[i]):
                break
            kept = segment_start
        return kept, end
    kept = breaks[0]
    for i, line_break in enumerate(breaks):
        segment_end = breaks[i + 1] if i + 1 < len(breaks) else end
        if not _continues_name(text, line_break + 1, segment_end):
            break
        kept = segment_end
    return start, kept


def _adjacent(left: re.Match, right: re.Match, text: str) -> bool:
    """Whether two name-shaped tokens are separated only by ordinary whitespace.

    One line break is allowed, because names wrap ("avv. Gervasio Spadaccini ed
    Anastasia⏎Belloccio"), but only where the next line reads as the rest of the name:
    both tokens in the same case style, and `_continues_name`. The lexicon is weak
    evidence, and the word after a break starts the next line as often as it finishes
    a name: "Presidente: VERDI CARLO⏎Rossi insiste" made the phantom person "CARLO
    Rossi", whose surname then went to a neutral tag instead of to the real party
    "Mario Rossi".
    """
    gap = text[left.end():right.start()]
    if not gap or not re.fullmatch(P.SEP_NL, gap):
        return False
    return "\n" not in gap or (left.group(0).isupper() == right.group(0).isupper()
                               and _continues_name(text, right.start(), right.end()))


def _first_name_candidates(text: str) -> list[str]:
    """Full-name candidates whose first or last component is a listed first name.

    The list is evidence, not a dictionary substitution: a first name never becomes a
    seed alone. Adjacent listed/common words are also refused, which avoids treating
    sentence openings and place names as a person while keeping ordinary
    ``Given Surname`` and ``SURNAME GIVEN`` forms. Streets, saints and towns are named
    after people too, and are refused: "Viale Pietro Pietramellara", "San Giorgio",
    "Ospedale di Vittorio Veneto". Before this the street lost its name and kept its
    number, and the "surname" Pietramellara went on to replace every other mention.
    """
    tokens = list(re.finditer(P.NAME_TOKEN, text))
    listed = first_names()
    common = common_words()
    found: list[str] = []
    seen: set[tuple[int, int]] = set()

    def add(start: int, end: int) -> None:
        span = (tokens[start].start(), tokens[end].end())
        if P.ORG_SUFFIX_AFTER.match(text, span[1]):
            return
        if P.NAMED_PLACE_BEFORE.search(text, max(0, span[0] - 40), span[0]):
            return
        if place_key(text[span[0]:span[1]]) in comuni():
            return
        if span not in seen:
            seen.add(span)
            found.append(text[span[0]:span[1]])

    for index, token in enumerate(tokens):
        if token.group(0).casefold() not in listed:
            continue

        # Given-name first: ``Ferruccio Malaspina`` or ``Amedeo Della Rovere``.
        if index + 1 < len(tokens) and _adjacent(token, tokens[index + 1], text):
            next_word = tokens[index + 1].group(0).casefold()
            if next_word in listed:
                # ``Federico Maria Sbaraglia``: two given names and one surname.
                if (next_word != token.group(0).casefold()
                        and "\n" not in text[token.end():tokens[index + 1].start()]
                        and index + 2 < len(tokens)
                        and _adjacent(tokens[index + 1], tokens[index + 2], text)
                        and tokens[index + 2].group(0).casefold() not in common
                        and tokens[index + 2].group(0).casefold() not in listed):
                    add(index, index + 2)
            elif next_word in _SURNAME_PARTICLES:
                if (index + 2 < len(tokens)
                        and _adjacent(tokens[index + 1], tokens[index + 2], text)
                        and tokens[index + 2].group(0).casefold() not in common
                        and tokens[index + 2].group(0).casefold() not in listed):
                    add(index, index + 2)
            elif next_word not in common and next_word not in listed:
                add(index, index + 1)

        # Surname first is accepted only in the ALL-CAPS style used by legal headers.
        # In ordinary prose, ``Ieri Ferruccio Malaspina`` would otherwise make the
        # sentence-opening word look like Ferruccio's surname.
        if (index > 0
                and token.group(0).isupper()
                and tokens[index - 1].group(0).isupper()
                and _adjacent(tokens[index - 1], token, text)):
            previous = tokens[index - 1].group(0).casefold()
            if previous not in common and previous not in listed:
                start = index - 1
                end = index
                if (start > 0
                        and _adjacent(tokens[start - 1], tokens[start], text)
                        and tokens[start - 1].group(0).casefold() in _SURNAME_PARTICLES):
                    start -= 1
                if (index + 1 < len(tokens)
                        and tokens[index + 1].group(0).isupper()
                        and _adjacent(token, tokens[index + 1], text)
                        and "\n" not in text[token.end():tokens[index + 1].start()]
                        and tokens[index + 1].group(0).casefold() in listed):
                    end += 1
                add(start, end)

    return found


def collect(text: str, cfg, *, mentions=(), people=()) -> list[Entity]:
    """Find document-local person entities; policy is applied later.

    `mentions` are person `Mention`s from a NER the caller ran on this same text;
    `people` are ``(surface, role)`` pairs a reviewer added.
    """
    seeds = SeedSet(cfg.min_token_len)

    for attr, role in _SIMPLE_ANCHORS:
        for m in getattr(P, attr).finditer(text):
            if attr in _ORGANISATION_PRONE and _in_organisation(text, m.start(1), m.end(1)):
                continue
            start, end = m.span(1)
            if attr in _WRAPPING_ANCHORS:
                start, end = _one_name(text, start, end, before=_WRAPPING_ANCHORS[attr])
            seeds.add(
                text[start:end],
                role,
                require_distinctive=attr not in _ALLOW_COMMON_NAME,
                source=f"regex:{attr.lower()}",
            )

    # Counsel lists must run too: "avvocati A B, C D e E F" introduces several people
    # at a single cue, and the single-name pattern only ever sees the first of them.
    for m in P.COUNSEL_LIST.finditer(text):
        for part in P.COUNSEL_LIST_SEP.split(m.group(1)):
            seeds.add(part, "Difensore", require_distinctive=False,
                      source="regex:counsel_list")
    # Parties come in lists too — dozens of applicants in a mass appeal, the
    # counter-interested parties of a public competition — and, as with counsel, the
    # single-name anchors only see the first. The cue decides the side.
    for m in P.PARTY_LIST.finditer(text):
        if _in_organisation(text, m.start(1), m.end(1)):
            continue
        role = _party_role(m.group(0))
        for part in P.COUNSEL_LIST_SEP.split(m.group(1)):
            seeds.add(part, role, require_distinctive=False, source="regex:party_list")
    # …and counsel named by surname alone ("l'avv. Scaramuzza"), the one place a
    # one-token candidate is allowed through.
    for m in P.COUNSEL_SOLO.finditer(text):
        seeds.add(m.group(1), "Difensore", allow_single=True,
                  source="regex:counsel_surname")
    # The same for a party known only by surname: "il sig. Malaspina", "il ricorrente
    # Malaspina". When the full name is also given, the surname folds into it.
    for attr, role in (("TITOLO_SOLO", "Nominativo"), ("PARTY_ROLE_SOLO", "Ricorrente")):
        for m in getattr(P, attr).finditer(text):
            if not _in_organisation(text, m.start(1), m.end(1)):
                seeds.add(m.group(1), role, allow_single=True,
                          source=f"regex:{attr.lower()}")

    if cfg.profile != "query":
        for m in P.PARTY_BLOCK.finditer(text):
            role = _party_role(m.group(0))
            for run in P.ALLCAPS_RUN.finditer(m.group(1)):
                for name in _names_in_run(run.group(0)):
                    seeds.add(name, role, require_distinctive=False,
                              source="regex:legal_party_block")

    # Relatives and correspondents are named by first name alone: "il figlio minore
    # Tommaso", "Caro Paolo,", "Un caro saluto,⏎Luca". The cue says it is a person; a
    # lower-case or common-word name must also be a listed first name.
    use_list = getattr(cfg, "first_names", True)
    for attr in ("PARENTELA", "SALUTO"):
        for m in getattr(P, attr).finditer(text):
            name = m.group(m.lastindex)
            first = name.split()[0].casefold()
            listed = use_list and first in first_names()
            if not listed and (attr == "SALUTO" or not name[0].isupper()):
                continue
            seeds.add(name, "Nominativo", allow_single=True, require_distinctive=False,
                      given_name=listed, source=f"regex:{attr.lower()}")

    # A first-name list cheaply finds people whom legal layout does not announce. It is
    # deliberately weaker than context or NER: only a complete adjacent name is added,
    # never a listed token on its own. Late policy treats this source as neutral.
    if use_list:
        for name in _first_name_candidates(text):
            seeds.add(name, "Nominativo", require_distinctive=False,
                      source="lexicon:first_name")

    # Optional transformer NER, last: it reads sentences rather than layout, so it finds
    # the people no anchor announces. Its mentions go through exactly the same `add`
    # gauntlet as every regex hit — institution/company rejection and the common-word
    # guard still apply. Judicial-role evidence is resolved later, alongside every
    # other candidate.
    if getattr(cfg, "ner", None):
        from . import ner as ner_mod
        model_ids = (cfg.ner,) if isinstance(cfg.ner, str) else cfg.ner
        for model_id in model_ids:
            backend = ner_mod.get_backend(model_id, cfg.ner_device, cfg.ner_threshold)
            for mention in backend.find_people(text):
                # allow_single: the model has sentence-level evidence a regex does not,
                # so a lone surname is worth trusting here where it would not be from
                # a cue. SeedSet deduplicates agreement between ensemble members. A
                # model can run a name into the next line's label as a regex can.
                surface = mention.text
                if text[mention.start:mention.end] == surface:
                    surface = text[slice(*_one_name(text, mention.start, mention.end))]
                seeds.add(surface, mention.role, allow_single=True,
                          require_distinctive=False, source=f"ner:{model_id}")
    # The same for a NER run outside this package (in a browser, say). Its offsets are
    # into this text, so the surface is read from it rather than from the model.
    for mention in mentions:
        seeds.add(text[slice(*_one_name(text, mention.start, mention.end))], mention.role,
                  allow_single=True, require_distinctive=False, source=mention.source)

    # People a reviewer added skip every guard, but still fold into the names found
    # above and propagate like them.
    for surface, role in people:
        seeds.add(surface, role, source="user", trusted=True)

    return seeds.all()


def _names_in_run(run: str) -> list[str]:
    """Personal names inside one maximal upper-case run.

    The run is first *cut* at every institution, organisation or legal-form marker it
    contains, then names are read only from the surviving segments. Cutting rather than
    rejecting matters in both directions: rejecting the whole run loses the real party
    in "ROSSI MARIO CONTRO AGENZIA DELLE ENTRATE", while not cutting at all lets a
    window slide across "…SUPREMA CORTE | D'APPELLO DI TRIESTE" and invent a person out
    of the tail of a court's name.
    """
    # Once an organisation marker starts, its following words describe that same
    # organisation. Keeping the suffix produced "NAZIONALE DEL LAVORO" from "BANCA
    # NAZIONALE DEL LAVORO" and "GENERALE DELLO" from "AVVOCATURA GENERALE DELLO
    # STATO" as invented people. The prefix remains useful for layouts such as
    # "ROSSI MARIO CONTRO AGENZIA DELLE ENTRATE".
    starts = [m.start() for m in P.INSTITUTION_HEAD.finditer(run)]
    starts += [m.start() for m in P.ORG_HEAD.finditer(run)]
    starts += [m.start() for m in P.COMPANY_SUFFIX_RE.finditer(run)]
    segments = [run[:min(starts)] if starts else run]

    out = []
    for seg in segments:
        for m in P.ALLCAPS_NAME.finditer(seg):
            out.append(m.group(1))
    return out


def variant_patterns(entity: Entity, min_len: int,
                     skip_tokens: frozenset[str] = frozenset()
                     ) -> list[tuple[re.Pattern, bool]]:
    """Every regex that should resolve to `seed`, as ``(pattern, is_full_name)``.

    Two kinds come back, and the caller must be able to tell them apart because they
    carry different confidence:

    * **full spellings** — the name as written, and with its tokens reversed, since a
      header writes "BENATTI ROSSELLA" where prose writes "Rossella Benatti";
    * **bare distinctive tokens** — the surname alone, which is what catches
      "la Benatti" in the body but is a weaker claim on any given span.

    Full spellings must win a contested span so that "BENATTI ROSSELLA" is consumed
    whole rather than having its surname replaced and a stray first name left behind.
    """
    out: list[tuple[int, re.Pattern, bool]] = []

    def add(literal: str, full: bool) -> None:
        out.append((len(literal),
                    re.compile(rf"(?<![\p{{L}}\p{{N}}]){literal}(?![\p{{L}}\p{{N}}])",
                               re.I),
                    full))

    for variant in entity.variants | {entity.display}:
        # A lone common first name ("Luca", "Rosa") is no spelling to hunt without
        # regard to case and context; `core` proposes it case-sensitively instead.
        if len(variant.split()) == 1 and not rare_tokens(variant, min_len):
            continue
        for order in name_orders(variant):
            toks = [re.escape(token) for token in order.split()]
            add(r"\s+".join(toks), full=True)

    for tok in rare_tokens(entity.display, min_len):
        if tok.casefold() in skip_tokens:
            continue
        add(re.escape(tok), full=False)

    out.sort(key=lambda p: -p[0])
    return [(pattern, full) for _, pattern, full in out]


def name_orders(value: str) -> set[str]:
    """Likely full-name orders across surname-first headers and ordinary prose."""
    tokens = [token for token in re.split(r"\s+", value) if token]
    if not tokens:
        return set()
    orders = {" ".join(tokens), " ".join(reversed(tokens))}
    # All cyclic rotations cover one- and two-token surnames/given names without the
    # combinatorial and attribution risk of arbitrary permutations.
    orders.update(
        " ".join(tokens[index:] + tokens[:index])
        for index in range(1, len(tokens))
    )
    return orders
