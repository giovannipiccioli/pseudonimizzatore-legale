"""Review-oriented residual checks over pseudonymized output.

These checks never rewrite text and never claim that a document is safe.
``passed_checks`` means only that these inexpensive heuristics found nothing;
``needs_review`` identifies a higher-priority manual-review candidate.
"""
from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

import regex as re

from . import patterns as P
from .model import ResidualFinding, Verification
from .seeds import comuni, first_names, place_key


_PRIVATE_PERSON_CUE = re.compile(
    rf"(?i:\b(?:contribuente|ricorrente|controricorrente|resistente|appellante|"
    rf"appellato|imputato|indagato|convenuto|attore|opponente|istante|debitore|"
    rf"creditore|erede|testimone|persona\s+fisica)\b)"
    rf"[\s,:;-]{{1,20}}(?:[dD]ott\.?(?:ssa)?\s+|[sS]ig\.?(?:ra)?\s+)?"
    rf"({P.FULL_NAME})"
)

_ALREADY_ANONYMIZED = re.compile(
    r"\(?[Oo]missis\)?|\bOMISSIS\b|\b\p{Lu}\.\s?\p{Lu}\.(?:\s?\p{Lu}\.)?"
    r"(?![\p{L}])"
)

_POSSIBLE_PERSON = re.compile(
    rf"(?<![\p{{L}}'’])({P.FULL_NAME})(?![\p{{L}}'’])"
)


def _contained(span: tuple[int, int], protected: Iterable[tuple[int, int]]) -> bool:
    start, end = span
    return any(other_start <= start and end <= other_end
               for other_start, other_end in protected)


def _whole_value(value: str) -> re.Pattern:
    return re.compile(
        rf"(?<![\p{{L}}\p{{N}}]){re.escape(value)}(?![\p{{L}}\p{{N}}])",
        re.I,
    )


# ── capitalised phrases that cannot be a person ───────────────────────────────────────
# The name-shape scan below is deliberately broad. These three tests drop a phrase only
# when the phrase *as a whole* cannot be a name, and never because of the words around
# it, so a name next to a heading or a role is still reported.

#: Articles, prepositions and conjunctions.
_FUNCTION_WORDS = frozenset(
    "il lo la le gli i un uno una l di d de del dello della dei degli delle da dal dalla dai "
    "dalle dall dell nell sull all in nel nella nei nelle per con su sul sulla sui sulle a al "
    "alla ai agli e ed o ad tra fra che non ha".split())
#: The ones that can open a surname: "Del Giudice", "Lo Strano", "Dall'Aglio".
_SURNAME_PARTICLES = frozenset(
    "de di da d del dello della dei degli delle dal dalla dall dell lo la le li".split())
#: Courtesy titles, procedural roles and the words of a court's headings and signature
#: blocks, besides the section headings and roles the scan already knows.
_LAYOUT_WORDS = P.SECTION_HEADING_TOKENS | frozenset("""
dott prof avv sig sigra signor signore signora egr egregio gentile spett gent ing geom rag arch
sezione sezioni prima seconda terza quarta quinta sesta settima ottava nona decima
secondo terzo quarto quinto sesto settimo ottavo bis ter quater unite riunite
civile penale lavoro giurisdizionale controllo centrale regionale provinciale territoriale
collegio parte data giustizia tributaria sent ord decr
segretaria cliente locatore locatrice conduttore conduttrice dirigente funzionario garante
istruttore monocratico rel
""".split())
#: Fixed phrases of a decision's heading.
_FIXED_PHRASES = re.compile(r"\b(?:in nome del popolo(?: italiano)?|popolo italiano|(?:primo|secondo) grado)\b")
#: A legal form right after the phrase: it is a company, and companies stay by default.
_COMPANY_AFTER = re.compile(rf"[^\S\n]+(?:{P.COMPANY_SUFFIX})(?![\p{{L}}])", re.IGNORECASE)
#: A province's two letters after a town: "Alessandria AL".
_PROVINCE = re.compile(r"[^\S\n]+\p{Lu}{2}$")


@lru_cache(maxsize=1)
def _closed_words() -> frozenset[str]:
    """The words a phrase made only of them cannot be a name for. A word that is also a
    first name ("Primo", "Gentile") is left out, and so is "giudice", a common surname."""
    return (_FUNCTION_WORDS | _LAYOUT_WORDS) - first_names() - {"giudice"}


