"""Second, independent check that no real person reached the committed fixtures.

`check_fixtures.py` is built on the same heuristics as the de-identifier, so it shares
its blind spots: a name made only of common words ("SALVO MICHELE", "Mario Di Carlo"),
a witness called by bare surname, a court clerk. About forty such names sat in committed
fixtures until this was run. It asks an Italian NER model instead and lists every
person it finds that is not an invented namebank identity.

    python ner_audit.py [path-substring]

Needs `transformers` and the model (downloaded once); a few minutes on CPU. The output
is a list to read by eye — case names ("sentenza Tomaszewska"), OCR debris and places
the model misreads come up too. Fix the fixture, or the builder, for every real name.
"""
import sys
from pathlib import Path

import regex as re

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))
import namebank as NB
from pseudonimizzatore_legale.ner import PERSON_LABELS

MODEL = "DeepMount00/Italian_NER_XXL_v2"
FIXTURES = HERE.parent / "corpus"

#: Titles and roles the model folds into a name span ("dott.ssa", "Consigliere Relatore").
TITLES = {"dott", "ssa", "avv", "avvocato", "avvocata", "prof", "sig", "notaio", "cons",
          "ref", "giudice", "presidente", "relatore", "consigliere", "estensore",
          "referendario", "procuratore", "generale", "sostituto", "segretario",
          "segretaria"}

INVENTED = set()
for _s, _f in NB.PEOPLE + NB.COUNSEL + NB.JUDGES:
    INVENTED |= {t.lower() for t in f"{_s} {_f}".split()}
for _c in NB.COMPANIES:
    INVENTED |= {t.lower() for t in _c.split()}


def invented(token):
    # the model often cuts a word in two: "tilde Pontremoli", "TENSIA"
    return token in TITLES or any(token in t for t in INVENTED)


def chunks(text, size=900):
    """Pieces short enough for the model, cut at a line break or else a space."""
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            cut = text.rfind("\n", start + size // 2, end)
            cut = cut if cut > 0 else text.rfind(" ", start + size // 2, end)
            end = cut if cut > 0 else end
        yield start, text[start:end]
        start = end


def people(pipe, text):
    """Character spans of every person the model finds, NOME + COGNOME joined."""
    spans = []
    for offset, piece in chunks(text):
        for e in pipe(piece):
            if (e.get("entity_group") or "").upper() in PERSON_LABELS and e["score"] >= 0.5:
                spans.append([offset + e["start"], offset + e["end"]])
    merged = []
    for s, e in sorted(spans):
        if merged and s - merged[-1][1] <= 2:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return merged


def main():
    from transformers import pipeline
    pipe = pipeline("token-classification", model=MODEL, aggregation_strategy="simple")
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    paths = sorted(p for p in FIXTURES.rglob("*.txt") if only in str(p))
    total = 0
    for path in paths:
        text = path.read_text(encoding="utf-8")
        found = {}
        for s, e in people(pipe, text):
            name = re.sub(r"\s+", " ", text[s:e]).strip(" ,.;:'’")
            tokens = [t.lower() for t in re.findall(r"\p{L}+", name) if len(t) >= 3]
            if tokens and not all(invented(t) for t in tokens):
                found.setdefault(name, text[max(0, s - 60):e + 30].replace("\n", " "))
        if found:
            print(f"\n{path.relative_to(FIXTURES)}")
            for name, context in found.items():
                print(f"   {name:30s} …{context}…")
            total += len(found)
    print(f"\n{total} person(s) outside the namebank across {len(paths)} fixtures")


if __name__ == "__main__":
    main()
