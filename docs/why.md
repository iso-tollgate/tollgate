# Why Tollgate, and how it's built

This is the longer version of the story — the README keeps the five-minute summary; this is for anyone who wants the full reasoning.

## Why now, specifically

ISO 20022 has been landing in US payments in waves. CHIPS migrated in 2024. Fedwire's core migration was 2025. Most of that wave has already happened — if you're expecting "ISO 20022 migration is coming," it mostly already came.

What's still ahead, with a real date attached: by **November 2026**, several networks — Fedwire, CHIPS, SWIFT cross-border payments, and others — stop accepting unstructured free-text addresses for certain parties on a payment message. A structured Town and Country becomes mandatory, not optional, for specific roles. If a system has been quietly getting away with free-text-only addresses because the old message format never enforced otherwise, that stops working on a fixed date.

That's the kind of failure Tollgate is built to catch ahead of time: not "is this XML well-formed," but "will this specific, dated rule reject this message even though the schema says it's fine."

## The deterministic-check / AI-narration split

Tollgate's checks are deterministic code — XSD validation, regex, length comparisons against known boundaries. No AI decides whether something is wrong. If Tollgate reports a violation, that's a fact a computer checked, not a guess a model made.

AI only enters at the explanation layer, and only when you ask for it with `--explain`. Given an already-detected violation, Claude writes the plain-English explanation: what's wrong, why it matters, what likely caused it if there's a real signal for that. It never decides whether something is a violation — it's a translator, not a judge. This is a single API call per violation, not an agent with tools — kept deliberately simple so it's easy to audit and easy to evaluate.

`--explain` is opt-in, not the default, because the deterministic checks are free, fast, and fully local, while explanation makes a real, billed call to the Anthropic API.

This split exists because trusting every word of a conservative tool beats trusting a slick explanation sitting on top of a guess. In a space adjacent to real money movement, that tradeoff isn't close.

## Data handling, in full

Tollgate processes real bank payment data. That data does not casually leave your machine.

- The five deterministic checks run entirely locally. Nothing is sent anywhere unless you explicitly pass `--explain`.
- When `--explain` is used, only the rule name, the field path (a structural reference like `Dbtr/Nm`, not a value), the deterministic finding text, and a source citation are sent to the Anthropic API.
- The actual offending value (a real name, a real address fragment) is **never sent to the API**, even with `--explain` on. It appears only in local output — your own console report, your own JSON output, your own markdown report — never in the API payload. This is enforced in code and verified by a test that mocks the API client and inspects the literal payload sent (`tests/test_data_handling.py`).
- See [`docs/SOURCES.md`](SOURCES.md)'s `data-handling-ai-boundary` section for the full reasoning and what was found and fixed.

## How this was built

Built with Claude doing real reasoning work, not as a thin prompt wrapper. The deterministic rules came from actual research against primary sources (the Federal Reserve's own Fedwire documentation, SWIFT's own character-set specifications) — every rule is traceable in [`docs/SOURCES.md`](SOURCES.md).

Several real bugs were found and fixed during development, specifically by deliberately testing messy, adversarial input rather than trusting that clean test fixtures meant the tool was done:

- A naive truncation-detection rule would have falsely flagged completely legitimate values that happened to use a field's own real maximum length, before any code was written — caught by reasoning through the design, not by a failing test.
- `validate_xsd()`'s exception handling let a raw Python stack trace reach the user for non-XML input, despite its own docstring already claiming malformed documents would be caught cleanly.
- An empty file produced a confusing "Is a directory" error rather than a clear "this file is empty" message, due to how the underlying XML library resolves empty input.
- A plain string with no `<` character made the same library treat it as a file path rather than literal content, leaking a local filesystem path into the error message.
- A role-to-address-field mapping incorrectly assumed every party type stored its address at the same nesting depth in the XML tree, which would have silently missed every bank-address violation.
- An earlier draft of the AI explanation layer sent the full content of a sensitive field (a real name) to the Anthropic API — found and fixed by checking what the prompt actually needed, not assumed safe by default.

See the inline comments in `validation/xsd_validator.py`, `validation/address_rule.py`, `validation/truncation_rule.py`, `cli.py`, and `docs/SOURCES.md`'s `known-limitations` section for the specifics on each.

## What it explicitly does not do

- Not a SWIFT-certified compliance tool. Does not replace MyStandards testing.
- Covers exactly one message type in v1: pacs.008.001.08. Not pacs.009, not camt.05x, not the rest of the standard.
- Checks structure and format, not business logic — it won't tell you if a BIC is unreachable or an account doesn't exist.
- The character-set restriction is documented for the FIN/MX coexistence era specifically. Some networks have discussed loosening this for domestic use cases. Confirm current behavior for your specific target network before treating any rule here as a permanent universal.
- For messages with multiple transactions in one file, violations in different transactions can report identical-looking field paths (no transaction index). Not a crash, just an ambiguity — documented in `docs/SOURCES.md`.
