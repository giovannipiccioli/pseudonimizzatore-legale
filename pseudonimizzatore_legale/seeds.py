"""Find people from high-precision anchors, then propagate local variants.

The obvious way to find names — match name-*shaped* strings — forces a choice between
recall and precision that has no good answer. Loosen it and ordinary Italian gets
deleted; tighten it and the party is still readable three lines down.

So the two concerns are separated, and pull in opposite directions on purpose:

**Seeding is conservative.** A name is accepted only where the surrounding text proves
it is a person: a professional title, adjacency to a codice fiscale, a biographic
clause, the party block of a decision. Precision matters more than recall here, because
a bad seed does not stay local — propagation then hunts that mistake through the whole
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
            require_distinctive: bool = True, source: str = "regex") -> Entity | None:
        """Register `raw` as a person, unless one of the guards refuses it.

        `require_distinctive` asks whether the name must contain a corpus-rare token.
        For a regex hit the answer is yes — a candidate made entirely of common words is
        far more likely to be a phrase than a person, and there would be nothing safe to
        propagate anyway. A NER mention is different: the model has read the sentence,
        so "Giovanni Esposito" is a person even though both halves are common Italian
        names. Such a seed still replaces its exact spellings; it just contributes no
        bare token to propagate, which `variant_patterns` handles by emitting none.
        """
        name = _truncate_at_heading(_clean(raw))
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
        if len(toks) == 1 and not distinctive:
            return None
        if require_distinctive and not distinctive:
            return None                      # nothing distinctive to key on

        entity = Entity(display=name, role=role)
        entity.sources.add(source)
        existing = self._by_key.get(entity.key)
        if existing is None:
            entity.variants.add(name)
            self._by_key[entity.key] = entity
            return entity
        existing.variants.add(name)
        existing.sources.add(source)
        if _ROLE_RANK.get(role, 9) < _ROLE_RANK.get(existing.role, 9):
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
)

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
})


def collect(text: str, cfg) -> list[Entity]:
    """Find document-local person entities; policy is applied later."""
    seeds = SeedSet(cfg.min_token_len)

    for attr, role in _SIMPLE_ANCHORS:
        for m in getattr(P, attr).finditer(text):
            seeds.add(
                m.group(1),
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
        role = _party_role(m.group(0))
        for part in P.COUNSEL_LIST_SEP.split(m.group(1)):
            seeds.add(part, role, require_distinctive=False, source="regex:party_list")
    # …and counsel named by surname alone ("l'avv. Scaramuzza"), the one place a
    # one-token candidate is allowed through.
    for m in P.COUNSEL_SOLO.finditer(text):
        seeds.add(m.group(1), "Difensore", allow_single=True,
                  source="regex:counsel_surname")

    if cfg.profile != "query":
        for m in P.PARTY_BLOCK.finditer(text):
            role = _party_role(m.group(0))
            for run in P.ALLCAPS_RUN.finditer(m.group(1)):
                for name in _names_in_run(run.group(0)):
                    seeds.add(name, role, require_distinctive=False,
                              source="regex:legal_party_block")

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
                # a cue. SeedSet deduplicates agreement between ensemble members.
                seeds.add(mention.text, mention.role, allow_single=True,
                          require_distinctive=False, source=f"ner:{model_id}")

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
