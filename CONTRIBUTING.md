# Contributing to InsightFlow

InsightFlow is maintained as an individual project. Issues and pull requests are welcome, with review and response times depending on maintainer availability. Please describe the user-visible behavior and the evidence for any security or data-access claims.

## Set up a checkout

Use the prerequisites and setup steps in [Install.md](Install.md). From the repository root:

~~~sh
make check
make config
make install
make dev
~~~

Keep runtime configuration and credentials local. Do not commit `config.yaml`, `extensions_config.json`, `.env`, frontend environment files, database credentials, or generated private data.

## Repository commands

Run a focused command for the files you changed:

| Area | Commands |
| --- | --- |
| Root orchestration | `make check`, `make doctor`, `make dev`, `make start`, `make up`, `make down` |
| Backend | From `backend/`: `make test`, `make lint`; a focused test can use `python -m pytest tests/path/test_file.py::test_name -q` |
| Frontend | From `frontend/`: `pnpm check`, `pnpm test`, `pnpm test:e2e` |
| Version gate | From repository root: `scripts/verify_versions.sh <version>` |

Backend default tests are offline. Live provider and blocking-I/O checks require their documented opt-in targets or environment settings. Browser tests use the repository's local fixtures unless the test explicitly names a real service.

## Change expectations

- Keep InsightFlow product copy and new comments primarily in Chinese. Provide both `zh-CN` and `en-US` for new frontend text. Keep code identifiers, API fields, configuration keys, stable error codes, and protocol values in their established machine-readable form.
- Preserve the boundary between the Analytics application and the general agent runtime. Analysis admits only the fixed Analytics toolset; ordinary chat integrations do not inherit Analytics SQL authorization.
- Use the smallest validation that proves the change. Documentation-only changes need readback, link checks, and diff checks; localized code changes need their focused tests and checks. Broaden validation for shared contracts, startup, persistence, security, or release boundaries.
- Add durable tests for observable behavior, important invariants, and confirmed regressions. Avoid tests that only restate trivial implementation details.
- Update user documentation when behavior or operational expectations change. Keep evidence reports factual: source presence, automated tests, synthetic fixtures, model output, and release acceptance are distinct claims.

## Version and release changes

The release version has two source files: `backend/pyproject.toml` and `frontend/package.json`. Update both together with `scripts/bump_version.sh <version>`, then run `scripts/verify_versions.sh <version>`. A `v*` tag is the release identifier; applicable CI version checks block publishing when either source disagrees with the tag. Read [RELEASING.md](RELEASING.md) before preparing a release.

Do not edit `CLAUDE.md`; it is only an import shim for `AGENTS.md`. Follow the root and module `AGENTS.md` files for service topology, security boundaries, code layout, and commands.

## Reporting security issues

For sensitive vulnerabilities, follow [SECURITY.md](SECURITY.md). Avoid putting credentials, customer data, or exploit details in a public issue.
