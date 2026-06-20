# tollgate

A pre-submission safety gate for ISO 20022 payment messages. It catches the gap between "this passed schema validation" and "this will actually get accepted by the network" — before you find out the hard way.

## The problem, in one sentence

A pacs.008 payment message can be 100% valid XML, pass every XSD check you run against it, and still get rejected the moment it hits a real clearing network — because some of the rules that matter live outside the schema entirely.

Concretely: the ISO 20022 XML schema allows full Unicode in a name field. SWIFT's network layer restricts the allowed characters to Basic Latin, independently of what the schema permits. A name like "Helena Müller" passes XSD validation cleanly and fails on the wire. No XSD validator will ever catch that, because it isn't a schema problem. Tollgate exists because nothing else checks for this class of gap.

```
$ tollgate validate broken_payment.xml
1 error(s), 0 warning(s) found in broken_payment.xml:

ERROR charset_violation -- FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/Nm
  Contains character(s) outside SWIFT's character set X: 'ü'. This is
  schema-valid XML (ISO 20022 permits full Unicode) but SWIFT's network
  layer restricts allowed characters independently of the schema --
  this will not be caught by XSD validation alone.
```

That's a real, reproducible example — not a hypothetical. Every claim in this README has a working command behind it; see [Try it yourself](#try-it-yourself) below.

## Why now

ISO 20022 has been landing in US payments in waves. CHIPS migrated in 2024. Fedwire's core migration was 2025. Most of that wave has already happened — if you're reading this expecting "ISO 20022 migration is coming," it mostly isn't; it mostly already came.

What's still ahead, with a real date attached: by **November 2026**, several networks — Fedwire, CHIPS, SWIFT cross-border payments, and others — stop accepting unstructured free-text addresses for certain parties on a payment message. A structured Town and Country becomes mandatory, not optional, for specific roles on the message. If a system has been quietly getting away with free-text-only addresses because the old message format never enforced otherwise, that stops working on a fixed date.

That's the kind of failure Tollgate is built to catch ahead of time: not "is this XML well-formed," but "will this specific, dated rule reject this message even though the schema says it's fine."

## What it checks (v1 scope: pacs.008.001.08 only)

Five checks run on every message. Four of them exist specifically because they catch something XSD validation cannot:

| # | Check | Catches |
|---|---|---|
| 1 | **Schema validity** | Standard XSD structural validation against the official pacs.008.001.08 schema. The floor everything else stands on. |
| 2 | **SWIFT character set** | A message with a character outside SWIFT's allowed set (e.g. accented letters) — schema-valid, network-invalid. |
| 3 | **Address structure** | Free-format address lines used where a structured Town/Country is required, or address line counts that exceed network guidelines even though the schema allows more. |
| 4 | **Truncation signals** | A field value landing at exactly 35 or 70 characters — old legacy MT line-length limits — in a field whose modern limit is much higher. A heuristic, reported as a warning, not a certainty. |
| 5 | **Network-mandatory gaps** | Fields the schema marks optional but a real network requires in practice (e.g. UETR, which Fedwire's own documentation states is mandatory even though the XSD's `minOccurs="0"` permits its absence). |

Every rule traces to a primary or clearly-identified source — see [`docs/SOURCES.md`](docs/SOURCES.md). If a rule is in this tool, there's a citation behind it; where the evidence was thinner, the docs say so explicitly instead of asserting confidence that isn't there.

## What it explicitly does not do

- Not a SWIFT-certified compliance tool. Does not replace MyStandards testing.
- Covers exactly one message type in v1: pacs.008.001.08. Not pacs.009, not camt.05x, not the rest of the standard.
- Checks structure and format, not business logic — it won't tell you if a BIC is unreachable or an account doesn't exist.
- The character-set restriction is documented for the FIN/MX coexistence era specifically. Some networks have discussed loosening this for domestic use cases. Confirm current behavior for your specific target network before treating any rule here as a permanent universal.
- A known limitation worth knowing about: for messages with multiple transactions in one file, violations in different transactions can report identical-looking field paths (no transaction index). Not a crash, just an ambiguity — documented in `docs/SOURCES.md`.

## The deterministic-check / AI-narration split

Tollgate's checks are deterministic code — XSD validation, regex, length comparisons against known boundaries. No AI decides whether something is wrong. If Tollgate reports a violation, that's a fact a computer checked, not a guess a model made.

AI only enters at the explanation layer, and only when you ask for it with `--explain`. Given an already-detected violation, Claude writes the plain-English explanation: what's wrong, why it matters, what likely caused it if there's a real signal for that. It never decides whether something is a violation — it's a translator, not a judge. This is a single API call per violation, not an agent with tools — kept deliberately simple so it's easy to audit and easy to evaluate.

