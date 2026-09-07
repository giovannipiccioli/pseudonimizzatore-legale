"""Options for a pseudonymization run.

Output policy and the few detector/runtime switches live here. Legal decisions all use
the same detector pipeline; there are no court- or document-type routers.

The defaults follow Italian published-case-law conventions: parties and counsel are
removed, explicit judicial roles and public bodies are kept, companies are opt-in, and
consistency is scoped to one document.
"""
from dataclasses import dataclass

#: There is one document-agnostic legal pipeline. ``query`` only omits block scanning
#: for short interactive input. The two old names remain inexpensive compatibility
#: aliases; they do not route to court-specific implementations.
PROFILES = ("legal", "query", "cassazione", "generic")
_PROFILE_ALIASES = {"cassazione": "legal", "generic": "legal"}


@dataclass(frozen=True)
class Config:
    """Policy for one pseudonymization run.

    profile
        ``"legal"`` (default) runs the same source-agnostic legal pipeline on every
        decision. ``"query"`` only omits long block scanning for short interactive
        input. Legacy values ``"cassazione"`` and ``"generic"`` are accepted as aliases
        of ``"legal"`` and do not select different court logic.
    companies
        Pseudonymize private companies as ``Società_N``. **Off by default**: in tax
        litigation the company is usually the subject matter rather than a private
        individual, and removing it often destroys the point of the document. Public
        bodies are never pseudonymized regardless of this flag.
    keep_judges
        Keep exact names that appear in a judicial role — Presidente, Relatore, Consigliere,
        Giudice, Sostituto Procuratore, and the bench lists of collegiate panels. On by
        default. Turning this off does not *remove* judges; it stops defending them, so
        late policy may then accept ordinary person candidates at those spans.
    keep_case_numbers
        Keep procedural identifiers (``n. 274/2023``, ``R.G. 17382/2023``, ECLI). On by
        default: pseudonymizing them makes the
        output uncitable and unlinkable to any other database. Switching it off does
        not pseudonymize case numbers; it only removes their explicit keep decision.
    sanitize
        Run the normalisation pre-pass (NFKC, zero-width strip, de-hyphenation, entity
        decode, markdown flattening). Needed for ``.md`` input and for anything
        converted from PDF or OCR. Costs roughly 15% of runtime, and **changes offsets**
        — turn it off only if you need the original bytes preserved exactly, and accept
        the lower recall that comes with it.
    min_token_len
        Shortest token that may propagate a name through the document. Below 4
        characters the false-positive risk outweighs the recall gain.
    ner
        Hugging Face model id of a token-classification model, a tuple of model ids to
        union for recall-first use, or ``None`` (default) to run regex-only. When set,
        each model becomes an **additional seed source**: it finds people the layout
        does not announce, and the same institution guards, conservative bare-token
        propagation, late policy and span resolution apply.

        Costs tens of times the regex runtime in the bundled benchmark, which is why it
        is opt-in. Requires ``pip install
        "pseudonimizzatore-legale[ner]"``. See `pseudonimizzatore_legale.ner` for what it does and does not
        buy, and the README for measured numbers.
    ner_threshold
        Minimum model confidence for a mention to become a seed. Below ~0.5 ordinary
        capitalised words start arriving; above ~0.8 genuine names in unusual layouts
        drop out.
    ner_device
        ``None`` (default) picks Apple MPS when available, else CPU. Pass ``"cpu"``,
        ``"mps"``, ``"cuda"`` or a device index to override. **Set this to ``"cpu"``
        for multi-worker batch runs** — several processes contending for one GPU is
        slower than letting each use its own core.
    verify
        Run review-oriented residual checks after rewriting. On by default. These checks do
        not modify output; they set ``Report.status`` to ``"needs_review"`` when a
        structured identifier, strongly cued person or known alias remains.

    Note there is no ``keep_places`` flag: place names are never detected in the first
    place, so they survive unconditionally. Residential addresses *are* removed, but
    they are anchored on ``residente``/``domiciliato`` rather than on the place name.
    """

    profile: str = "legal"
    companies: bool = False
    keep_judges: bool = True
    keep_case_numbers: bool = True
    sanitize: bool = True
    min_token_len: int = 4
    ner: str | tuple[str, ...] | None = None
    ner_threshold: float = 0.60
    ner_device: str | None = None
    verify: bool = True

    def __post_init__(self) -> None:
        if self.profile not in PROFILES:
            raise ValueError(
                f"unknown profile {self.profile!r}; expected one of {PROFILES}")
        if self.profile in _PROFILE_ALIASES:
            object.__setattr__(self, "profile", _PROFILE_ALIASES[self.profile])
        if isinstance(self.ner, tuple) and not self.ner:
            raise ValueError("ner model tuple must not be empty")
