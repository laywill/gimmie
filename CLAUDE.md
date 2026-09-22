# CLAUDE.md

## Role & Communication Style

You are a senior software engineer collaborating with a peer. Prioritize thorough planning and alignment before implementation. Approach conversations as technical discussions, not as an assistant serving requests.

- **Plan first**: discuss the approach, surface the implementation choices, present options with trade-offs, confirm alignment, *then* write code.
- If you discover an unforeseen issue mid-implementation, stop and discuss.
- Push back on flawed logic. Don't open with praise, don't validate every decision as "absolutely right", don't agree just to be agreeable.
- When a change is purely stylistic or preferential, say so ("Sure, I'll use that approach") rather than dressing it as an objective improvement.
- Assume common programming concepts are understood. Be direct with feedback rather than couching it in niceties.

## Project

`gimmie` is a PyPI-published CLI that downloads files listed in a text file (one URL per line). Python >= 3.10, `requests` is the only runtime dependency, `src/` layout, built with Hatchling. Entry point: `gimmie = "gimmie.main:main"`.

## Commands

```bash
pip install -e ".[dev,test]"   # dev setup
pre-commit install             # install git hooks

pytest                                   # all tests
pytest --cov=gimmie tests/               # with coverage (what CI runs)
pytest tests/test_gimmie.py::test_cleanup_download   # single test
RUN_INTEGRATION_TESTS=1 pytest           # include the env-gated integration test

pre-commit run --all-files     # local lint/format pass; do this before pushing
hatch version patch            # roll version (also: minor, major, fix, rc, dev...)
```

The devcontainer (`mcr.microsoft.com/devcontainers/python:3.14`) runs the install and `pre-commit install` in `postCreateCommand`.

## Architecture

All logic lives in [src/gimmie/main.py](src/gimmie/main.py) as module-level functions — no classes, no logging framework (`print()` only), no shared state.

`download_file()` is the orchestrator: a `while attempts <= retry_count` loop that calls small single-purpose helpers, each of which is independently unit-tested. The helpers were deliberately split out of what would otherwise be one long function, so when adding behaviour prefer extending or adding a helper over inlining into the loop.

The download protocol each iteration:

1. `prepare_file_paths()` — derives the filename from the URL path, creates the destination dir, and returns both the final path and a hidden `.{filename}.part` temp path. Everything downloads to the `.part` file.
2. `prepare_download_state()` — if a `.part` file exists *and* `attempt_resume` *and* this is a retry (`attempts > 0`), sets a `Range: bytes=N-` header and `"ab"` mode; otherwise deletes the stale `.part`. Note the `attempts > 0` condition: a fresh invocation never resumes, only retries within the same run do.
3. `handle_resume_response()` — a `200` in response to a `Range` request means the server ignored it, so the `.part` is discarded and the request is re-issued without the header.
4. `download_content()` — streams the body in 8192-byte chunks, enforces `total_timeout` against `start_time` mid-stream, and computes total size from `Content-Range` (resumed) or `Content-Length` (fresh). If the running byte count exceeds the estimated total, it silently degrades from a percentage display to a raw byte count rather than showing >100%.
5. `cleanup_download()` — on success renames `.part` over the final path; on terminal failure removes it.

Error policy lives entirely in `handle_download_error()`, which returns a **bool meaning "retryable"**. Timeouts and connection errors are retryable; 4xx is terminal *except* 429. `apply_retry_backoff()` sleeps `min(2**attempts, 60)` seconds. If you add an exception type, classify it there rather than in the loop.

`read_urls_from_file()` strips surrounding quotes/commas and skips blank lines and `#` comments; it swallows read errors and returns `[]`, which `main()` treats as "no valid URLs" and exits 1. Per-file failures never abort the batch — `download_files_from_list()` just counts successes.

## Versioning and release

The version is single-sourced in [src/gimmie/\_\_init\_\_.py](src/gimmie/__init__.py) (`__version__`), read by Hatch via `[tool.hatch.version]`. Use `hatch version <segment>` rather than editing the string by hand.

Two CI gates enforce this:

- [version_check.yml](.github/workflows/version_check.yml) runs on PRs touching `__init__.py` and rejects anything that isn't a clean major/minor/patch increment over the base branch.
- [publish.yml](.github/workflows/publish.yml) fires on `v*` tags (or manual dispatch with an existing tag) and **fails the build if the tag minus its `v` prefix doesn't equal `hatch version`**. So bump the version, merge, then tag `vX.Y.Z` to match. Publishing uses PyPI trusted publishing via the `pypi` environment.

## Conventions and CI

- Formatting is black at line length 88, with isort `--profile black` and `pyupgrade --py310-plus`. flake8 uses the same 88 but ignores `E501` — black owns line length.
- `no-commit-to-branch` blocks commits on `main` locally; work on a branch. CI skips that hook via `SKIP=no-commit-to-branch`.
- MegaLinter runs on every push/PR with `APPLY_FIXES: all` and **commits fixes directly back to the PR branch**, so pull before continuing work after CI runs. Disabled linters and the reasons why are documented inline in [.mega-linter.yml](.mega-linter.yml) — check there before re-enabling one.
- cspell runs over the repo: new project-specific jargon goes in the `words` list in [.cspell.json](.cspell.json) or the build fails.
- **Every GitHub Actions `uses:` must be pinned to a full commit SHA with the semantic version in a trailing comment** — `uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1`. Never a tag or branch ref: a tag is mutable and re-pointing it silently changes what runs in CI. The SHA is the security boundary; the comment is what makes the pin readable and is what Dependabot rewrites when it bumps the action, so a pin without one is a pin nobody can review. This applies to new workflows and to any `uses:` line you touch — several existing files (`pre-commit.yml`, `publish.yml`, `pytest.yml`, `version_check.yml`) are correctly SHA-pinned but still missing the comment, so add it as you go.
- Tests run against Python 3.10–3.14. Line endings are LF-normalized via [.gitattributes](.gitattributes); `.editorconfig` sets 4-space indent for `.py`, 2 elsewhere.

## Testing notes

Tests mock HTTP with the `responses` library. Two things to know:

- There are **two pytest configs** — `[tool.pytest.ini_options]` in [pyproject.toml](pyproject.toml) and [tests/pytest.ini](tests/pytest.ini). Which one applies depends on how pytest is invoked (`pytest` from the root vs `pytest tests/`). Keep them in sync when changing settings.
- Only `test_main_function` is gated by `RUN_INTEGRATION_TESTS`. `test_integration_with_real_file` makes a real request to GitHub on every run and asserts only `if result:`, so it passes silently when offline.
