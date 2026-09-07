"""Batch driver: a directory tree of .txt/.md in, pseudonymized copies out.

Because consistency is per document (see :mod:`pseudonimizzatore_legale.labels`), workers share
no state and this is a plain process pool. Throughput depends heavily on document size,
worker count and whether optional NER is enabled.

Resume is opt-in. Sidecar-backed resume validates the source, output, configuration,
engine version and report schema; an explicit resume without sidecars is reported as
an unvalidated skip.
"""
import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from multiprocessing import Pool
from pathlib import Path

from ._version import __version__
from .config import Config
from .core import REPORT_SCHEMA_VERSION, anonymize

SUFFIXES = {".txt", ".md", ".markdown", ".text"}

_CFG: Config | None = None
_SIDECAR = False


def _init(cfg: Config, sidecar: bool) -> None:
    global _CFG, _SIDECAR
    _CFG, _SIDECAR = cfg, sidecar


def _config_data(config: Config) -> dict:
    """A JSON-shaped configuration value suitable for sidecar comparisons."""
    return json.loads(json.dumps(asdict(config), sort_keys=True))


def _sidecar_is_current(
    src: Path,
    output: Path,
    sidecar_path: Path,
    config: Config,
) -> bool:
    try:
        data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        source_digest = hashlib.sha256(src.read_bytes()).hexdigest()
        output_digest = hashlib.sha256(output.read_bytes()).hexdigest()
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return (
        data.get("schema_version") == REPORT_SCHEMA_VERSION
        and data.get("engine_version") == __version__
        and data.get("source_sha256") == source_digest
        and data.get("output_sha256") == output_digest
        and data.get("config") == _config_data(config)
    )


def _reject_symlink_destination(path: Path, boundary: Path | None = None) -> None:
    """Reject symbolic links at ``path`` and, optionally, below ``boundary``.

    System ancestors may legitimately be symbolic links (macOS maps ``/var`` to
    ``/private/var``), so a batch checks only the user-selected destination tree.
    """
    components = [path]
    if boundary is not None:
        component = path.parent
        while component != boundary:
            if component == component.parent or boundary not in component.parents:
                raise ValueError(f"destination escapes its output tree: {path}")
            components.append(component)
            component = component.parent
        components.append(boundary)
    for component in components:
        if component.is_symlink():
            raise ValueError(
                f"destination path contains a symbolic link: {component}"
            )


