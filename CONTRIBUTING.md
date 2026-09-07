# Contributing

Contributions are welcome, especially reusable Italian legal-text structures and
privacy-recall regressions.

## Set up

```bash
python -m pip install -e ".[dev,notebooks]"
python -m pytest -q
```

Before opening a pull request, also run:

```bash
python evaluation/build_corpus/check_fixtures.py
python evaluation/score_corpus.py
jupyter nbconvert --execute --to notebook --output-dir /tmp/notebook-check \
  notebooks/01_playground.ipynb
```

The corpus scorer is a measurement rather than a pass/fail gate. Report changes to
complete-entity recall, complete documents, protected-value survival, and the precision
lower bound in the pull request.

## Rules for fixtures

- Never commit a raw legal document or real personal data.
- Use invented identities and structured identifiers.
- Add positive and negative tests for each new detector rule.
- Prefer a reusable Italian legal structure over a source- or court-specific router.
- A person counts as removed only when every annotated alias and occurrence is gone.

The corpus builder requires private archives configured through environment variables.
Normal development and scoring use only the committed de-identified fixtures.

## Changes to policy

Keep evidence collection separate from output policy. Detectors should propose spans;
`policy.py` should decide which overlapping proposal wins. Verification must report
possible residuals without silently rewriting them.
