# package-distribution Specification

## Purpose
How the `fd-cn-gov` package is built and shipped: dynamic version from the package source, the source registry bundled inside the wheel, and publication to PyPI through GitHub Actions OIDC trusted publishing on a `v*` tag.

## Requirements

### Requirement: Build from a clean checkout
The project SHALL be buildable into both an sdist (`*.tar.gz`) and a wheel (`*.whl`) from a clean checkout using `python -m build`, with the version derived from the package source rather than written statically in `pyproject.toml`.

#### Scenario: Clean checkout produces both distributions
- **WHEN** a contributor runs `python -m build` on a fresh clone with build tooling installed
- **THEN** both `dist/fd_cn_gov-<version>-py3-none-any.whl` and `dist/fd_cn_gov-<version>.tar.gz` are produced
- **AND** no `version` field is present in the `[project]` table of `pyproject.toml` (it is dynamic)

### Requirement: Bundled registry data ships in the wheel
The wheel SHALL include `fd_cn_gov/registry/registry.db` and `fd_cn_gov/registry/registry.json` so that `import fd_cn_gov` and the `fd-cn-gov` CLI function without rebuilding the registry.

#### Scenario: Wheel is self-contained
- **WHEN** the built wheel is installed into a fresh virtual environment
- **THEN** `python -c "import fd_cn_gov; assert len(fd_cn_gov.list_sources()) == 11"` exits 0
- **AND** `fd-cn-gov list` prints the 11 registered sources

### Requirement: Single source of truth for version
The distribution version SHALL be derived from `fd_cn_gov.__version__` via `[tool.setuptools.dynamic]`, so the wheel metadata and the installed package cannot drift.

#### Scenario: Wheel metadata matches package version
- **WHEN** the built wheel's metadata is inspected
- **THEN** the `Version` field equals `fd_cn_gov.__version__`

### Requirement: Distribution metadata is PyPI-ready
The distribution metadata SHALL include project URLs (Homepage, Repository, Changelog), an SPDX license identifier, and Trove classifiers matching the supported Python version (`>=3.10`) and license (MIT). The built distributions SHALL pass `twine check` with no errors or warnings.

#### Scenario: twine check passes
- **WHEN** `twine check dist/*` is run on the freshly built distributions
- **THEN** the command exits 0 and prints no warnings

### Requirement: Tag-triggered release via Trusted Publishing
A git tag matching `v*` SHALL trigger a GitHub Actions release workflow that builds the sdist + wheel, validates them, installs the wheel into a fresh environment and runs the registry smoke test, and then publishes to PyPI using OIDC Trusted Publishing. No PyPI API token SHALL be stored in or read from repository secrets.

#### Scenario: Tag push publishes to PyPI
- **WHEN** a tag `v0.1.0` is pushed to the default branch
- **THEN** the release workflow builds sdist + wheel
- **AND** runs `twine check` and a wheel smoke test (`fd-cn-gov list`)
- **AND** uploads to PyPI using the `pypi` trusted-publishing environment with `permissions: id-token: write`
- **AND** no `PYPI_API_TOKEN` (or equivalent) secret is referenced by the workflow

#### Scenario: Republish of an existing version is rejected
- **WHEN** the workflow attempts to publish a version whose files already exist on PyPI
- **THEN** PyPI rejects the upload and the workflow exits non-zero

### Requirement: Non-publishing build validation on pull requests
Every pull request and push to `main` SHALL trigger a build-validation workflow that builds sdist + wheel and runs `twine check`, **without** publishing. This catches metadata and packaging regressions before a release tag.

#### Scenario: PR build check
- **WHEN** a pull request is opened
- **THEN** the build-validation workflow builds the distributions and runs `twine check`
- **AND** does not upload to any package index

### Requirement: Post-publish installability from PyPI
After a version is published, `pip install fd-cn-gov==<version>` SHALL succeed in a clean environment and expose a working `fd-cn-gov` CLI with the bundled registry.

#### Scenario: Fresh install from PyPI
- **WHEN** a user runs `pip install fd-cn-gov==0.1.0` in a new virtual environment with Python >=3.10
- **THEN** the install succeeds
- **AND** `fd-cn-gov --help` exits 0
- **AND** `fd-cn-gov list` prints the 11 registered sources
