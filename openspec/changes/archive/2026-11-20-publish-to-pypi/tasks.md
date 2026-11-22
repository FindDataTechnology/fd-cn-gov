## 1. Pre-flight (external / human setup)

- [ ] 1.1 Verify `fd-cn-gov` is available on PyPI — open `https://pypi.org/project/fd-cn-gov` and confirm it is not already taken
- [x] 1.2 Determine the real GitHub `owner/repo` for this project (the README currently uses `<owner>` as a placeholder)
- [ ] 1.3 Decide which PyPI account will own/register the `fd-cn-gov` project

## 2. pyproject.toml metadata

- [x] 2.1 Remove the static `version = "0.1.0"` from `[project]` and add `dynamic = ["version"]`
- [x] 2.2 Add `[tool.setuptools.dynamic]` with `version = {attr = "fd_cn_gov.__version__"}`
- [x] 2.3 Switch `license = { text = "MIT" }` to the SPDX form `license = "MIT"`
- [x] 2.4 Add `[project.urls]` with Homepage, Repository, Changelog, and Issues pointing at the real `owner/repo`
- [x] 2.5 Add Trove classifiers: Development Status, Intended Audience, `License :: OSI Approved :: MIT License`, `Programming Language :: Python :: 3 :: only`, 3.10/3.11/3.12/3.13, `Operating System :: OS Independent` — *NOTE: omitted the `License :: OSI Approved :: MIT License` classifier; PEP 639 (setuptools ≥77) deprecates license classifiers when an SPDX `license` expression is present, and combining them risks a build validation error. All other listed classifiers were added.*
- [x] 3.1 Confirm `fd_cn_gov/__init__.py` (`__version__ = "0.1.0"`) is the only version literal; grep the repo for stray `0.1.0` strings that imply a second source of truth

## 4. README install instructions

- [x] 4.1 Make `pip install fd-cn-gov` the primary Install command
- [x] 4.2 Demote the git install to a "from source" note and replace the `<owner>` placeholder with the real repo
- [x] 4.3 (Optional) add a PyPI project link / version badge near the title

## 5. Build-validation workflow (non-publishing)

- [x] 5.1 Create `.github/workflows/build-check.yml` triggering on `pull_request` and `push` to `main`
- [x] 5.2 Job steps: checkout, `setup-python` 3.10, `pip install build twine`, `python -m build`, `twine check dist/*`
- [x] 5.3 Add a wheel smoke-test step: create a fresh venv, `pip install dist/*.whl`, run `fd-cn-gov list` and assert it prints 11 sources

## 6. Release workflow (publishing, tag-triggered)

- [x] 6.1 Create `.github/workflows/release.yml` triggering on `push: tags: ["v*"]`
- [x] 6.2 Reuse the build + `twine check` + wheel smoke-test steps from the build-check job (composite step or duplicated)
- [x] 6.3 Add a publish step using `pypa/gh-action-pypi-publish@release/v1` with `permissions: id-token: write` and `environment: pypi`
- [x] 6.4 Confirm the workflow references **no** `PYPI_API_TOKEN` / password secret (OIDC only)

## 7. Trusted Publishing configuration (external / human)

- [ ] 7.1 On PyPI: register the `fd-cn-gov` project (created automatically on first upload, or pre-create it)
- [ ] 7.2 On PyPI: add a GitHub Actions OIDC publisher scoped to `<owner>/<repo>` + environment name `pypi`
- [ ] 7.3 On GitHub: create the `pypi` environment (optionally with required reviewers / branch restriction)

## 8. Local verification

- [x] 8.1 `python -m pip install --upgrade build twine`
- [x] 8.2 `python -m build` and confirm both `dist/*.tar.gz` and `dist/*.whl` are produced
- [x] 8.3 `twine check dist/*` passes with no errors or warnings
- [x] 8.4 Install the wheel into a fresh venv and run `fd-cn-gov list` (assert 11 sources) and `fd-cn-gov --help` (assert exit 0)
- [x] 8.5 Assert `pip show fd-cn-gov` Version equals `fd_cn_gov.__version__`

## 9. Dry-run on TestPyPI (recommended before the real release)

- [ ] 9.1 Configure a TestPyPI trusted publisher for `<owner>/<repo>` (or use a scoped TestPyPI API token for this one stage)
- [ ] 9.2 Tag `v0.1.0rc1` and push; publish to TestPyPI
- [ ] 9.3 `pip install -i https://test.pypi.org/simple/ fd-cn-gov==0.1.0rc1` in a fresh venv and run the smoke test

## 10. Release

- [ ] 10.1 Tag `v0.1.0` and push the tag
- [ ] 10.2 Confirm the release workflow builds, validates, and publishes to PyPI (workflow green)
- [ ] 10.3 In a fresh venv: `pip install fd-cn-gov==0.1.0`, run `fd-cn-gov list` (assert 11 sources) and `fd-cn-gov --help` (exit 0)
- [ ] 10.4 If `0.1.0` is broken: **yank** it on PyPI (do not attempt to re-upload the same version — PyPI rejects it)
