# CLAUDE.md

Read this before doing any work in this repo. It encodes hard-won lessons from building Tollgate, not aspirational rules — every item here exists because skipping it caused a real, found bug.

## What this project is

A pre-submission safety gate for ISO 20022 pacs.008 payment messages. Catches messages that pass XSD schema validation but would still be rejected (or silently misinterpreted) by a real payment network. v1 scope is pacs.008.001.08 only — do not add a second message type without an explicit decision to do so.

## The core discipline: research and verify before writing code

Every validation rule in this project traces to a primary or clearly-identified source — see `docs/SOURCES.md`. Before adding a new rule:

1. Research the gotcha properly. Don't guess at field names, currency lists, or thresholds — find a real source (regulator documentation, the standard's own publisher, official schema definitions).
2. Verify the claim against the actual vendored XSD (`src/tollgate/schemas/pacs.008.001.08.xsd`) before writing detection logic. Multiple sessions found that secondary sources (blog posts, even careful research notes) contained claims that didn't hold up against the real schema — the FAIM-tag claim in `mandatory_gap_rule.py`'s history is the canonical example; it was replaced with a fully-verified UETR finding instead of shipping an unconfirmed citation.
3. If a primary source can't be directly verified (e.g. blocked by network access, paywalled), say so explicitly in the code and in `SOURCES.md` rather than asserting confidence you don't have. See the currency_rule.py honest-limitation note for the pattern.
4. Write the rule, then **test it against deliberately adversarial input before trusting it** — not just the happy path. Every one of this project's six rules had at least one real bug found this way:
   - `charset_rule.py`: the original character-set regex was missing a plain space character, meaning it would have flagged ordinary text like "Tomas Becker" as a violation.
   - `truncation_rule.py`: a naive version would have flagged any field at exactly 35/70 chars, including fields whose own legitimate maximum IS 35/70 — caught by reasoning through the design before writing code, not by a failing test.
   - `address_rule.py`: agent roles (DbtrAgt, etc.) nest their address one level deeper than party roles — a naive `role_tag/PstlAdr` search would have silently missed every agent-role violation.
   - `currency_rule.py`: testing it against the generator's own clean baseline output surfaced a real, pre-existing generator bug (JPY amounts always formatted with 2 decimal places, when JPY supports 0) that had been silently wrong since the project's first session.
   - `xsd_validator.py`: the exception handler let a raw Python stack trace reach the user for non-XML input, and separately, leaked a local filesystem path into an error message for a different malformed-input case.

If you find yourself trusting a docstring's claim ("X is handled," "Y is verified") without running code to confirm it — stop and verify first. This has been wrong multiple times in this project's history.

## Severity discipline

- `severity="error"`: a deterministic, schema-level-confident violation (XSD failure, character set violation, address structure violation, missing network-mandatory field).
- `severity="warning"`: a heuristic signal, not a certainty (truncation suspicion, currency decimal mismatch where the failure mode is "might be silently misinterpreted" rather than "will be rejected"). Never upgrade a warning to an error just to make output look more decisive — the uncertainty is real and the explanation layer needs to communicate it honestly.

## The deterministic/AI split — do not blur this

Validation logic (does X violate a rule) is deterministic Python, never an LLM call. The AI layer (`explain/explainer.py`) only narrates an already-detected violation in plain English — it never decides whether something is wrong. `--explain` is opt-in (flag), not default, because it's a real billed API call; the five-then-six deterministic checks are free and local.

**Data handling, non-negotiable:** `Violation.raw_value` (which can contain a real name, address, or other sensitive field content) must never be sent to the Anthropic API. It's fine in local output (CLI report, JSON, markdown) — the restriction is specifically about the network boundary. See `docs/SOURCES.md#data-handling-ai-boundary` and `tests/test_data_handling.py` for the enforced/tested version of this rule. If you're touching `explain/prompts.py` or `explain/explainer.py`, re-read this before changing what gets sent.

## Adding a new validation rule: the checklist

1. Research + cite in `docs/SOURCES.md` first.
2. Verify against the real vendored XSD before writing detection code.
3. Add a `RuleId` enum value in `validation/models.py`.
4. Write the rule module (`validation/<name>_rule.py`), following the existing pattern: a `_local_path()` helper for readable field paths, walk-by-structural-property (attribute presence, tag name, or tree depth) rather than assuming a fixed shape until you've checked the schema.
5. Write a real injector in `generator/synthetic_fixtures.py`'s `_INJECTORS` dict — every `RuleId` needs one, or `tollgate generate` and the eval harness will break for that rule (this has happened — adding a RuleId without wiring it into every consumer is a real, recurring integration gap).
6. Wire the new check into `api.py`'s `_run_all_checks()` — this is the actual source of truth the CLI and library both call into.
7. Wire it into the eval harness (`tests/evals/eval_harness.py`): `RULE_ID_SYNONYMS`, `DETECTOR_FOR_RULE`, `_run_detector_for_rule`.
8. Write tests proving: (a) a clean baseline has zero violations across several seeds, (b) the showcase case (schema-valid, rule-invalid) with an actual XSD validation run alongside it to prove the gap, (c) no false positive on a legitimate edge case that resembles the violation but isn't one.
9. Run the FULL test suite, not just the new file — adding a RuleId touches shared enums and dicts that other tests assert against.

## Testing conventions

- Always `cp -r source/. dest/` (trailing `/.`) when copying the repo for a clean test environment — `cp -r source/* dest/` silently skips dotfiles/dotdirs (`.github/`, `.gitignore`), which has caused confusion mid-session before.
- `pip install -e ".[dev]"` then `pytest tests/` for the full suite.
- `tests/test_explainer.py` has 3 tests gated by `ANTHROPIC_API_KEY` — they skip cleanly without one. Don't treat a skip as a failure; don't treat a skip as "verified" either. As of 2026-06-21 these have been live-verified once on a real machine with a real key — if you change `explainer.py` or `prompts.py`, re-run them for real before trusting the change.
- On macOS, `pip`/`pytest` may need `python3 -m pip` / `python3 -m pytest`, and a venv is required if you hit "externally-managed-environment" (`python3 -m venv .venv && source .venv/bin/activate`). See `TROUBLESHOOTING.md`.

## Repo layout

- `github.com/iso-tollgate/tollgate` — main repo
- `github.com/iso-tollgate/homebrew-tollgate` — Homebrew tap. Formula targets the real published `iso-tollgate==0.1.0` sdist (verified sha256, resource blocks for all dependencies generated via `homebrew-pypi-poet`). `brew install --build-from-source`, `brew test`, and `brew audit --strict --online` still need to be run for real on a machine with Homebrew — not verifiable in this sandbox.
- Published to PyPI as `iso-tollgate`, first release `0.1.0` (2026-06-21). `pip install iso-tollgate` works end-to-end, confirmed via a clean-venv install test.

## Don't

- Don't add a feature "because it'd be nice" without checking it against the original brief's scope discipline (one message type, pre-submission sanity check, not a SWIFT-certified compliance tool).
- Don't claim a rule is sourced without an actual citation in `docs/SOURCES.md`.
- Don't trust that "all tests pass" after adding a RuleId without running the FULL suite — shared mappings break silently otherwise.
- Don't write AI-sounding filler in README/docs. Real examples, real verified command output, no invented case studies.
