## Context

`fd-cn-gov` (v0.1.0) is a setuptools-based Python package: `pyproject.toml` already declares name/version/deps/CLI-entry/`package-data`, and a local build has produced `fd_cn_gov.egg-info`, so the packaging basics work. It ships a bundled SQLite + JSON registry (`fd_cn_gov/registry/registry.{db,json}`) that **must** travel inside the distribution or `import fd_cn_gov` and `fd-cn-gov list` break for end users. Today the only install path is `pip install git+…`, which is invisible to dependency resolvers and friction for users. This change adds a reproducible build → validate → publish path to PyPI without touching runtime behavior.

## Goals / Non-Goals

**Goals:**
- `pip install fd-cn-gov` works from PyPI, with the CLI and registry data functional out of the box.
- Release is reproducible from a clean checkout (same inputs → same artifacts, modulo build metadata).
- One source of truth for the version — `pyproject.toml` and the installed package cannot drift.
- No long-lived PyPI secret in the repo.

**Non-Goals:**
- Changing the public Python API or CLI behavior.
- Auto-versioning from commits (setuptools-scm / commitizen) — manual tagging is fine for now.
- Conda / nix / other distribution channels.
- Auto-publish on every push to `main` — only on tag.

## Decisions

### D1: Keep setuptools as the build backend
Already wired, `package-data` for the registry works, and the team is familiar with it.
- *Alternative considered:* hatchling / flit — simpler config, but no payoff that justifies the migration cost for a package this size.

### D2: Single version source via `dynamic = ["version"]`
Use `version = {attr = "fd_cn_gov.__version__"}` under `[tool.setuptools.dynamic]`, keeping `fd_cn_gov/__init__.py` as the only place the version is written.
- *Alternative considered:* static `version = "0.1.0"` in `pyproject.toml` synced by hand — drifts the moment someone forgets.
- *Alternative considered:* setuptools-scm deriving from git tags — nice, but couples versioning to git history and is overkill while releases are hand-tagged.

### D3: Release via GitHub Actions + Trusted Publishing (OIDC)
PyPI's OIDC trusted publishing lets the workflow mint a short-lived token with no stored secret. The job runs with `permissions: id-token: write` against a PyPI environment named `pypi`.
- *Alternative considered:* `PYPI_API_TOKEN` in a repo secret — rotates, leak-prone, broader blast radius.
- *Alternative considered:* `twine upload` from a laptop — not reproducible, not auditable, single-point-of-failure.

### D4: Trigger on tag push `v*`
The git tag is the canonical release artifact; a tag push is unambiguous and works for both first publish and future releases.
- *Alternative considered:* GitHub Release event — adds a manual UI step on top of the tag; the tag alone is sufficient.

### D5: Ship registry data via existing `package-data`
`[tool.setuptools.package-data] fd_cn_gov = ["registry/registry.db", "registry/registry.json"]` is already declared and correct for the wheel. We **verify** it (import smoke test in CI) rather than change it. No `MANIFEST.in` needed — setuptools includes `package-data` in the sdist too.
- *Alternative considered:* `MANIFEST.in` with `include` — redundant with `package-data` for this case and easy to get out of sync.

### D6: Build sdist + wheel with `python -m build`, validate with `twine check`
Standard PEP 517 build front-end; `twine check` catches missing README/license/metadata issues before they reach PyPI.

### D7: Non-publishing build job on PRs/push-to-main
A lightweight job builds + `twine check`s on every PR and push to `main` so metadata regressions are caught without publishing. The publish step only runs on `v*` tags.

## Risks / Trade-offs

- **[PyPI name `fd-cn-gov` unavailable/taken]** → check `pypi.org/project/fd-cn-gov` and claim the project **before** tagging. If taken, decide on an alternate name and update `pyproject.toml` first.
- **[Registry data missing from wheel]** → release job installs the built wheel into a fresh venv and runs `fd-cn-gov list`; the publish step is gated on this passing.
- **[Trusted Publishing mis-configured]** → fails closed (no OIDC token → no upload). Requires the `pypi` environment to exist on the GitHub repo and the publisher to be registered on the PyPI project with the exact `owner/repo` + environment.
- **[Publish is irreversible]** → PyPI files cannot be overwritten, only yanked (or deleted within 72h of upload for the very first time on a project). Never re-tag a released version. Mitigation: dry-run TestPyPI publish of the release candidate before the real `v0.1.0` tag.
- **[Version drift]** → eliminated by D2; the release job asserts `pip show fd-cn-gov` Version == `fd_cn_gov.__version__`.
- **[Loose `scrapling` pin]** → `scrapling` has no lower bound; a future breaking release could break installs. Out of scope here; flagged as a follow-up.

## Migration Plan

This is a greenfield publish, not a migration of existing users (git-install users are unaffected):

1. **Pre-flight (human, outside the repo):** confirm `fd-cn-gov` is free on PyPI; create the PyPI project and register a Trusted Publishing OIDC publisher scoped to `<owner>/<repo>` + environment `pypi`. Create the `pypi` environment on the GitHub repo (optionally with required reviewers).
2. **In-repo:** merge `pyproject.toml` metadata changes, dynamic version, README install update, and the two workflows (build-check on PR, release on tag).
3. **Dry-run (optional but recommended):** push a `v0.1.0rc1` tag and publish to **TestPyPI** first; install from TestPyPI and run the smoke test.
4. **Release:** tag `v0.1.0` and push → release workflow publishes to PyPI.

**Rollback:** if `0.1.0` is broken, `yank` it on PyPI (files stay but won't be chosen by `pip install fd-cn-gov` without an explicit `==0.1.0`); delete the remote tag only to stop re-triggers (the workflow still won't republish the same version — PyPI rejects re-uploads).

## Open Questions

- **PyPI ownership:** which PyPI account registers/owns `fd-cn-gov`? (Needed for the Trusted Publishing registration — a one-time manual step.)
- **GitHub repo identity:** the exact `owner/repo` for the OIDC publisher config? (The README currently shows `<owner>` as a placeholder.)
- **TestPyPI dry-run:** do we run a TestPyPI stage before the real `v0.1.0` publish? (Recommended: yes.)
