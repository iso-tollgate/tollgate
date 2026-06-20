"""The explanation layer's only public function.

Deliberately a single function, not a class, not an agent loop —
per the explicit decision: single-prompt Claude API calls in v1,
revisit only if evals demand more.

LIVE-VERIFIED (2026-06-21): this function was sandboxed during initial
development -- the sandbox had no API key configured and
api.anthropic.com wasn't on its network allowlist, so the original
implementation was correct by inspection only. It has since been run
for real, on the developer's own machine with a real ANTHROPIC_API_KEY,
via tests/test_explainer.py's three live-API tests (skipped
automatically without a key present, so the rest of the suite never
required one). Confirmed on a real run: explanations correctly name
the violated field and cause, correctly hedge on warning-severity
(heuristic) findings rather than asserting certainty, and feed
correctly into the eval harness's scoring function.

DATA HANDLING (2026-06-20): violation.raw_value is deliberately NEVER
sent to the API. It can contain the full content of a sensitive
field -- a real person's or company's name, an address fragment, taken
directly from a real payment message the user is checking. Tollgate's
entire premise is processing real bank payment data; sending PII to a
third-party API without explicit, informed consent is not acceptable
here. See prompts.py's EXPLAIN_VIOLATION_USER_TEMPLATE for the fuller
note on why raw_value isn't actually needed for explanation quality --
every rule's `message` field was written to already contain whatever
isolated, safe-to-send detail (a single character, a length, a line
count) the explainer needs, without the full sensitive value attached.
raw_value remains available locally (CLI report, JSON output, eval
harness) -- this restriction applies ONLY to what crosses the network
boundary to Anthropic's API.
"""

import os

from tollgate.explain.prompts import EXPLAIN_VIOLATION_SYSTEM_PROMPT, EXPLAIN_VIOLATION_USER_TEMPLATE
from tollgate.validation.models import Violation


def explain_violation(violation: Violation, model: str = "claude-sonnet-4-6") -> str:
    """Given one already-detected Violation, return a plain-English
    explanation grounded in the specific rule and field involved.

    Single call to the Anthropic API, system prompt + user prompt from
    prompts.py, no tools, no retry-with-different-prompt logic -- if
    the eval harness shows a class of explanation is consistently
    weak, fix the prompt template, don't paper over it with retries.

    Raises RuntimeError with a clear message if ANTHROPIC_API_KEY
    isn't set, rather than letting the underlying SDK's less specific
    auth error surface directly -- this is the first thing someone
    running this for the first time will hit.

    Deliberately does NOT pass violation.raw_value to the API -- see
    module docstring's DATA HANDLING note.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. explain_violation() calls the "
            "real Anthropic API and needs a key in the environment."
        )

    import anthropic

    client = anthropic.Anthropic()

    user_prompt = EXPLAIN_VIOLATION_USER_TEMPLATE.format(
        rule_id=violation.rule_id.value,
        field_path=violation.field_path,
        severity=violation.severity,
        message=violation.message,
        source_ref=violation.source_ref or "(none)",
    )

    response = client.messages.create(
        model=model,
        max_tokens=300,
        system=EXPLAIN_VIOLATION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return response.content[0].text
