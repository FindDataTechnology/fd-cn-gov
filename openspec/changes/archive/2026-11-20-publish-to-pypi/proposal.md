## Why

The package is currently installable only from git (`pip install git+https://github.com/<owner>/fd-cn-gov.git`), which blocks normal version pinning, is invisible to dependency resolvers and dependency scanners, and adds friction for anyone who just wants to try it. The project is already setuptools-based with a working `pyproject.toml`, a declared CLI entry point, and bundled registry data — so the lift to publish on PyPI is small, and doing it now establishes the release path before the first external users show up.

## What Changes

- Finalize `pyproject.toml` metadata for PyPI: project URLs (Homepage, Repository, Changelog), Trove classifiers, SPDX license expression, explicit/dynamic version alignment between `pyproject.toml` and `fd_cn_gov/__init__.py`.
- Confirm bundled data files (`registry/registry.db`, `registry/registry.json`) ship inside both the sdist and the wheel (already declared via `package-data`; verify, don't assume).
- Add a reproducible local build + validation step (`build` for sdist+wheel, `twine check`).
- Add a GitHub Actions release workflow that builds and publishes to PyPI on tag push using **Trusted Publishing** (OIDC) — no long-lived PyPI API token stored in the repo.
- Update `README.md` install section to show `pip install fd-cn-gov` as the primary path (git install becomes the fallback).
- Tag the first release (`v0.1.0`) and publish it.

No public Python API or CLI behavior changes — this is packaging + release only.

## Capabilities

### New Capabilities
- `package-distribution`: Building validated sdist + wheel distributions from `pyproject.toml`, publishing them to PyPI, and keeping the release path reproducible from a clean checkout.

### Modified Capabilities
<!-- None — no existing specs in openspec/specs/, and no spec-level runtime behavior is changing. -->

## Impact

- **Code**: `pyproject.toml` (metadata), `fd_cn_gov/__init__.py` (version source-of-truth), `README.md` (install instructions), new `.github/workflows/release.yml`.
- **Dependencies**: No new runtime dependencies. New dev-only tooling: `build`, `twine` (used in CI and optionally locally).
- **External systems**: PyPI project `fd-cn-gov` (must be available — first publish claims the name); GitHub repo tags / Actions environment for Trusted Publishing.
- **Users**: Gain `pip install fd-cn-gov`; existing git-install users are unaffected.
- **Risk**: PyPI name squat / collision on `fd-cn-gov` (low — owned namespace); forgetting to include `registry.*` in the wheel would ship a broken package (mitigated by an import smoke-test in the release job).
