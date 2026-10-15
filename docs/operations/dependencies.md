# Reproducible Python dependencies

## Supported runtime and lock files

The backend build targets the exact Python patch release in `.python-version`. Railway and CI read the same file. `requirements.txt` is the production API lock: every direct and transitive distribution is version-pinned and SHA-256 checked. Railway and CI install it with `pip --require-hashes`.

Dependency files have separate responsibilities:

- `requirements.in` lists reviewed direct production dependencies.
- `requirements.txt` is the generated Linux production lock and is the only application manifest deployed by Railway.
- `requirements-audit.in` and `requirements-audit.txt` lock the isolated CI vulnerability scanner.
- `requirements-ai.in` and `requirements-ai.txt` lock the optional CPU research stack. They are not installed in the API image.

The optional AI lock does not enable, complete, or deploy VTON. Before any AI architecture is enabled, model weights must be stored in a controlled artifact registry with an immutable version, SHA-256 digest, license record, provenance, and rollback reference. Runtime downloads by a mutable model name are not an approved production release mechanism.

The optional CPU lock resolves exact, hashed Torch wheels from the official PyTorch index alongside PyPI. Both indexes are considered during that optional resolution only; exact versions and hashes remain mandatory. The production API lock uses PyPI alone.

If the optional research environment is deliberately provisioned, install it with `python -m pip install --require-hashes -r requirements-ai.txt`. Do not install it into the API service or treat it as an approved model release.

## Updating dependencies

1. Review release notes and advisories for each intended direct update.
2. Change only reviewed pins in the appropriate `.in` file.
3. Run `powershell -File scripts/lock_dependencies.ps1` for production/audit locks. Add `-IncludeAI` only when intentionally reviewing the optional AI graph.
4. Review lock diffs for unexpected packages, indexes, URLs, and platform markers.
5. Build a clean Python environment and install with `python -m pip install --require-hashes -r requirements.txt`.
6. Run the PostgreSQL-backed full suite and the vulnerability audit before merging.

Never hand-edit generated lock files. Do not add private package credentials or alternative indexes to committed requirement files.

## Security and SBOM policy

CI fails when `pip-audit` reports a known vulnerability in the production lock and uploads a CycloneDX JSON SBOM for the successful build. Exceptions require a time-bounded written risk acceptance containing the advisory, exploitability analysis, owner, compensating controls, and expiry date; suppressions must not be added silently.

The former `python-jose` dependency is intentionally prohibited because version 3.5.0 is affected by critical algorithm-confusion advisory GHSA-3qf3-8w2g-rqmx and no patched release is listed. JWT encoding and decoding use pinned PyJWT with the application algorithm fixed to HS256.
