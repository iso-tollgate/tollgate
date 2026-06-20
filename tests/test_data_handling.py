"""Tests verifying Tollgate does not send sensitive payment data
(real names, addresses, etc.) to the Anthropic API.

BACKGROUND: an earlier version of explainer.py sent
Violation.raw_value to the API verbatim. For charset_violation and
truncation_suspected, raw_value can contain the full content of a
sensitive field -- e.g. a real person's name taken directly from a
real payment message ("Helena Müller"). Sending that to a third-party
API without explicit user consent is not acceptable for a tool whose
entire premise is processing real bank payment data. Fixed by
removing raw_value from the prompt template entirely -- checked first
that it wasn't actually needed for explanation quality (it wasn't;
every rule's `message` field already isolates only the safe-to-send
detail).

These tests mock the Anthropic client to inspect exactly what's sent,
rather than relying on the live API (which isn't available in this
sandbox) -- this verifies the DATA HANDLING property specifically,
independent of whether a live call has been tested.
"""

from unittest.mock import MagicMock, patch

from tollgate.explain.explainer import explain_violation
from tollgate.explain.prompts import EXPLAIN_VIOLATION_USER_TEMPLATE
from tollgate.generator.synthetic_fixtures import build_valid_baseline, inject_error
from tollgate.validation.charset_rule import check_charset
from tollgate.validation.models import RuleId
from tollgate.validation.truncation_rule import check_truncation_signals


def _mock_anthropic_response(text: str = "mocked explanation"):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=text)]
    return mock_response


def test_prompt_template_has_no_raw_value_placeholder():
    """The template itself must not reference raw_value at all -- this
    is checked at the template level, not just by mocking a call,
    since the template is the single place this could be reintroduced.
    """
    assert "{raw_value}" not in EXPLAIN_VIOLATION_USER_TEMPLATE
    assert "raw_value" not in EXPLAIN_VIOLATION_USER_TEMPLATE.lower()


def test_charset_violation_real_name_never_sent_to_api(monkeypatch):
    """The motivating case: a real name with a sensitive character
    must not appear in the actual API payload, even though it's
    present in Violation.raw_value locally.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")

    baseline = build_valid_baseline(seed=1)
    broken, _ = inject_error(baseline, RuleId.CHARSET_VIOLATION)
    violation = check_charset(broken)[0]

    # Confirm the sensitive value really is present locally first --
    # otherwise this test would trivially pass for the wrong reason.
    assert violation.raw_value == "Helena Müller"

    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()
        mock_anthropic_cls.return_value = mock_client

        explain_violation(violation)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        sent_messages = call_kwargs["messages"]
        sent_content = sent_messages[0]["content"]

        assert "Helena Müller" not in sent_content, (
            f"The real name 'Helena Müller' (from raw_value) must never "
            f"appear in the API payload. Sent content was: {sent_content!r}"
        )


def test_truncation_suspected_raw_value_never_sent_to_api(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")

    baseline = build_valid_baseline(seed=1)
    broken, _ = inject_error(baseline, RuleId.TRUNCATION_SUSPECTED)
    violation = check_truncation_signals(broken)[0]

    assert violation.raw_value is not None
    sensitive_value = violation.raw_value

    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()
        mock_anthropic_cls.return_value = mock_client

        explain_violation(violation)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        sent_content = call_kwargs["messages"][0]["content"]

        assert sensitive_value not in sent_content


def test_safe_information_is_still_sent_for_explanation_quality(monkeypatch):
    """The fix shouldn't have removed information the explainer
    actually needs -- field_path, the deterministic message (which
    already isolates safe details like the specific character or
    exact length), rule_id, and source_ref should all still be sent.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")

    baseline = build_valid_baseline(seed=1)
    broken, _ = inject_error(baseline, RuleId.CHARSET_VIOLATION)
    violation = check_charset(broken)[0]

    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()
        mock_anthropic_cls.return_value = mock_client

        explain_violation(violation)

        sent_content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]

        assert violation.field_path in sent_content
        assert violation.rule_id.value in sent_content
        assert "ü" in sent_content  # the isolated, safe-to-send character from `message`
        assert violation.source_ref in sent_content