`--explain` is opt-in, not the default, because the deterministic checks are free, fast, and fully local, while explanation makes a real, billed call to the Anthropic API.

## Data handling

Tollgate processes real bank payment data. That data does not casually leave your machine.

- The five deterministic checks run entirely locally. Nothing is sent anywhere unless you explicitly pass `--explain`.
- When `--explain` is used, only the rule name, the field path (a structural reference like `Dbtr/Nm`, not a value), the deterministic finding text, and a source citation are sent to the Anthropic API.
- The actual offending value (a real name, a real address fragment) is **never sent to the API**, even with `--explain` on. It appears only in local output — your own console report, your own JSON output, your own markdown report — never in the API payload. This is enforced in code and verified by a test that mocks the API client and inspects the literal payload sent (`tests/test_data_handling.py`).
- See `docs/SOURCES.md`'s `data-handling-ai-boundary` section for the full reasoning.

## Install

```bash
git clone https://github.com/ArunMishra1/tollgate.git
cd tollgate
pip install -e .
```

For running the test suite yourself:

```bash
pip install -e ".[dev]"
```

Requires Python 3.11+.

Not yet published to PyPI — clone-and-install is the only path for now.

## Try it yourself

### CLI: check a single file

```bash
tollgate validate payment.xml
```

A clean message:
```
✓ payment.xml -- no issues found across all five checks.
```

A message with a problem:
```
1 error(s), 0 warning(s) found in payment.xml:

ERROR charset_violation -- FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/Nm
  Contains character(s) outside SWIFT's character set X: 'ü'. ...
```

Exit code is `0` if clean, `1` if any error-severity violation was found — scriptable in CI as-is.

Useful flags:
```bash
tollgate validate payment.xml --output report.md     # write a markdown report instead of printing
tollgate validate payment.xml --json                  # machine-readable output for scripts/CI
tollgate validate payment.xml --explain               # add AI explanations (needs ANTHROPIC_API_KEY)
```

### CLI: check a whole directory at once

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

One unreadable or broken file never stops the rest of the batch from being checked — every file gets its own outcome.

### Python library, no file required

```python
from tollgate import check_message

result = check_message(xml_string_you_already_have_in_memory)

if result.has_errors:
    for v in result.violations:
        print(v.rule_id.value, v.field_path, v.message)
```

Also available: `check_file(path)` for a file on disk, and `check_directory(path)` for a batch — both return the same kind of result object, with a `.to_dict()` for JSON serialization.

### Don't have a real payment file to test with?

Tollgate ships its own synthetic message generator — it can build a realistic, schema-valid pacs.008 message and deliberately inject any of the seven documented error types, so you can see every check in action without needing real bank data:

```bash
tollgate generate --count 5 --rule-id charset_violation --output-dir /tmp/fixtures
tollgate validate /tmp/fixtures/charset_violation_0.xml
```

### GitHub Action — check payment files on every PR

```yaml
- uses: ArunMishra1/tollgate/.github/actions/validate@main
  with:
    path: "payments/**/*.xml"
```

Fails the build on any error-severity finding, with inline `::error file=...::` annotations on the PR diff. See [`.github/workflows/example-consumer-usage.yml`](.github/workflows/example-consumer-usage.yml) for a complete example workflow.

## How this was built

Built with Claude doing real reasoning work, not as a thin prompt wrapper. The deterministic rules came from actual research against primary sources (the Federal Reserve's own Fedwire documentation, SWIFT's own character-set specifications) — every rule is traceable in `docs/SOURCES.md`. Several real bugs were found and fixed during development by deliberately testing messy, adversarial input rather than trusting that clean test fixtures meant the tool was done — see the inline comments in `validation/xsd_validator.py`, `cli.py`, and `docs/SOURCES.md`'s `known-limitations` section for specifics on what broke and how it got fixed.

## Status

152 tests passing, 3 skipped. The 3 skipped tests require a live `ANTHROPIC_API_KEY` to actually call the Anthropic API (`tests/test_explainer.py`) — they're skipped automatically without one, so the rest of the suite (every deterministic rule, the synthetic generator, the eval harness, the CLI, and the library API) is fully verified without needing any API key or billing.

What exists and is tested: all five validation rules, the synthetic fixture generator with labeled error injection for all seven gotcha types, an eval harness that scores AI explanations against known ground truth, the CLI (single-file and directory modes, console/JSON/markdown output), a Python library API, and a GitHub Action for CI use.

What hasn't been live-verified yet: the `--explain` flag's actual output quality against the real Claude API — the code is correct by inspection and unit-tested with a mocked client, but running it for real against live API calls is the next concrete step.

## License

Apache 2.0. See [`LICENSE`](LICENSE).
