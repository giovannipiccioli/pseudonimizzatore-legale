"""Put the originals back into a text written with the tags.

A pseudonymized document can go to a service that must not learn who is involved, a
language model for example, and come back as new text: a summary, a draft, an answer.
That text still says `Nominativo_1`. `restore` replaces each tag with the original it
stands for, read from the review state of the run that made the tags:

    output, report = anonymize(source)
    draft = ...                                   # new text that uses the tags
    text, restoration = restore(draft, report.state)

The state is the whole key. The engine keeps nothing, so whoever holds the state can
restore and nobody else can: store it like the source document. A state carried from
one document to the next restores every document that shares its tags.

The original of a tag is

- for a person, one spelling for all the forms that share the tag: the row's `name`,
  or, when the name is in capitals (`MALASPINA FERRUCCIO`, from a heading), the first
  alias that is not (`Ferruccio Malaspina`). A bare `il Malaspina` comes back as the
  full spelling;
- for a datum, the row's `value`;
- for a passage redacted on its own, the quoted passage.

A tag is read as a whole word, so `Nominativo_1` is never found inside
`Nominativo_12`, in any letter case, and with the `\\_` that Markdown writers put for
an underscore. A tag written in capitals, as in a heading, gets its original in
capitals. Nothing else changes: an article or an agreement written for the tag (`il
Nominativo_1` about a woman) stays as the writer left it.

A word shaped like a tag that the state does not know, such as a `Nominativo_9` the
writer invented, stays in place and is listed in `unknown` for review.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import regex as re

from .constraints import ReviewState
from .labels import RESERVED

# A tag stands alone: no letter or digit touches it, directly or across an underscore,
# so `X_Nominativo_1` and `Nominativo_1_bis` are not tags, while `_Nominativo_1_`
# (Markdown italics) is.
_BEFORE = r"(?<![\p{L}\p{N}](?:\\?_)?)"
_AFTER = r"(?!(?:\\?_)?[\p{L}\p{N}])"


@dataclass
class Restoration:
    """What `restore` did: the tags it replaced, and tag-shaped words it did not know.

    `restored` counts the replacements per tag, in the order the tags first appear.
    `unknown` lists each unrecognised tag once, as written (with `_` for `\\_`).
    """

    restored: dict[str, int] = field(default_factory=dict)
    unknown: list[str] = field(default_factory=list)


def _originals(state: dict) -> dict[str, str]:
    """Every tag the state assigned, with the original text it replaced."""
    content = ReviewState(state).content          # validates the state as `analyze` does
    originals = {}
    for row in content["people"]:
        if "placeholder" in row:
            # A heading's `MALASPINA FERRUCCIO` may be the name; prose wants the body's
            # spelling when the source has one.
            spellings = [row["name"], *row.get("aliases", [])]
            originals[row["placeholder"]] = next(
                (s for s in spellings if not s.isupper()), row["name"])
    for row in content["data"]:
        if "placeholder" in row:
            originals[row["placeholder"]] = row["value"]
    for choice in content["occurrences"]:
        if "placeholder" in choice:
            originals[choice["placeholder"]] = choice["anchor"]["quote"]
    return originals


def _spelled(tag: str) -> str:
    """A pattern for a tag whose underscores may be written `\\_`."""
    return r"\\?_".join(re.escape(part) for part in tag.split("_"))


def restore(text: str, state: dict) -> tuple[str, Restoration]:
    """Replace the tags in `text` with the originals recorded in `state`.

    `state` is a `Report.state` (or `Analysis.state`), as returned or as saved to JSON
    and loaded again. Returns the restored text and a `Restoration`.

    >>> from pseudonimizzatore_legale import anonymize
    >>> output, report = anonymize("Il sig. Mario Rossi, C.F. RSSMRA80A01H501U, ricorre.")
    >>> restore("Nominativo_1 (CF_1) ha ragione.", report.state)[0]
    'Mario Rossi (RSSMRA80A01H501U) ha ragione.'
    """
    originals = _originals(state)
    folded = {tag.casefold(): tag for tag in originals}
    prefixes = set(RESERVED)
    prefixes.update(re.sub(r"_\d+$", "", tag) for tag in originals if re.search(r"_\d+$", tag))
    shapes = [_spelled(tag) for tag in sorted(originals, key=len, reverse=True)]
    shapes.append("(?:" + "|".join(_spelled(p) for p in sorted(prefixes, key=len, reverse=True))
                  + r")\\?_\d+")
    pattern = re.compile(_BEFORE + "(?:" + "|".join(shapes) + ")" + _AFTER, re.IGNORECASE)

    restored: Counter = Counter()
    unknown: list[str] = []

    def substitute(match: re.Match) -> str:
        written = match[0].replace("\\_", "_")
        tag = written if written in originals else folded.get(written.casefold())
        if tag is None:
            if written not in unknown:
                unknown.append(written)
            return match[0]
        restored[tag] += 1
        original = originals[tag]
        return original.upper() if written.isupper() and not tag.isupper() else original

    result = pattern.sub(substitute, text)
    return result, Restoration(restored=dict(restored), unknown=unknown)
