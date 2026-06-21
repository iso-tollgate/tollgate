# Usage guide

Every example below was run against the actual codebase before being written down — output shown is real, not illustrative.

## Install

```bash
pip install iso-tollgate
```

Or from source, for development:

```bash
git clone https://github.com/iso-tollgate/tollgate.git
cd tollgate
pip install -e .
```

For running the test suite yourself:

```bash
pip install -e ".[dev]"
pytest tests/
```

Requires Python 3.11+.

## CLI: check a single file

```bash
tollgate validate payment.xml
```

A clean message:
```
✓ payment.xml -- no issues found across all 6 checks.
```

A message with a problem — exit code is `1`:
```
1 error(s), 0 warning(s) found in payment.xml:

ERROR charset_violation -- FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/Nm
  Contains character(s) outside SWIFT's character set X: 'ü'. ...
```

Flags:

| Flag | Effect |
|---|---|
| `--output report.md` | Write a markdown report instead of printing to console |
| `--json` | Machine-readable output for scripts/CI (incompatible with `--output`) |
| `--explain` | Add AI-generated plain-English explanations — calls the Anthropic API, needs `ANTHROPIC_API_KEY` |
| `--message-type` | v1 only supports `pacs.008` (the default) |

## CLI: check a whole directory at once

```bash
tollgate validate-dir payments/ --recursive
```

```
Checked 4 file(s): 2 clean, 2 with errors

ISSUES payments/broken1.xml -- 1 error(s), 0 warning(s)
OK payments/clean1.xml
UNREADABLE payments/garbage.xml -- UnicodeDecodeError: ...
OK payments/subdir/nested.xml
```

One unreadable or broken file never stops the rest of the batch — every file gets its own outcome. `--recursive` is off by default so pointing this at the wrong directory doesn't silently scan far more than intended.

Flags: `--pattern` (default `*.xml`), `--recursive`, `--json`, `--message-type`.

## Python library

No file on disk required — works directly on an XML string or bytes you already have in memory:

```python
from tollgate import check_message

result = check_message(xml_string_you_already_have_in_memory)

if result.has_errors:
    for v in result.violations:
        print(v.rule_id.value, v.field_path, v.message)
```

Also available:

```python
from tollgate import check_file, check_directory

result = check_file("payment.xml")               # same result type, reads a file for you
batch  = check_directory("payments/")             # checks every file in a folder, returns a BatchCheckResult
```

`CheckResult` and `BatchCheckResult` both expose `.to_dict()` for JSON serialization, plus `.has_errors`, `.has_warnings`, `.is_clean` for branching.

## Synthetic test data

Tollgate ships its own message generator — builds a realistic, schema-valid pacs.008 message and can deliberately inject any of seven documented error types, so you can see every check in action without needing real bank data:

```bash
tollgate generate --count 5 --rule-id charset_violation --output-dir /tmp/fixtures
```

```
✓ Wrote 5 fixture(s) to /tmp/fixtures
```

Drop `--rule-id` to generate fixtures for all seven gotcha types at once.

## GitHub Action

Check payment files on every PR, fail the build on errors:

```yaml
- uses: iso-tollgate/tollgate/.github/actions/validate@main
  with:
    path: "payments/**/*.xml"
```

Inputs:

| Input | Default | Effect |
|---|---|---|
| `path` | — (required) | Glob pattern for files to check |
| `fail-on-warning` | `false` | Treat warning-severity findings as build failures too |
| `python-version` | `3.11` | Python version to set up |

Posts inline `::error file=...::` annotations directly on the PR diff. See [`.github/workflows/example-consumer-usage.yml`](../.github/workflows/example-consumer-usage.yml) for a complete example workflow.

## AI explanations and data handling

`--explain` calls the Anthropic API once per violation. It never sends the actual sensitive value (a real name, a real address fragment) — only the rule name, the structural field path, the deterministic finding text, and a source citation. See [`docs/why.md`](why.md#data-handling-in-full) for the full reasoning, and `tests/test_data_handling.py` for the test that verifies this directly by mocking the API client and inspecting the literal payload sent.
