"""What `Config(initials=...)` must never do, checked on every fixture of the corpus.

The option adds one kind of decision and nothing else. These properties are what the
feature has to keep as the patterns, the sigle and the other detectors change:

* off, no decision comes from the initials detector;
* on, every other decision is the one the library takes without the option;
* the prudent reading takes a subset of what the everywhere reading takes;
* no annotated value is lost or newly leaked, in either reading;
* a sigla of `resources/sigle.json` is never touched, whatever stands around it;
* the output holds no initials to take again.

The last group runs the same checks on text assembled from invented parts, so a rule
changed for one fixture is tried on shapes the fixtures do not have.
"""
import dataclasses
import json
import random
from pathlib import Path

import pytest

from pseudonimizzatore_legale import Config, analyze, anonymize, render, seeds
from evaluation.metrics import score_output

CORPUS = Path(__file__).resolve().parent.parent / "evaluation" / "corpus"
GOLDS = sorted(CORPUS.rglob("*.gold.json"))


def initials_decisions(analysis):
    return [d for d in analysis.decisions if d.source.startswith("regex:initials")]


def shape(analysis):
    """The decisions without the tag numbers, which a new person shifts."""
    return [(d.start, d.end, d.kind, d.source, d.action) for d in analysis.decisions
            if not d.source.startswith("regex:initials")]


class Fixture:
    """One corpus document analysed with the option off, prudent and everywhere."""

    def __init__(self, gold_path):
        self.gold = json.loads(gold_path.read_text(encoding="utf-8"))
        self.raw = gold_path.with_suffix("").with_suffix(".txt").read_text(encoding="utf-8")
        base = Config(**self.gold.get("config", {}))
        self.analyses, self.outputs, self.scores = {}, {}, {}
        for name, value in (("off", False), ("on", True), ("all", "all")):
            analysis = analyze(self.raw, dataclasses.replace(base, initials=value))
            output, report = render(analysis)
            self.analyses[name], self.outputs[name] = analysis, output
            self.scores[name] = score_output(analysis.text, output, self.gold,
                                             report.replacement_spans)


@pytest.fixture(scope="module")
def fixtures():
    cache = {}

    def get(gold_path):
        if gold_path not in cache:
            cache[gold_path] = Fixture(gold_path)
        return cache[gold_path]
    return get


def ids(paths):
    return [str(p.relative_to(CORPUS)).removesuffix(".gold.json") for p in paths]


@pytest.mark.parametrize("gold_path", GOLDS, ids=ids(GOLDS))
class TestCorpusFixtures:
    def test_off_has_no_initials_decision(self, fixtures, gold_path):
        assert initials_decisions(fixtures(gold_path).analyses["off"]) == []

    def test_on_changes_nothing_but_initials(self, fixtures, gold_path):
        f = fixtures(gold_path)
        assert shape(f.analyses["on"]) == shape(f.analyses["off"])
        assert shape(f.analyses["all"]) == shape(f.analyses["off"])

    def test_prudent_is_inside_everywhere(self, fixtures, gold_path):
        f = fixtures(gold_path)
        prudent = {(d.start, d.end) for d in initials_decisions(f.analyses["on"])}
        everywhere = {(d.start, d.end) for d in initials_decisions(f.analyses["all"])}
        assert prudent <= everywhere

    @pytest.mark.parametrize("reading", ["on", "all"])
    def test_no_annotated_value_is_lost_or_newly_leaked(self, fixtures, gold_path, reading):
        f = fixtures(gold_path)
        assert set(f.scores[reading].lost) <= set(f.scores["off"].lost)
        assert set(f.scores[reading].leaked) <= set(f.scores["off"].leaked)

    @pytest.mark.parametrize("reading", ["on", "all"])
    def test_the_output_holds_no_initials_to_take_again(self, fixtures, gold_path, reading):
        f = fixtures(gold_path)
        again = analyze(f.outputs[reading], dataclasses.replace(
            Config(**f.gold.get("config", {})), initials="all" if reading == "all" else True))
        assert initials_decisions(again) == []


#: What the prudent reading takes in the corpus, read by hand: every entry is a party or a
#: minor ("la minore R.M."), and no fixture outside the table has a person written as
#: initials behind a cue. A fixture rebuild changes the letters: re-derive the table by
#: reading the new output, and never delete a failing entry to get a green run.
TAKEN = {
    "cassazione/15_auto_2018_17478PEN": ["A.M."],
    "cassazione/16_auto_2018_31785CIV": ["C.G.", "C.G.", "C.G."],
    "cassazione/27_auto_2023_19890CIV": ["R.S.", "R.M.", "R.M.", "R.M.", "R.S.", "R.S.", "R.S.",
                                         "R.M.", "R.M."],
    "corte_conti/13_auto_2003__1000sgcal": ["F. M", "F. M."],
    "corte_conti/14_auto_2003__1095sgcal": ["M. A. G."],
    "corte_conti/18_auto_2016_6_1000app2": ["G. N.", "G. N."],
    "corte_conti/21_auto_2019_19_100app2": ["A. B.", "A. B."],
}


@pytest.mark.parametrize("gold_path", GOLDS, ids=ids(GOLDS))
def test_the_prudent_reading_takes_these_initials_in_the_corpus(fixtures, gold_path):
    name = ids([gold_path])[0]
    taken = [d.text for d in initials_decisions(fixtures(gold_path).analyses["on"])]
    assert taken == TAKEN.get(name, [])


