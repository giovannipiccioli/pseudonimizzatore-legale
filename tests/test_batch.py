"""Filesystem behavior of the public batch API."""
import json

import pytest

from pseudonimizzatore_legale import Config, anonymize_batch, anonymize_file


def test_file_sidecar_is_json_and_contains_verdict(tmp_path):
    source = tmp_path / "source.txt"
    destination = tmp_path / "output.txt"
    source.write_text(
        "La decisione riguarda Antonio De Luca senza altre indicazioni.",
        encoding="utf-8",
    )
    record = anonymize_file(str(source), str(destination), sidecar=True)
    sidecar = destination.with_suffix(".txt.map.json")
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert record["status"] == "needs_review"
    assert data["schema_version"] == 1
    assert data["status"] == "needs_review"
    assert data["residuals"][0]["text"] == "Antonio De Luca"
    assert data["source_sha256"]
    assert data["output_sha256"]
    assert data["engine_version"] == "0.3.0"
    assert data["config"]["verify"] is True


def test_resume_regenerates_a_requested_missing_sidecar(tmp_path):
    source_dir = tmp_path / "input"
    destination_dir = tmp_path / "output"
    source_dir.mkdir()
    destination_dir.mkdir()
    (source_dir / "case.txt").write_text(
        "Il sig. Mario Rossi ricorre.", encoding="utf-8"
    )
    (destination_dir / "case.txt").write_text("stale", encoding="utf-8")

    summary = anonymize_batch(
        source_dir, destination_dir, workers=1, sidecar=True, resume=True
    )
    assert summary["files"] == 1
    assert (destination_dir / "case.txt.map.json").exists()


def test_valid_sidecar_resume_skips_with_validation(tmp_path):
    source = tmp_path / "input"
    destination = tmp_path / "output"
    source.mkdir()
    (source / "case.txt").write_text("Il sig. Mario Rossi ricorre.", "utf-8")
    anonymize_batch(source, destination, workers=1, sidecar=True)
    summary = anonymize_batch(
        source, destination, workers=1, sidecar=True, resume=True
    )
    assert summary["files"] == 0
    assert summary["skipped"] == 1
    assert summary["unvalidated_skips"] == 0


def test_batch_summary_exposes_review_queue(tmp_path):
    source_dir = tmp_path / "input"
    destination_dir = tmp_path / "output"
    source_dir.mkdir()
    (source_dir / "case.txt").write_text(
        "La decisione riguarda Antonio De Luca senza altre indicazioni.",
        encoding="utf-8",
    )
    summary = anonymize_batch(source_dir, destination_dir, workers=1)
    assert summary["needs_review"] == 1
    assert summary["review_queue"][0]["residuals"] == 1


def test_batch_rejects_nested_destination(tmp_path):
    source_dir = tmp_path / "input"
    source_dir.mkdir()
    with pytest.raises(ValueError, match="disjoint"):
        anonymize_batch(source_dir, source_dir / "output", workers=1)


def test_file_rejects_in_place_overwrite(tmp_path):
    source = tmp_path / "case.txt"
    source.write_text("testo", encoding="utf-8")
    with pytest.raises(ValueError, match="must differ"):
        anonymize_file(source, source)


def test_batch_validates_source_and_workers(tmp_path):
    with pytest.raises(NotADirectoryError):
        anonymize_batch(tmp_path / "missing", tmp_path / "output")
    source = tmp_path / "input"
    source.mkdir()
    with pytest.raises(ValueError, match="positive"):
        anonymize_batch(source, tmp_path / "output", workers=0)


def test_unverified_batch_is_queued(tmp_path):
    source = tmp_path / "input"
    destination = tmp_path / "output"
    source.mkdir()
    (source / "case.txt").write_text("testo breve", encoding="utf-8")
    summary = anonymize_batch(
        source, destination, config=Config(verify=False), workers=1
    )
    assert summary["needs_review"] == 0
    assert summary["unverified"] == 1
    assert summary["review_queue"][0]["status"] == "not_run"


def test_empty_resume_keeps_the_summary_schema(tmp_path):
    source = tmp_path / "input"
    destination = tmp_path / "output"
    source.mkdir()
    (source / "case.txt").write_text("testo breve", encoding="utf-8")
    anonymize_batch(source, destination, workers=1)
    summary = anonymize_batch(source, destination, workers=1, resume=True)
    assert summary["files"] == 0
    assert summary["skipped"] == 1
    assert summary["unvalidated_skips"] == 1
    assert summary["errors"] == 0
    assert summary["review_queue"] == []


