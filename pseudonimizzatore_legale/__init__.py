"""Local, offline pseudonymization of Italian legal documents.

    from pseudonimizzatore_legale import anonymize

    text, report = anonymize(open("sentenza.txt").read())

Parties, counsel and personal identifiers become role tags (`Ricorrente_1`,
`Difensore_1`, `CF_1`). Judges, public bodies, places and case numbers stay in clear.
Companies are opt-in. Every surface form of the same person gets the same tag, so a
party pseudonymized in the header is not still readable in the body.

Two entry points:

    anonymize(text)                          one document
    anonymize_batch(src_dir, dst_dir)        a directory tree, in parallel

and one for short free-form input, with a limit worth reading about first:

    anonymize(query, profile="query")

The substitution is **one-way by design** — there is no de-pseudonymization path, and
nothing is persisted that would allow one unless you explicitly request a sidecar.
This is pseudonymization, not anonymization: the output is still personal data.

See README.md to get started, ARCHITECTURE.md for how and why it works.
"""
from .batch import anonymize_batch, anonymize_file
from .config import Config
from .core import Report, anonymize
from .model import Decision, EntityRecord, Mention, ResidualFinding
from ._version import __version__

__all__ = [
    "anonymize",
    "anonymize_batch",
    "anonymize_file",
    "Config",
    "Report",
    "Mention",
    "Decision",
    "EntityRecord",
    "ResidualFinding",
    "__version__",
]
