"""The explanation layer's only public function.

Deliberately a single function, not a class, not an agent loop —
per the explicit decision: single-prompt Claude API calls in v1,
revisit only if evals demand more.

HONEST LIMITATION (2026-06-20): this function has NOT been live-tested
against the real Anthropic API. The sandbox this project was built in
has no API key configured and api.anthropic.com is not on its network
allowlist, so the implementation below is correct by inspection and by
matching the documented API shape, but has not actually been called
and verified end-to-end. Run tests/test_explainer.py with a real
ANTHROPIC_API_KEY set (it's skipped automatically otherwise) before
trusting this in the eval harness or CLI.
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
        raw_value=violation.raw_value or "(none)",
        source_ref=violation.source_ref or "(none)",
    )

    response = client.messages.create(
        model=model,
        max_tokens=300,
        system=EXPLAIN_VIOLATION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return response.content[0].text
