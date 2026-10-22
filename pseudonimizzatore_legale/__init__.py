"""Local, offline pseudonymization of Italian legal documents.

    from pseudonimizzatore_legale import anonymize

    text, report = anonymize(open("sentenza.txt").read())

Parties, counsel and personal identifiers become tags (`Nominativo_1`, `CF_1`;
`roles=True` names a person's role: `Ricorrente_1`, `Difensore_1`). Judges, public bodies, places and case numbers stay in clear.
Companies are opt-in. Every surface form of the same person gets the same tag, so a
party pseudonymized in the header is not still readable in the body.

Two entry points:

    anonymize(text)                          one document
    anonymize_batch(src_dir, dst_dir)        a directory tree, in parallel

and one for short free-form input, with a limit worth reading about first:

    anonymize(query, profile="query")

A review tool calls the two halves of `anonymize` itself — `analyze` to detect and tag,
`render` to rewrite and verify — and passes a reviewer's corrections back as `Edits`.

The substitution is **one-way by design** — there is no de-pseudonymization path, and
nothing is persisted that would allow one unless you explicitly request a sidecar.
This is pseudonymization, not anonymization: the output is still personal data.

See README.md to get started, ARCHITECTURE.md for how and why it works.
"""
from .config import Config
from .core import Analysis, Edits, Report, analyze, anonymize, normalize, render
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
    "Edits",
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
