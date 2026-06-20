"""Tests for explain/explainer.py.

HONEST LIMITATION: this module was built without access to a live
Anthropic API call (the development sandbox has no ANTHROPIC_API_KEY
configured and no network access to api.anthropic.com). The tests
below split into two groups:
  - test_missing_api_key_raises_clear_error: runs unconditionally, no
    API access needed, tests the explicit guard added specifically
    because of this limitation.
  - test_real_api_call_*: marked with skipif so they run automatically
    once a real ANTHROPIC_API_KEY is present, but don't fail CI for
    anyone running tests without one. These are the FIRST real,
    live verification this function has ever had -- run them before
    trusting explain_violation() in the eval harness or CLI.
"""

import os

import pytest

from tollgate.explain.explainer import explain_violation
from tollgate.validation.models import RuleId, Violation

HAS_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))


def test_missing_api_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    violation = Violation(
        rule_id=RuleId.CHARSET_VIOLATION,
        field_path="FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/Nm",
        message="Contains character(s) outside SWIFT's character set X: 'ü'.",
        severity="error",
        raw_value="Helena Müller",
        source_ref="charset-x",
    )

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        explain_violation(violation)


@pytest.mark.skipif(not HAS_API_KEY, reason="No ANTHROPIC_API_KEY set -- skipping live API test")
def test_real_api_call_charset_violation_mentions_field_and_cause():
    """The first real, live test of this function. If this is your
    first time running it: this makes an actual billed API call.
    """
    violation = Violation(
        rule_id=RuleId.CHARSET_VIOLATION,
        field_path="FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/Nm",
        message=(
            "Contains character(s) outside SWIFT's character set X: 'ü'. "
            "This is schema-valid XML (ISO 20022 permits full Unicode) but "
            "SWIFT's network layer restricts allowed characters "
            "independently of the schema -- this will not be caught by "
            "XSD validation alone."
        ),
        severity="error",
        raw_value="Helena Müller",
        source_ref="charset-x",
    )

    explanation = explain_violation(violation)

    assert isinstance(explanation, str)
    assert len(explanation) > 0
    # Loose checks only -- exact wording is the model's choice. The real
    # quality bar is the eval harness's score_explanation(), not this test.
    text_lower = explanation.lower()
    assert "name" in text_lower or "nm" in text_lower or "debtor" in text_lower
    assert "character" in text_lower or "swift" in text_lower


@pytest.mark.skipif(not HAS_API_KEY, reason="No ANTHROPIC_API_KEY set -- skipping live API test")
def test_real_api_call_mentions_warning_severity_honestly():
    """For a severity="warning" (heuristic) violation, the explanation
    should not present it as a certain failure -- this was an explicit
    instruction in the system prompt; verify the model actually
    follows it.
    """
    violation = Violation(
        rule_id=RuleId.TRUNCATION_SUSPECTED,
        field_path="FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/Nm",
        message=(
            "Nm is exactly 35 characters long, matching a legacy MT "
            "line-length limit, even though this field allows up to 140. "
            "This is a heuristic signal, not a certain failure."
        ),
        severity="warning",
        raw_value="A" * 35,
        source_ref="truncation-pilot",
    )

    explanation = explain_violation(violation)
    text_lower = explanation.lower()

    # The explanation should hedge -- look for hedging language, not
    # confident certainty language presenting this as a definite error.
    hedging_terms = ["may", "possibl", "suggest", "could", "signal", "heuristic", "coincidence"]
    assert any(term in text_lower for term in hedging_terms), (
        f"Expected hedging language for a warning-severity heuristic, "
        f"got: {explanation!r}"
    )


@pytest.mark.skipif(not HAS_API_KEY, reason="No ANTHROPIC_API_KEY set -- skipping live API test")
def test_real_api_call_feeds_eval_harness_scoring():
    """Integration check: run a real explanation through the eval
    harness's score_explanation() to confirm the two actually work
    together, not just independently.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from evals.eval_harness import score_explanation
    from tollgate.generator.synthetic_fixtures import build_valid_baseline, inject_error
    from tollgate.validation.charset_rule import check_charset

    baseline = build_valid_baseline(seed=2000)
    corrupted, label = inject_error(baseline, RuleId.CHARSET_VIOLATION)
    violations = check_charset(corrupted)
    assert len(violations) >= 1

    explanation = explain_violation(violations[0])
    result = score_explanation(label, explanation)

    print(f"\nReal explanation: {explanation}")
    print(f"Score: {result.score}")

    assert result.score in ("correct", "partial"), (
        f"Expected a real Claude explanation to score at least 'partial', "
        f"got '{result.score}' for explanation: {explanation!r}"
    )