def _atomic_write(path: Path, data: bytes) -> None:
    """Write bytes beside ``path`` and atomically replace the final file."""
    _reject_symlink_destination(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_destination(path)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def anonymize_file(src: Path | str, dst: Path | str, config: Config | None = None,
                   sidecar: bool = False) -> dict:
    """Pseudonymize one file. Returns a small record for the run summary."""
    src, dst = Path(src), Path(dst)
    if src.resolve() == dst.resolve():
        raise ValueError("source and destination file must differ")
    _reject_symlink_destination(dst)
    if sidecar:
        _reject_symlink_destination(dst.with_suffix(dst.suffix + ".map.json"))
    cfg = config or Config()
    source_bytes = src.read_bytes()
    raw = source_bytes.decode("utf-8")
    out, report = anonymize(raw, cfg)
    output_bytes = out.encode("utf-8")
    _atomic_write(dst, output_bytes)
    if sidecar:
        meta = asdict(report)
        meta["source_sha256"] = hashlib.sha256(source_bytes).hexdigest()
        meta["output_sha256"] = hashlib.sha256(output_bytes).hexdigest()
        meta["engine_version"] = __version__
        meta["config"] = _config_data(cfg)
        sidecar_bytes = json.dumps(meta, ensure_ascii=False, indent=1).encode("utf-8")
        _atomic_write(dst.with_suffix(dst.suffix + ".map.json"), sidecar_bytes)
    return {
        "src": str(src),
        "dst": str(dst),
        "chars": len(raw),
        "entities": report.entities,
        "replacements": report.replacements,
        "risk": report.risk,
        "status": report.status,
        "residuals": len(report.residuals),
        "warnings": len(report.warnings),
    }


def _work(pair):
    src, dst = pair
    try:
        return anonymize_file(Path(src), Path(dst), _CFG, _SIDECAR)
    except Exception as exc:                              # one bad file must not stop a run
        return {"src": str(src), "dst": str(dst),
                "error": f"{type(exc).__name__}: {exc}"}


def anonymize_batch(src_dir, dst_dir, config: Config | None = None, workers: int | None = None,
                    sidecar: bool = False, resume: bool = False, progress=None) -> dict:
    """Pseudonymize every .txt/.md under `src_dir` into `dst_dir`, preserving layout.

    `progress` is called with (done, total) roughly every 200 files. Resume is disabled
    by default; set `resume=True` and preferably `sidecar=True` to skip validated work.
    Returns counts, throughput, residual-review records and highest-risk documents.
    """
    import time

    src_dir, dst_dir = Path(src_dir), Path(dst_dir)
    if not src_dir.is_dir():
        raise NotADirectoryError(f"source directory does not exist: {src_dir}")
    if dst_dir.exists() and not dst_dir.is_dir():
        raise NotADirectoryError(f"destination is not a directory: {dst_dir}")
    if workers is not None and (not isinstance(workers, int) or workers < 1):
        raise ValueError("workers must be a positive integer")
    src_resolved, dst_resolved = src_dir.resolve(), dst_dir.resolve()
    if (src_resolved == dst_resolved or src_resolved in dst_resolved.parents
            or dst_resolved in src_resolved.parents):
        raise ValueError("source and destination directory trees must be disjoint")
    _reject_symlink_destination(dst_dir)
    cfg = config or Config()
    jobs = []
    skipped = 0
    unvalidated_skips = 0
    for path in sorted(src_dir.rglob("*")):
        if path.suffix.lower() not in SUFFIXES or not path.is_file():
            continue
        out = dst_dir / path.relative_to(src_dir)
        _reject_symlink_destination(out, dst_dir)
        resolved_parent = out.parent.resolve()
        if resolved_parent != dst_resolved and dst_resolved not in resolved_parent.parents:
            raise ValueError(f"destination escapes its output tree: {out}")
        sidecar_path = out.with_suffix(out.suffix + ".map.json")
        if sidecar:
            _reject_symlink_destination(sidecar_path, dst_dir)
        if resume and out.exists():
            if not sidecar or _sidecar_is_current(path, out, sidecar_path, cfg):
                skipped += 1
                if not sidecar:
                    unvalidated_skips += 1
                continue
        jobs.append((str(path), str(out)))

    if not jobs:
        if progress:
            progress(0, 0)
        return {
            "files": 0,
            "skipped": skipped,
            "unvalidated_skips": unvalidated_skips,
            "errors": 0,
            "error_sample": [],
            "chars": 0,
            "entities": 0,
            "replacements": 0,
            "seconds": 0.0,
            "docs_per_s": None,
            "workers": 0,
            "high_risk": [],
            "needs_review": 0,
            "unverified": 0,
            "review_queue": [],
        }

    n_workers = workers or min(os.cpu_count() or 4, 14)
    t0 = time.perf_counter()
    records, done = [], 0
    with Pool(n_workers, initializer=_init, initargs=(cfg, sidecar)) as pool:
        for rec in pool.imap_unordered(_work, jobs, chunksize=32):
            records.append(rec)
            done += 1
            if progress and done % 200 == 0:
                progress(done, len(jobs))
    if progress and done % 200:
        progress(done, len(jobs))
    elapsed = time.perf_counter() - t0

    ok = [r for r in records if "error" not in r]
    errors = sorted(
        (r for r in records if "error" in r), key=lambda record: record["src"]
    )
    risky = sorted(ok, key=lambda r: (-r["risk"], r["src"]))[:20]
    needs_review = [r for r in ok if r.get("status") == "needs_review"]
    unverified = [r for r in ok if r.get("status") == "not_run"]
    review = sorted(
        (r for r in ok if r.get("status") != "passed_checks"),
        key=lambda record: record["src"],
    )
    return {
        "files": len(records),
        "skipped": skipped,
        "unvalidated_skips": unvalidated_skips,
        "errors": len(errors),
        "error_sample": errors[:10],
        "chars": sum(r.get("chars", 0) for r in ok),
        "entities": sum(r.get("entities", 0) for r in ok),
        "replacements": sum(r.get("replacements", 0) for r in ok),
        "seconds": round(elapsed, 1),
        "docs_per_s": round(len(records) / elapsed, 1) if elapsed else None,
        "workers": n_workers,
        "high_risk": risky,
        "needs_review": len(needs_review),
        "unverified": len(unverified),
        "review_queue": review[:100],
    }