def _not_a_name(value: str, output: str, end: int) -> bool:
    """Whether the capitalised phrase ``output[..end]`` cannot be a person.

    * It is made only of articles, prepositions, titles, roles and heading words ("Il
      Presidente", "Sezione Terza", "IN NOME DEL POPOLO"). A phrase that opens with a
      surname particle and ends with a plain word stays: "Del Giudice" is a person. One
      that ends with a particle, like "DI PRIMO GRADO DI", is the slice of a heading.
    * A legal form follows it ("Nautica Brancaleone S.n.c.").
    * It is a comune ("Reggio Calabria", "Alessandria AL"), unless its first word is a
      first name: "Alice Castello" may be a person.
    """
    words = [w for w in re.split(r"['’\s.,;:]+", _FIXED_PHRASES.sub(" ", " ".join(value.casefold().split()))) if w]
    if not words:
        return True
    if all(word in _closed_words() for word in words):
        return words[0] not in _SURNAME_PARTICLES or words[-1] in _FUNCTION_WORDS
    if _COMPANY_AFTER.match(output, end):
        return True
    town = {place_key(_PROVINCE.sub("", value)), place_key(value)} & comuni()
    return any(key.split()[0] not in first_names() for key in town)


#: A title or trade and the capitalised words after it, one to four of them.
_TITLE_NAME = re.compile(
    rf"(?<![\p{{L}}\p{{N}}_]){P.PERSONAL_TITLE}(?![\p{{L}}.])[:,]?[^\S\n]+"
    rf"({P.NAME_TOKEN}(?:{P.SEP}{P.NAME_TOKEN}){{0,3}})(?![\p{{L}}'’])")
#: The titles judges carry. Another judge's surname, repeated after one of them, is theirs.
_JUDGE_TITLE = re.compile(r"(?i:dott|dr|prof)")
#: A judicial role right after the name ("dott. Verdi Presidente", "dr. Verdi, Giudice"), or
#: alone on the line above or below it, as a signature block stacks them.
_JUDGE_ROLE_AFTER = re.compile(rf"[^\S\n]*[,;–-]?[^\S\n]*(?i:{P.JUDICIAL_ROLE})\b")
_JUDGE_ROLE_ALONE = re.compile(
    rf"[^\S\n]*(?i:(?:il|la|l['’])[^\S\n]*)?(?i:{P.JUDICIAL_ROLE})[^\S\n]*:?[^\S\n]*")


def _judge_like(output: str, start: int, end: int, title: str, judges: set[str]) -> bool:
    """Whether something else says that a name after a title is a judge's, who stays in clear.

    A judicial role right before the title ("il Presidente dott. Verdi"), right after the
    name, or alone on the next line up or down; and, for the titles judges carry, a word of
    the name that a kept judge also has: the bench list names "Anita Verdi", and "dott.
    Verdi" in the text is the same person.
    """
    line_start = output.rfind("\n", 0, start) + 1
    if P.INITIALS_JUDGE_BEFORE.search(output[line_start:start]):
        return True
    if _JUDGE_ROLE_AFTER.match(output, end):
        return True
    above = output[output.rfind("\n", 0, max(line_start - 1, 0)) + 1:max(line_start - 1, 0)]
    below_start = output.find("\n", end)
    below = "" if below_start < 0 else output[below_start + 1:output.find("\n", below_start + 1)
                                              if output.find("\n", below_start + 1) >= 0 else len(output)]
    if line_start > 0 and _JUDGE_ROLE_ALONE.fullmatch(above):
        return True
    if below_start >= 0 and _JUDGE_ROLE_ALONE.fullmatch(below):
        return True
    return bool(_JUDGE_TITLE.match(title)
                and judges & {t.casefold() for t in re.findall(r"\p{L}{3,}", output[start:end])})