# ── the sigle ───────────────────────────────────────────────────────────────

SIGLE = sorted(seeds.sigle())

#: A sigla in the shapes it shows up in. The last two stand behind a cue and in a list.
SIGLA_CONTEXTS = [
    "Il {s} ha concluso per il rigetto.",
    "ai sensi del {s} n. 5 del 2000 e dell'art. 3",
    "Cass., {s}, n. 186 del 1987",
    "ricorso proposto da {s} avverso la sentenza",
    "nei confronti di {s} e di altri",
    "difeso dall'avv. {s}, con studio in Roma",
]


@pytest.mark.parametrize("sigla", SIGLE)
def test_a_listed_sigla_is_never_touched(sigla):
    for template in SIGLA_CONTEXTS:
        text = template.format(s=sigla)
        baseline = anonymize(text, Config())[0]
        assert anonymize(text, Config(initials=True))[0] == baseline, text
        assert anonymize(text, Config(initials="all"))[0] == baseline, text


# ── text assembled from invented parts ──────────────────────────────────────

#: Sentences without a person or a sigla in them.
FILLER = [
    "La Corte ha esaminato il motivo e lo ritiene infondato.",
    "Il giudice di merito ha accertato i fatti con motivazione adeguata.",
    "Il termine per impugnare decorre dalla notificazione della sentenza.",
    "Le spese seguono la soccombenza e sono liquidate come in dispositivo.",
    "Secondo il consolidato orientamento, la censura non coglie la ratio decidendi.",
]

#: The shapes that name a person by initials; `{a}` is where they stand.
CUED = [
    "Il ricorso è proposto da {a} avverso la sentenza.",
    "Il ricorso è proposto nei confronti di {a}, che non si è costituito.",
    "La parte è difesa dall'avv. {a}, del foro di Roma.",
    "Il sig. {a} ha depositato memoria difensiva.",
    "{a}, nato a Torino il 12 marzo 1970, deduce un unico motivo.",
    "L'imputato {a} ricorre per cassazione.",
    "Gli eredi di {a} hanno resistito con controricorso.",
]

#: Initials of two letters, none of them a listed sigla.
LETTERS = sorted({f"{a}.{b}." for a in "BCDFGLMNRSTV" for b in "ABEGILMNOPRSTV"} - seeds.sigle())


def document(rng, k):
    """`k` cued sentences with the initials they name, between filler sentences."""
    chosen = rng.sample(LETTERS, k)
    lines = []
    for initials in chosen:
        lines += [rng.choice(FILLER), rng.choice(CUED).format(a=initials)]
    return "\n".join(lines + [rng.choice(FILLER)]), chosen


SEEDS = range(40)


@pytest.mark.parametrize("seed", SEEDS)
def test_every_cued_initials_goes_and_the_filler_stays(seed):
    rng = random.Random(seed)
    text, chosen = document(rng, rng.randint(1, 5))
    for config in (Config(initials=True), Config(initials="all")):
        result = anonymize(text, config)[0]
        for initials in chosen:
            assert initials not in result, (initials, result)
        for sentence in FILLER:
            assert result.count(sentence) == text.count(sentence)


@pytest.mark.parametrize("seed", SEEDS)
def test_the_option_adds_nothing_but_initials(seed):
    rng = random.Random(seed)
    text, _ = document(rng, rng.randint(1, 5))
    off, prudent, everywhere = (analyze(text, Config(initials=v)) for v in (False, True, "all"))
    assert shape(prudent) == shape(off) == shape(everywhere)
    assert {(d.start, d.end) for d in initials_decisions(prudent)} \
        <= {(d.start, d.end) for d in initials_decisions(everywhere)}


@pytest.mark.parametrize("seed", SEEDS)
def test_a_second_pass_finds_no_initials(seed):
    rng = random.Random(seed)
    text, _ = document(rng, rng.randint(1, 5))
    for config in (Config(initials=True), Config(initials="all")):
        once = anonymize(text, config)[0]
        assert initials_decisions(analyze(once, config)) == []


@pytest.mark.parametrize("seed", SEEDS)
def test_a_sigla_added_to_a_document_changes_nothing(seed):
    rng = random.Random(seed)
    text, _ = document(rng, rng.randint(1, 4))
    extra = rng.choice(SIGLA_CONTEXTS).format(s=rng.choice(SIGLE))
    for config in (Config(initials=True), Config(initials="all")):
        assert anonymize(text + "\n" + extra, config)[0] == \
            anonymize(text, config)[0] + "\n" + anonymize(extra, Config())[0]


#: Characters that make dotted capitals, cues, line ends and sentence ends.
ALPHABET = list("AGSTMR..   \n,;:()-/") + ["e ", "da ", "avv. ", "nei confronti di ",
                                           "proposto da ", "art. ", "n. 5 "]


@pytest.mark.parametrize("seed", range(30))
def test_random_text_never_breaks_the_pipeline(seed):
    rng = random.Random(1000 + seed)
    text = "".join(rng.choice(ALPHABET) for _ in range(400))
    for config in (Config(initials=True), Config(initials="all")):
        analysis = analyze(text, config)
        spans = sorted((d.start, d.end) for d in analysis.decisions)
        assert all(a < b for a, b in spans)
        assert all(spans[i][1] <= spans[i + 1][0] for i in range(len(spans) - 1))
        output, report = render(analysis)
        assert report.status in ("passed_checks", "needs_review")
        assert initials_decisions(analyze(output, config)) == []
