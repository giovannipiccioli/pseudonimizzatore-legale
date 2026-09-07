"""Text normalization that must happen *before* detection.

Court text arrives through PDF extraction, OCR and markdown conversion, and each of
those fragments names in its own way: a soft hyphen inside "Ros-si", a zero-width space
left by a converter, `**Mario** Rossi`, a full-width character from a bad encoding.
Every one defeats an exact-match detector — the name is still legible to a human and
invisible to a regex — so they are repaired first.

**This step changes offsets**, deliberately. The pipeline works on the sanitized text
from here on and never maps back, which is why `anonymize()` returns sanitized-and-
substituted text rather than a patched copy of the original. If you need the original
bytes preserved exactly, pass `sanitize=False` and accept the lower recall.
"""
import html
import unicodedata

import regex as re

#: Zero-width and invisible characters used (accidentally or not) to split words.
_ZERO_WIDTH = re.compile(r"[​‌‍⁠﻿­]")
_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n|\A\+\+\+\n.*?\n\+\+\+\n", re.S)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
#: The delimiter may not reappear inside the span: without that, a run of scan noise
#: like "Rep. _____" or "****" reads as nested emphasis and collapses to one character.
_MD_EMPHASIS_STAR = re.compile(r"(\*\*|\*|`)([^*`]+?)\1")
#: Underscore emphasis requires word boundaries — that is what CommonMark says, and it
#: is also what stops this pass from eating the underscores in our own output tags:
#: `Resistente_1 … Difensore_1` on one line otherwise reads as `_…_` emphasis and comes
#: back as `Resistente1 … Difensore1`, so a second pass over an already-processed file
#: silently corrupted it.
_MD_EMPHASIS_UNDERSCORE = re.compile(
    r"(?<![\p{L}\p{N}])(__|_)([^_]+?)\1(?![\p{L}\p{N}])")
_MD_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.M)
_MD_QUOTE = re.compile(r"^[ \t]*>[ \t]?", re.M)
#: "Ma-\nrio" → "Mario"; typographic hyphenation at end of line.
_HYPHEN_WRAP = re.compile(r"(\p{L})-\n(\p{Ll})")
#: A line opening with a dash is a procedural role marker (" -controricorrente-"), not
#: a hyphenated word, and joining it swallows the line break after it.
_DASH_MARKER_LINE = re.compile(r"^[^\S\r\n]*[-–]")
#: A pipe between two letters is almost always an OCR'd "l".
_OCR_PIPE = re.compile(r"(?<=\p{L})\|(?=\p{L})")


def sanitize(raw: str) -> str:
    """Normalise `raw` so that entity detection sees whole words.

    Order matters: entity decoding can introduce zero-width characters, so it runs
    before the strip; emphasis removal runs after tag removal so `<b>Ma</b>rio` and
    `**Ma**rio` both collapse.
    """
    s = unicodedata.normalize("NFKC", raw)
    s = html.unescape(s)
    s = _ZERO_WIDTH.sub("", s)
    s = _OCR_PIPE.sub("l", s)
    s = _dehyphenate(s)
    s = _FRONTMATTER.sub("", s)
    s = _HTML_COMMENT.sub("", s)
    s = _HTML_TAG.sub("", s)
    s = _MD_IMAGE.sub(r"\1", s)
    s = _MD_LINK.sub(r"\1", s)
    s = _MD_EMPHASIS_STAR.sub(r"\2", s)
    s = _MD_EMPHASIS_UNDERSCORE.sub(r"\2", s)
    s = _MD_HEADING.sub("", s)
    s = _MD_QUOTE.sub("", s)
    return s


def _dehyphenate(s: str) -> str:
    """Join words split by typographic hyphenation, leaving role markers alone."""
    def repl(m: re.Match) -> str:
        line_start = s.rfind("\n", 0, m.start()) + 1
        if _DASH_MARKER_LINE.match(s, line_start):
            return m.group(0)
        return m.group(1) + m.group(2)

    return _HYPHEN_WRAP.sub(repl, s)


#: Typographic variants that stop an entity from matching its own occurrence.
_QUOTE_MAP = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
})


def normalize_quotes(s: str) -> str:
    """Fold curly quotes to ASCII so "D'Angelo" and "D’Angelo" compare equal."""
    return s.translate(_QUOTE_MAP)
