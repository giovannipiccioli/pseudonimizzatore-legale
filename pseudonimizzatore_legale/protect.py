"""Collect judicial names and procedural references before role policy is applied."""
from dataclasses import dataclass, field

import regex as re

from . import patterns as P

_MAX_NAME_TOKENS = 4


@dataclass
class Protected:
    """Judicial names for the person matcher and spans for citation policy."""

    names: set[str] = field(default_factory=set)
    #: Case-number and case-citation spans.
    spans: list[tuple[int, int]] = field(default_factory=list)


def _plausible_person(name: str) -> bool:
    toks = [t for t in re.split(r"\s+", name.strip()) if t]
    if not (2 <= len(toks) <= _MAX_NAME_TOKENS):
        return False
    if P.INSTITUTION_HEAD.match(name.strip()):
        return False
    return not any(re.search(r"\d", t) for t in toks)


#: A name inside a bench-list window, bounded so it cannot start mid-word.
#: FULL_NAME, not FULL_NAME_NL: each match must stay on one line. The line break
#: between two consecutive judges is often the only boundary separating them (no comma,
#: no per-name role word), and letting a name cross it would merge "Ornella Trevisanato"
#: and the next line's "Celeste Bonaventura" into one fictitious four-token person.
_WINDOW_NAME = re.compile(rf"(?<![\p{{L}}'’])({P.FULL_NAME})(?![\p{{L}}'’])")
#: A role word sitting at the end of a captured name — the tabular layout's column.
_TRAILING_ROLE = re.compile(rf"\s+(?i:{P.JUDICIAL_ROLE})$")


def collect(text: str) -> Protected:
    """Find judicial names and case-number spans in the source text."""
    prot = Protected()

    def register(raw: str) -> None:
        # In a tabular bench list a captured name can include the role column.
        name = _TRAILING_ROLE.sub("", raw).strip(" .,;:-–")
        name = " ".join(name.split())
        if _plausible_person(name):
            prot.names.add(name)

    for pattern in P.JUDGE_ANCHORS:
        for m in pattern.finditer(text):
            register(m.group(1))

    # A bench announced by a single cue is a bounded, source-agnostic legal layout.
    for cue_pattern, end_pattern in P.JUDGE_LISTS:
        for cue in cue_pattern.finditer(text):
            stop = end_pattern.search(text, cue.end())
            window_end = min(cue.end() + P.JUDGE_LIST_WINDOW,
                             stop.start() if stop else len(text))
            window = text[cue.end():window_end]
            for m in _WINDOW_NAME.finditer(window):
                if P.INSTITUTION_HEAD.search(m.group(1)) or \
                        P.ORG_HEAD.search(m.group(1)):
                    continue
                register(m.group(1))

    # Public bodies are handled as a *rejection rule* in seeds.py, not as shielded
    # spans. Shielding them here looked equivalent but was not: a protected span wins
    # its characters outright, so "avvocatura" occurring inside the domain of
    # `ags.rm@mailcert.avvocaturastato.it` blocked a real e-mail from being replaced.
    # A European case is cited by a name as well as a number ("C-348/16, Moussa Sacko",
    # "Scoppola c. Italia"); both stay, under the same switch.
    case_spans = [m.span() for m in P.CASE_NUMBER.finditer(text)]
    case_spans += [m.span(1) for pattern in P.CASE_NAMES for m in pattern.finditer(text)]
    prot.spans = sorted(set(case_spans))
    return prot