def verify(
    output: str,
    *,
    protected_spans: Iterable[tuple[int, int]] = (),
    expected_aliases: Iterable[str] = (),
    replacements: int = 0,
    warnings: Iterable[str] = (),
    dismissed_spans: Iterable[tuple[int, int]] = (),
) -> Verification:
    """Return residual findings in output coordinates without modifying ``output``."""
    protected = tuple(protected_spans)
    dismissed = set(dismissed_spans)
    findings: dict[tuple[int, int, str], ResidualFinding] = {}

    def add(start: int, end: int, kind: str, source: str, reason: str) -> None:
        if (start, end) in dismissed:
            return
        # Only a person finding wholly inside an accepted public-role span is exempt.
        # Structured PII must never be hidden by partial overlap with a kept case id.
        if kind == "PERSON" and _contained((start, end), protected):
            return
        text = output[start:end]
        if not text or re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ]+_\d+", text):
            return
        findings[(start, end, kind)] = ResidualFinding(
            start=start,
            end=end,
            text=text,
            kind=kind,
            source=source,
            reason=reason,
        )

    # Structured detectors are deterministic and independent of person seeding.
    for label, pattern, group in P.STRUCTURED:
        check = P.STRUCTURED_CHECKS.get(label, bool)
        for match in pattern.finditer(output):
            if not check(match.group(0).strip()):
                continue
            index = 1 if group and match.lastindex else 0
            if group and match.lastindex:
                index = next(
                    (i for i in range(1, match.lastindex + 1)
                     if match.group(i) is not None),
                    0,
                )
            add(match.start(index), match.end(index), label.upper(),
                "verification:structured", f"residual {label}")

    # Deliberately broader than the conservative primary regex seeder.
    for match in _PRIVATE_PERSON_CUE.finditer(output):
        value = match.group(1)
        if P.INSTITUTION_HEAD.search(value) or P.ORG_HEAD.search(value):
            continue
        tokens = [token.casefold().strip(".,;:") for token in value.split()]
        if value.isupper() and any(
            token in P.SECTION_HEADING_TOKENS for token in tokens
        ):
            continue
        add(match.start(1), match.end(1), "PERSON", "verification:private-role",
            "person-like text remains after a private-party cue")

    # Review-only high-recall scan. Unlike the primary seeder it needs no legal cue:
    # any remaining 2–4-token capitalized phrase is surfaced for inspection. This
    # intentionally accepts false alarms; it never rewrites text.
    for match in _POSSIBLE_PERSON.finditer(output):
        value = match.group(1)
        if _ALREADY_ANONYMIZED.search(value):
            continue
        # FULL_NAME stops at the underscore in a generated tag and can otherwise read
        # "La Ricorrente_1" as the two-token name "La Ricorrente".
        if re.match(r"(?:_\p{L}+)*_\d+", output[match.end(1):]):
            continue
        if (P.INSTITUTION_HEAD.search(value) or P.ORG_HEAD.search(value)
                or P.COMPANY_SUFFIX_RE.search(value) or P.STREET_HEAD.match(value)
                or _not_a_name(value, output, match.end(1))):
            continue
        tokens = [token.casefold().strip(".,;:") for token in value.split()]
        if value.isupper() and any(
            token in P.SECTION_HEADING_TOKENS for token in tokens
        ):
            continue
        add(match.start(1), match.end(1), "PERSON", "verification:name-shape",
            "unresolved capitalized name candidate")

    # A title or trade and the words after it, still in clear: a surname or a name is what
    # follows nine times out of ten, and the patterns that replace it may have refused it
    # (a common word such as "Casa", a first name alone). Not when the words are an adjective
    # of the role, nor when the name is probably a judge's.
    judges = {token.casefold() for start, end in protected
              for token in re.findall(r"\p{L}{3,}", output[start:end])}
    for match in _TITLE_NAME.finditer(output):
        if re.match(r"(?:_\p{L}+)*_\d+", output[match.end(1):]):
            continue
        if _ALREADY_ANONYMIZED.search(match.group(1)) or P.ROLE_ADJECTIVE_AT.match(match.group(1)):
            continue
        # The name ends where a role or a heading word begins ("Mario Verdi Presidente").
        end = match.end(1)
        for word in re.finditer(r"\S+", match.group(1)):
            if word.group(0).casefold().strip(".,;:") in _closed_words() | P.SECTION_HEADING_TOKENS:
                end = match.start(1) + word.start()
                break
        start = match.start(1)
        end = start + len(output[start:end].rstrip())
        if end <= start or _judge_like(output, start, end, match.group(0), judges):
            continue
        if any(kind == "PERSON" and other < end and start < stop
               for other, stop, kind in findings):
            continue                          # already reported, and as what it looks like
        add(start, end, "PERSON", "verification:title-name",
            "capitalised word after a title or a trade")

    # A known entity alias surviving the rewrite is always worth review. Exact judicial
    # spans are excluded above, which handles a party sharing a surname with a judge.
    for alias in sorted(set(expected_aliases), key=len, reverse=True):
        if len(alias.strip()) < 3:
            continue
        for match in _whole_value(alias).finditer(output):
            add(match.start(), match.end(), "PERSON", "verification:alias",
                "alias of an entity selected for redaction remains")

    words = output.count(" ") + 1
    pre_anonymized = len(_ALREADY_ANONYMIZED.findall(output)) >= 3
    if words > 300 and replacements == 0 and not pre_anonymized:
        findings[(0, 0, "DOCUMENT")] = ResidualFinding(
            start=0,
            end=0,
            text="",
            kind="DOCUMENT",
            source="verification:coverage",
            reason="long document contains no detected removable entity",
        )

    warning_tuple = tuple(dict.fromkeys(warnings))
    residuals = tuple(sorted(findings.values(), key=lambda item: (item.start, item.end)))
    status = "needs_review" if residuals or warning_tuple else "passed_checks"
    return Verification(status=status, residuals=residuals, warnings=warning_tuple)
