"""Local, offline pseudonymization of Italian legal documents.

    from pseudonimizzatore_legale import anonymize

    text, report = anonymize(open("sentenza.txt").read())

Parties, counsel and personal identifiers become tags (`Nominativo_1`, `CF_1`;
`roles=True` uses role-specific tags such as `Ricorrente_1` and `Difensore_1`).
Use `keep_roles=("giudice",)` to retain identified judges in a published decision.
Public bodies, places and case numbers have separate rules.
Companies are opt-in. Every surface form of the same person gets the same tag, so a
party pseudonymized in the header is not still readable in the body.

Two entry points:

    anonymize(text)                          one document
    anonymize_batch(src_dir, dst_dir)        a directory tree, in parallel

and one for short free-form input, with a limit worth reading about first:

    anonymize(query, profile="query")

A review tool can call `analyze` to detect and tag, then `render` to rewrite and
verify. Pass `report.state` back as `state=` to reuse metadata and review decisions.

The substitution is **one-way by design** — there is no de-pseudonymization path, and
nothing is persisted that would allow one unless you explicitly request a sidecar.
This is pseudonymization, not anonymization: the output is still personal data.

See README.md to get started, ARCHITECTURE.md for how and why it works.
"""
from .config import Config
from .constraints import TextAnchor
from .core import Analysis, Report, analyze, anonymize, normalize, render
from .labels import DATA_PREFIXES, ROLE_PREFIXES
from .model import Decision, EntityRecord, Mention, ResidualFinding
from ._version import __version__

__all__ = [
    "anonymize",
    "anonymize_batch",
    "anonymize_file",
    "analyze",
    "render",
    "normalize",
    "Analysis",
    "DATA_PREFIXES",
    "ROLE_PREFIXES",
    "TextAnchor",
    "Config",
    "Report",
    "Mention",
    "Decision",
    "EntityRecord",
    "ResidualFinding",
    "__version__",
]


def __getattr__(name: str):
    # The batch driver pulls in multiprocessing and tempfile, which a browser runtime
    # such as Pyodide cannot use; load it only when it is asked for.
    if name in ("anonymize_batch", "anonymize_file"):
        from . import batch
        return getattr(batch, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
