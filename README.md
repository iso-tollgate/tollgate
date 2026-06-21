# tollgate

**Catches ISO 20022 payment messages that pass schema validation and still get rejected by the network — before you find out the hard way.**

[![Tests](https://img.shields.io/badge/tests-163%20passing-brightgreen)](#status) [![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE) [![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)

A pacs.008 payment message can be 100% valid XML, pass every XSD check, and still bounce off a real clearing network — because some of the rules that matter live outside the schema entirely. Tollgate catches that gap.

## Quickstart

```bash
pip install iso-tollgate
```

```bash
tollgate validate payment.xml
```

```
1 error(s), 0 warning(s) found in payment.xml:

ERROR charset_violation -- FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/Nm
  Contains character(s) outside SWIFT's character set X: 'ü'. This is
  schema-valid XML (ISO 20022 permits full Unicode) but SWIFT's network
  layer restricts allowed characters independently of the schema --
  this will not be caught by XSD validation alone.
```

That's a real example, not a mockup — every command in this README was actually run before being written down. No payment file handy? Generate one:

```bash
tollgate generate --count 1 --rule-id charset_violation --output-dir /tmp/fixtures
tollgate validate /tmp/fixtures/charset_violation_0.xml
```

→ **[Full usage guide](docs/usage.md)** — every command, every flag, the Python library API, batch directory checking, the GitHub Action
→ **[Why this exists](docs/why.md)** — the dated deadline behind it, the AI design philosophy, what was found and fixed during development
→ **[Sources](docs/SOURCES.md)** — every rule traced to a citation

## What it checks

One message type in v1: **pacs.008.001.08**, the FI-to-FI customer credit transfer used across Fedwire, CHIPS, and SWIFT CBPR+.

| Check | Catches |
|---|---|
| Schema validity | Standard XSD structural validation. The floor everything else stands on. |
| SWIFT character set | A character outside SWIFT's allowed set — schema-valid, network-invalid. |
| Address structure | Free-format addresses used where structure is required, or line counts the schema allows but a network's guidelines don't. |
| Truncation signals | A value landing at exactly 35 or 70 characters — old legacy line limits — in a field with a much higher modern limit. Reported as a warning, not a certainty. |
| Network-mandatory gaps | Fields the schema marks optional that a real network requires in practice (e.g. UETR for Fedwire). |
| Currency decimal precision | An amount's decimal places don't match its currency's defined exponent (e.g. JPY, which has zero decimal places, formatted with two). Reported as a warning — the failure mode is silent misinterpretation, not certain rejection. |

Every rule traces to a primary source — see [`docs/SOURCES.md`](docs/SOURCES.md). No rule ships without one.

## Not a compliance tool

Tollgate is a developer-facing sanity check, not a replacement for SWIFT certification or MyStandards testing. It covers one message type, checks structure and format (not business logic like BIC reachability), and is explicit in [`docs/why.md`](docs/why.md) about every limitation found during development. If it can't catch something, the docs say so.

## Three ways to use it

| | |
|---|---|
| **CLI** | `tollgate validate payment.xml` · `tollgate validate-dir payments/` |
| **Python library** | `from tollgate import check_message, check_file, check_directory` |
| **CI** | `uses: iso-tollgate/tollgate/.github/actions/validate@main` |

Details and examples for all three: [`docs/usage.md`](docs/usage.md).

## Status

163 tests passing, 3 skip cleanly without an `ANTHROPIC_API_KEY` set (these 3 exercise `--explain` against the real Anthropic API and were live-verified once, 2026-06-21, on a real machine with a real key — see `CLAUDE.md` for the re-verification rule if `explainer.py` or `prompts.py` change). The full deterministic suite — every validation rule, the generator, the eval harness, both APIs — needs zero API key to verify.

`--explain` has been live-tested against the real model: it correctly names the violated field and cause, and correctly hedges on warning-severity (heuristic) findings rather than asserting them as certain failures — verified, not assumed.

Published on PyPI: `pip install iso-tollgate`. A Homebrew tap is in progress at [`homebrew-tollgate`](https://github.com/iso-tollgate/homebrew-tollgate).

## License

Apache 2.0. See [`LICENSE`](LICENSE).
