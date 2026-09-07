"""Optional transformer NER — an extra *seed source*, not a second pipeline.

Everything the regex layer does rests on anchors: a title, a codice fiscale next door,
a party block. That works because court documents are structured, and it fails exactly
where they are not — a name introduced by nothing at all:

    "Antonio De Luca contesta l'avviso"                        ← no cue, invisible

A NER model has no such requirement. Turning it on adds a detector that reads the
sentence rather than the layout.

**It is deliberately wired in as a seed source and nothing more.** NER proposes people;
everything downstream is shared with the regex path:

* **late policy resolves public roles** — an exact judge span can be kept without
  globally suppressing a different party who has the same surname;
* the **bare-token common-word guard still applies** — an exact multi-token model
  mention may be removed, but an ordinary word cannot propagate across the document;
* **propagation still runs**, so one NER hit on "Antonio De Luca" also catches the bare
  "De Luca" twelve lines later that the model itself may have missed;
* **span resolution is unchanged**, so a NER proposal competes with the others by
  priority and length instead of overwriting them.

The cost is substantial and hardware/model dependent, which is why it is off by
default. See the evaluation report for measured recall and precision before choosing a
model.

    from pseudonimizzatore_legale import anonymize
    anonymize(text, ner="Babelscape/wikineural-multilingual-ner")
    anonymize(text, ner=("DeepMount00/Italian_NER_XXL_v2",
                         "Davlan/xlm-roberta-base-ner-hrl"),
              ner_threshold=0.3)  # union detections when recall dominates runtime

`transformers` and `torch` are imported lazily, so the base library keeps its single
dependency. Install them with::

    pip install "pseudonimizzatore-legale[ner]"
"""
from __future__ import annotations

from functools import lru_cache

import regex as re

from .model import Mention

#: Entity labels that mean "a natural person", across the models worth using.
#: Italian_NER_XXL_v2 splits a full name into NOME + COGNOME and has a dedicated class
#: for counsel and notaries; the generic multilingual models emit a single PER.
PERSON_LABELS = frozenset({
    "PER", "PERSON", "PERSONA",          # generic multilingual taggers
    "NOME", "COGNOME",                   # Italian_NER_XXL_v2 splits names in two
    "AVV_NOTAIO",                        # …and knows counsel from other people
})

#: Labels that additionally tell us *which role* the person plays. Everything else
#: defaults to "Nominativo" — NER reads sentences, not procedural posture.
ROLE_BY_LABEL = {"AVV_NOTAIO": "Difensore"}

#: Below this the model is guessing. Tuned on the evaluation corpus: lower and ordinary
#: capitalised words start arriving, higher and genuine names in odd layouts drop out.
DEFAULT_THRESHOLD = 0.60

#: Long documents must be chunked — BERT tops out at 512 word pieces. Windows are
#: measured in characters (cheap, and close enough) and overlap so that a name landing
#: on a boundary is still seen whole by the neighbouring window.
#:
#: 1400 is not a round number picked for comfort: over 884 windows of real Cassazione
#: text it gives a median of 302 word pieces and a **maximum of 481**, just inside the
#: limit. Raising it would buy throughput — fewer forward passes per document — at the
#: cost of silent truncation, which the pipeline does not warn about: the tail of an
#: over-long window is simply dropped, and any name in it is never seen.
DEFAULT_WINDOW = 1400
DEFAULT_OVERLAP = 200


def _normalise(label: str) -> str:
    return label.upper().removeprefix("B-").removeprefix("I-")


def _windows(text: str, size: int, overlap: int) -> list[tuple[int, str]]:
    """Split into overlapping windows, preferring whitespace boundaries."""
    if len(text) <= size:
        return [(0, text)]
    out, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind(" ", start + size // 2, end)
            if cut > start:
                end = cut
        out.append((start, text[start:end]))
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return out


def _merge_adjacent(mentions: list[Mention], text: str) -> list[Mention]:
    """Join `NOME` + `COGNOME` (and any touching person spans) into one name.

    Models that tag given and family names separately would otherwise hand us two
    one-token seeds instead of one person, which propagates worse and reads worse in
    the report.
    """
    if not mentions:
        return []
    mentions = sorted(mentions, key=lambda m: (m.start, m.end))
    merged = [mentions[0]]
    for m in mentions[1:]:
        prev = merged[-1]
        gap = text[prev.end:m.start]
        # Only whitespace between them, and no line break — a name does not span a
        # paragraph, and two names on consecutive lines are two people.
        if m.start >= prev.end and gap.strip() == "" and "\n" not in gap and len(gap) <= 2:
            merged[-1] = Mention(
                text=text[prev.start:m.end], start=prev.start, end=m.end,
                # a specific role (counsel) survives a merge with a generic one
                role=prev.role if prev.role != "Nominativo" else m.role,
                score=min(prev.score, m.score),
                source=prev.source if prev.source != "regex" else m.source)
        elif m.start >= prev.end:
            merged.append(m)
        # else: overlapping, keep the first (windows already deduplicated)
    return merged


class NerBackend:
    """A loaded token-classification model, ready to find people in text."""

    def __init__(self, model_id: str, *, device: str | None = None,
                 threshold: float = DEFAULT_THRESHOLD,
                 window: int = DEFAULT_WINDOW, overlap: int = DEFAULT_OVERLAP,
                 batch_size: int = 8):
        from transformers import pipeline           # lazy: keeps torch optional

        self.model_id = model_id
        self.threshold = threshold
        self.window = window
        self.overlap = overlap
        self.batch_size = batch_size
        self._pipe = pipeline(
            "token-classification", model=model_id,
            aggregation_strategy="simple",          # merge word pieces into words
            device=self._resolve_device(device),
        )

    @staticmethod
    def _resolve_device(device: str | None) -> int | str:
        if device is not None:
            return device
        try:
            import torch
            if torch.backends.mps.is_available():
                return "mps"
        except Exception:
            pass
        return -1                                    # CPU

    def find_people(self, text: str) -> list[Mention]:
        """Every natural person the model finds, as character spans into `text`."""
        if not text.strip():
            return []
        windows = _windows(text, self.window, self.overlap)
        results = self._pipe([w for _, w in windows], batch_size=self.batch_size)
        if windows and isinstance(results, list) and results and isinstance(results[0], dict):
            results = [results]                      # single window: pipeline unwraps

        seen: dict[tuple[int, int], Mention] = {}
        for (offset, _), entities in zip(windows, results):
            for ent in entities:
                label = _normalise(ent.get("entity_group") or ent.get("entity", ""))
                if label not in PERSON_LABELS or ent["score"] < self.threshold:
                    continue
                start, end = offset + ent["start"], offset + ent["end"]
                surface = text[start:end]
                if not surface.strip():
                    continue
                # Overlapping windows see the same name twice; keep the better score.
                key = (start, end)
                prev = seen.get(key)
                if prev is None or ent["score"] > prev.score:
                    seen[key] = Mention(
                        text=surface, start=start, end=end,
                        role=ROLE_BY_LABEL.get(label, "Nominativo"),
                        score=float(ent["score"]), source=f"ner:{self.model_id}")
        return _merge_adjacent(list(seen.values()), text)


@lru_cache(maxsize=4)
def get_backend(model_id: str, device: str | None = None,
                threshold: float = DEFAULT_THRESHOLD) -> NerBackend:
    """Load (and cache) a backend. Loading costs seconds; reuse it across documents."""
    return NerBackend(model_id, device=device, threshold=threshold)


def available() -> bool:
    """True if the optional NER dependencies are installed."""
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False
