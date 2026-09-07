"""The optional NER path.

Split in two. The windowing and merging logic is pure text handling and is tested
directly — it needs no model and runs everywhere. The end-to-end behaviour needs a
downloaded model, so it is skipped when one is not cached; the properties it checks
are the ones needed to evaluate whether NER is an acceptable trade-off.
"""
import pytest

from pseudonimizzatore_legale import Config, anonymize
from pseudonimizzatore_legale import ner

MODEL = "DeepMount00/Italian_NER_XXL_v2"


def _model_available() -> bool:
    if not ner.available():
        return False
    from huggingface_hub import snapshot_download
    try:
        snapshot_download(MODEL, local_files_only=True)
        return True
    except Exception:                                # noqa: BLE001 — absence, not error
        return False


needs_model = pytest.mark.skipif(
    not _model_available(), reason=f"{MODEL} is not in the Hugging Face cache")


class TestWindows:
    """Chunking must cover the text without losing the offsets into it."""

    def test_short_text_is_one_window_at_offset_zero(self):
        assert ner._windows("breve", 1400, 200) == [(0, "breve")]

    def test_windows_cover_the_whole_text(self):
        text = " ".join(f"parola{i}" for i in range(400))
        windows = ner._windows(text, 200, 40)
        assert len(windows) > 1
        # Every character belongs to at least one window, at the right offset.
        covered = set()
        for offset, chunk in windows:
            assert text[offset:offset + len(chunk)] == chunk
            covered.update(range(offset, offset + len(chunk)))
        assert covered == set(range(len(text)))

    def test_windows_overlap_so_a_boundary_name_survives(self):
        text = "x" * 500
        windows = ner._windows(text, 200, 50)
        starts = [o for o, _ in windows]
        ends = [o + len(c) for o, c in windows]
        assert all(starts[i + 1] < ends[i] for i in range(len(windows) - 1))


class TestMergeAdjacent:
    """`NOME` + `COGNOME` are one person; two names on separate lines are two."""

    @staticmethod
    def _m(text, start, end, role="Nominativo"):
        return ner.Mention(text=text[start:end], start=start, end=end,
                           role=role, score=0.9)

    def test_given_and_family_name_are_joined(self):
        text = "Mario Rossi"
        merged = ner._merge_adjacent(
            [self._m(text, 0, 5), self._m(text, 6, 11)], text)
        assert [m.text for m in merged] == ["Mario Rossi"]

    def test_a_line_break_keeps_two_people_apart(self):
        text = "Mario Rossi\nLucia Bianchi"
        merged = ner._merge_adjacent(
            [self._m(text, 0, 11), self._m(text, 12, 25)], text)
        assert [m.text for m in merged] == ["Mario Rossi", "Lucia Bianchi"]

    def test_a_specific_role_survives_the_merge(self):
        text = "Paolo Neri"
        merged = ner._merge_adjacent(
            [self._m(text, 0, 5, "Difensore"), self._m(text, 6, 10)], text)
        assert merged[0].role == "Difensore"


class TestConfig:
    """NER is off unless asked for, and the flag reaches the backend by name."""

    def test_off_by_default(self):
        assert Config().ner is None

    def test_model_id_is_carried_on_the_config(self):
        assert Config(ner=MODEL).ner == MODEL

    def test_model_ensemble_is_carried_on_the_config(self):
        models = (MODEL, "Davlan/xlm-roberta-base-ner-hrl")
        assert Config(ner=models).ner == models

    def test_empty_model_ensemble_is_rejected(self):
        with pytest.raises(ValueError, match="must not be empty"):
            Config(ner=())

    def test_ensemble_unions_mentions_from_each_model(self, monkeypatch):
        text = "Antonio De Luca parla con Giulia Bianchi."
        mentions = {
            "model-a": ner.Mention("Antonio De Luca", 0, 15, "Nominativo", 0.9),
            "model-b": ner.Mention("Giulia Bianchi", 26, 40, "Nominativo", 0.9),
        }

        class Backend:
            def __init__(self, mention):
                self.mention = mention

            def find_people(self, _text):
                return [self.mention]

        monkeypatch.setattr(
            ner,
            "get_backend",
            lambda model_id, _device, _threshold: Backend(mentions[model_id]),
        )
        out, _ = anonymize(text, ner=("model-a", "model-b"))
        assert "Antonio De Luca" not in out
        assert "Giulia Bianchi" not in out


@needs_model
class TestEndToEnd:
    """What NER is for, and what it must not break."""

    def test_finds_a_name_no_anchor_announces(self):
        text = "Antonio De Luca contesta l'avviso di accertamento."
        plain, _ = anonymize(text)
        with_ner, report = anonymize(text, ner=MODEL)
        assert "Antonio De Luca" in plain          # the regex layer cannot see it
        assert "Antonio De Luca" not in with_ner
        assert "Antonio De Luca" in report.mapping

    def test_exact_judicial_role_span_wins_late_policy(self):
        text = ("Presidente: CATALDI MICHELE\n"
                "Il contribuente Antonio De Luca ricorre avverso l'avviso.")
        out, report = anonymize(text, ner=MODEL)
        assert "CATALDI MICHELE" in out            # NER proposes it; late policy keeps it
        assert "Antonio De Luca" not in out

    def test_institutions_are_not_pseudonymized(self):
        text = "Il ricorso di Antonio De Luca contro l'Agenzia delle Entrate."
        out, _ = anonymize(text, ner=MODEL)
        assert "Agenzia delle Entrate" in out

    def test_one_person_keeps_one_tag(self):
        text = ("Il contribuente Antonio De Luca ha presentato ricorso. "
                "De Luca lamenta la nullità dell'atto.")
        out, report = anonymize(text, ner=MODEL)
        tags = set(report.mapping.values())
        assert len(tags) == 1, report.mapping
        assert "De Luca" not in out
