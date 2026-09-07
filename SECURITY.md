# Security and privacy

## Reporting a problem

Please use GitHub's private security-advisory feature for vulnerabilities or privacy
failures. Do not open a public issue containing a real legal document, personal data,
an original-to-tag sidecar, credentials, or a reproducible example with real names.

Replace all identities and identifiers with invented equivalents before sharing a
sample. Include the library version, configuration, expected behavior, and the smallest
synthetic input that demonstrates the problem.

## Scope and operating assumptions

- Document text is processed locally. Optional NER may download model files on first
  use, but the library does not send document content to a hosted inference service.
- `Report.mapping` and `*.map.json` sidecars contain original sensitive values and must
  be protected like the source document.
- Pseudonymized output may remain personal data and must not be treated as automatically
  safe to publish.
- `passed_checks` is a heuristic result, not a security guarantee.
