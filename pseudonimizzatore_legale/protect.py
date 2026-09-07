"""Detect evidence for text that publication policy may keep.

This module does not veto person detection. It records exact judicial-role and case-
number spans; late policy decides whether those spans survive. In particular, a judge's
surname never blocks an unrelated party with the same surname.
"""
from dataclasses import dataclass, field

import regex as re

from . import patterns as P

_MAX_NAME_TOKENS = 4


@dataclass
class Protected:
    """Detected protection evidence, before policy is applied."""

    names: set[str] = field(default_factory=set)
    #: Character spans carrying judicial-role or case-number evidence.
    spans: list[tuple[int, int]] = field(default_factory=list)
    span_kinds: dict[tuple[int, int], str] = field(default_factory=dict)
    span_names: dict[tuple[int, int], str] = field(default_factory=dict)
    identities: set[tuple[str, ...]] = field(default_factory=set)

    def matches_identity(self, name: str) -> bool:
        """Whether a complete identity—not merely one token—has judicial evidence."""
        return _identity_key(name) in self.identities


def _identity_key(name: str) -> tuple[str, ...]:
    return tuple(sorted(
        token.casefold()
        for token in re.findall(r"[\p{L}'’]+", name)
        if token
    ))


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
    """Detect judicial-role and case-number evidence in ``text``.

    Detectors always report evidence; late policy applies ``keep_judges`` and
    ``keep_case_numbers``.
    """
    prot = Protected()

    def register(raw: str, span: tuple[int, int]) -> None:
        """Record one judge and the exact span carrying judicial-role evidence."""
        name = re.sub(r"\s+", " ", raw).strip(" .,;:-–")
        # In a tabular bench list the role sits on the same line as the name
        # ("Federico Maria Sbaraglia   Presidente"), and FULL_NAME is greedy enough to
        # read it as a fourth name token. Shielding it does no harm, but it makes the
        # recorded name wrong, so drop it.
        name = _TRAILING_ROLE.sub("", name).strip(" .,;:-–")
        if not _plausible_person(name):
            return
        prot.names.add(name)
        prot.spans.append(span)
        prot.span_kinds[span] = "judge"
        prot.span_names[span] = name
        prot.identities.add(_identity_key(name))

    for pattern in P.JUDGE_ANCHORS:
        for m in pattern.finditer(text):
            register(m.group(1), m.span(1))

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
                register(m.group(1),
                         (cue.end() + m.start(1), cue.end() + m.end(1)))

    # Public bodies are handled as a *rejection rule* in seeds.py, not as shielded
    # spans. Shielding them here looked equivalent but was not: a protected span wins
    # its characters outright, so "avvocatura" occurring inside the domain of
    # `ags.rm@mailcert.avvocaturastato.it` blocked a real e-mail from being replaced.
    for m in P.CASE_NUMBER.finditer(text):
        span = m.span()
        prot.spans.append(span)
        prot.span_kinds[span] = "case_number"
        prot.span_names[span] = m.group(0)

    prot.spans = sorted(set(prot.spans))
    return prot