def test_stale_sidecar_is_regenerated_after_config_change(tmp_path):
    source = tmp_path / "input"
    destination = tmp_path / "output"
    source.mkdir()
    (source / "case.txt").write_text("La Alfa S.r.l. ricorre.", encoding="utf-8")
    anonymize_batch(source, destination, workers=1, sidecar=True)
    summary = anonymize_batch(
        source,
        destination,
        config=Config(companies=True),
        workers=1,
        sidecar=True,
        resume=True,
    )
    assert summary["files"] == 1
    data = json.loads((destination / "case.txt.map.json").read_text("utf-8"))
    assert data["config"]["companies"] is True


def test_tampered_sidecar_backed_output_is_regenerated(tmp_path):
    source = tmp_path / "input"
    destination = tmp_path / "output"
    source.mkdir()
    (source / "case.txt").write_text("Il sig. Mario Rossi ricorre.", encoding="utf-8")
    anonymize_batch(source, destination, workers=1, sidecar=True)
    (destination / "case.txt").write_text("tampered", encoding="utf-8")
    summary = anonymize_batch(
        source, destination, workers=1, sidecar=True, resume=True
    )
    assert summary["files"] == 1
    assert (destination / "case.txt").read_text("utf-8") != "tampered"


def test_invalid_utf8_is_a_batch_error(tmp_path):
    source = tmp_path / "input"
    destination = tmp_path / "output"
    source.mkdir()
    (source / "case.txt").write_bytes(b"nome: \xff")
    summary = anonymize_batch(source, destination, workers=1)
    assert summary["errors"] == 1
    assert "UnicodeDecodeError" in summary["error_sample"][0]["error"]


def test_default_batch_run_overwrites_existing_output(tmp_path):
    source = tmp_path / "input"
    destination = tmp_path / "output"
    source.mkdir()
    destination.mkdir()
    (source / "case.txt").write_text("Il sig. Mario Rossi ricorre.", "utf-8")
    (destination / "case.txt").write_text("stale", "utf-8")
    summary = anonymize_batch(source, destination, workers=1)
    assert summary["files"] == 1
    assert (destination / "case.txt").read_text("utf-8") != "stale"


def test_sidecar_resume_reprocesses_a_changed_source(tmp_path):
    source = tmp_path / "input"
    destination = tmp_path / "output"
    source.mkdir()
    case = source / "case.txt"
    case.write_text("Il sig. Mario Rossi ricorre.", "utf-8")
    anonymize_batch(source, destination, workers=1, sidecar=True)
    case.write_text("Il sig. Luca Bianchi ricorre.", "utf-8")
    summary = anonymize_batch(
        source, destination, workers=1, sidecar=True, resume=True
    )
    assert summary["files"] == 1
    assert "Luca Bianchi" not in (destination / "case.txt").read_text("utf-8")


@pytest.mark.parametrize("mutation", ["corrupt", "schema", "engine"])
def test_sidecar_resume_reprocesses_invalid_metadata(tmp_path, mutation):
    source = tmp_path / "input"
    destination = tmp_path / "output"
    source.mkdir()
    (source / "case.txt").write_text("Il sig. Mario Rossi ricorre.", "utf-8")
    anonymize_batch(source, destination, workers=1, sidecar=True)
    sidecar = destination / "case.txt.map.json"
    if mutation == "corrupt":
        sidecar.write_text("not JSON", "utf-8")
    else:
        data = json.loads(sidecar.read_text("utf-8"))
        data["schema_version" if mutation == "schema" else "engine_version"] = -1
        sidecar.write_text(json.dumps(data), "utf-8")
    summary = anonymize_batch(
        source, destination, workers=1, sidecar=True, resume=True
    )
    assert summary["files"] == 1


def test_batch_rejects_destination_symlink_to_source(tmp_path):
    source = tmp_path / "input"
    destination = tmp_path / "output"
    source.mkdir()
    destination.mkdir()
    raw = source / "raw.txt"
    raw.write_text("Il sig. Mario Rossi ricorre.", "utf-8")
    link = destination / "raw.txt"
    try:
        link.symlink_to(raw)
    except (NotImplementedError, OSError):
        pytest.skip("symbolic links are unavailable")
    with pytest.raises(ValueError, match="symbolic link"):
        anonymize_batch(source, destination, workers=1)
    assert raw.read_text("utf-8") == "Il sig. Mario Rossi ricorre."


def test_batch_rejects_symlinked_subdirectory(tmp_path):
    source = tmp_path / "input"
    destination = tmp_path / "output"
    elsewhere = tmp_path / "elsewhere"
    (source / "nested").mkdir(parents=True)
    destination.mkdir()
    elsewhere.mkdir()
    (source / "nested" / "case.txt").write_text("testo", "utf-8")
    try:
        (destination / "nested").symlink_to(elsewhere, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("symbolic links are unavailable")
    with pytest.raises(ValueError, match="symbolic link"):
        anonymize_batch(source, destination, workers=1)
