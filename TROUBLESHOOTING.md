# Troubleshooting

Real problems hit while building and testing this project, and their actual fixes — not hypothetical FAQ entries.

## `pip: command not found` / `pytest: command not found` (macOS)

Python itself is fine, but `pip`/`pytest` aren't exposed as standalone commands. Use:

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest tests/ -v
```

If `python3 -m pip` says "No module named pip":

```bash
python3 -m ensurepip --upgrade
```

## `error: externally-managed-environment`

Homebrew-managed Python on macOS blocks system-wide pip installs by design (PEP 668). Use a virtual environment — don't pass `--break-system-packages`, which the error message itself warns can break your Homebrew Python setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

**You must re-run `source .venv/bin/activate` every time you open a new terminal window/tab** for this project — it only applies to the current shell session. If `pip`/`pytest`/`tollgate` stop working after closing and reopening Terminal, this is almost always why.

## "I unzipped the new file but don't see any changes"

Two likely causes, in order of likelihood:

1. **You unzipped on top of an existing folder with the same name.** Many unzip tools (especially default Mac/iOS file apps) silently skip files that already exist rather than overwriting them, when extracting into a location that already has a same-named folder. **Fix: delete the old folder entirely before unzipping the new one. Always extract into a clean/empty location.**
2. **You're looking at GitHub, not the extracted zip.** Claude's sandbox work isn't pushed to GitHub automatically — it only exists in the zip until you `git add`/`commit`/`push` it yourself. If you're comparing against the GitHub repo and nothing's been pushed yet, that's expected.

## "I copied the repo for local testing and some files are missing" (`.github/`, `.gitignore`, etc.)

`cp -r source/* dest/` uses shell glob expansion, which does **not** match dotfiles/dotdirs by default. This silently drops `.github/`, `.gitignore`, and anything else starting with a dot.

**Fix: use `cp -r source/. dest/`** (trailing `/.` on the source) — this copies everything, including dotfiles, correctly.

This bit us mid-session once already — a "full test suite run" wasn't actually testing the GitHub Action files at all until this was caught and fixed.

## A GitHub Action / workflow YAML file looks right but might be broken

YAML that *looks* syntactically fine to the eye can still be wrong — multi-line embedded scripts inside `run: |` blocks are especially fragile (bash-inside-YAML, or worse, Python-inside-bash-inside-YAML). This project hit a real YAML syntax error this way once.

**Always validate before trusting a workflow/action file:**

```bash
python3 -c "import yaml; yaml.safe_load(open('path/to/file.yml'))"
```

If a script embedded in a workflow needs more than a few lines, pull it into a standalone `.py` file (see `.github/actions/validate/scripts/run_validation.py` for the pattern) rather than nesting it inline.

## A TOML edit broke `pyproject.toml` / `python -m build` fails with a confusing type error

TOML tables apply to every bare key that follows them until the next `[section]` header. Inserting a new `[project.urls]` (or any new table) **in the middle** of an existing table's keys will silently reassign the keys that come after it to the new table.

This project hit exactly this: adding `[project.urls]` between `classifiers` and `dependencies` caused `dependencies` to be parsed as belonging to `project.urls`, producing `TypeError: URL 'dependencies' of field 'project.urls' must be a string`.

**Fix: always add a new TOML table at the very end of the existing table's content, immediately before the next `[section]` header — never in the middle.** Rebuild (`python -m build`) and re-check (`twine check dist/*`) after any `pyproject.toml` edit before trusting it.

## "Why does the README/docs claim a different test count than what I just ran?"

Test counts in README badges and prose are manually written, not auto-generated — they go stale the moment a new test file is added without updating them. If you add tests, grep for the old count and update every place it appears:

```bash
grep -rn "163 passing\|166 tests\|<old-number>" README.md docs/
```

This has happened at least once already in this project (a README badge said "152 passing" after the real count had moved to 163).

## `poet` fails with `ModuleNotFoundError: No module named 'pkg_resources'`

`homebrew-pypi-poet` (used to generate Homebrew formula `resource` blocks from a PyPI package's dependency tree) is an old tool that assumes `pkg_resources` is always available from `setuptools`. Recent `setuptools` versions (82.x+, as installed by default in a fresh venv as of mid-2026) stopped vendoring `pkg_resources`. Fix, inside the same throwaway venv used for `poet`:

```bash
pip install setuptools==68.2.2
poet iso-tollgate
```

This pins `setuptools` to a version that still ships `pkg_resources`. Safe to do in a disposable `/tmp` venv — does not affect the real project's dependencies. Hit and fixed 2026-06-21.

## Sandbox-vs-local environment differences (for anyone working with Claude across sessions)

Claude's sandbox cannot reach `api.anthropic.com` (the live Anthropic API) — only a fixed allowlist (PyPI, npm, GitHub, crates.io). This means:

- `tests/test_explainer.py`'s 3 live-API tests will always skip in Claude's sandbox, regardless of whether `ANTHROPIC_API_KEY` is set there. They can only be run for real on your own machine.
- Claude cannot run `brew install`, since Homebrew itself isn't available in the sandbox — formula correctness has to be verified by you, locally.
- Claude *can* build the real sdist/wheel (`python -m build`) and run `twine check` in the sandbox — that doesn't need network access to PyPI, just the local build tooling.
