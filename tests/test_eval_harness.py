"""Tests for tests/evals/eval_harness.py.

The explain/ layer (explain_violation) does not exist yet -- these
tests use deliberately fake explainer functions (good, vague/bad,
hallucinating) to prove the SCORING logic is correct independent of
the AI layer. When explain_violation() is implemented, running a real
eval against it is a one-line change: run_eval(explain_fn=explain_violation).

One real, useful finding surfaced while building these tests: feeding
charset_rule.py's own deterministic `message` string (without its
separate `field_path`) into the scorer only earns "partial," not
"correct" -- because that message describes the cause clearly but
never repeats the field name in prose. This isn't a scoring bug; it's
a reminder that a real explainer needs to combine field_path AND
message (which explain/prompts.py's template already does) rather
than just echoing the message alone.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from evals.eval_harness import EVAL_RESULTS_DIR, run_eval, score_explanation
from tollgate.generator.synthetic_fixtures import GroundTruthLabel
from tollgate.validation.models import RuleId, Violation

SCHEMA_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "tollgate"
    / "schemas"
    / "pacs.008.001.08.xsd"
)


@pytest.fixture(autouse=True)
def clean_eval_results():
    """Eval result files are test output, not fixtures -- clean up
    after each test so the eval_results directory doesn't accumulate
    junk from test runs.
    """
    yield
    if EVAL_RESULTS_DIR.exists():
        for f in EVAL_RESULTS_DIR.glob("*.json"):
            f.unlink()


def _make_label(rule_id: RuleId, field_path: str) -> GroundTruthLabel:
    return GroundTruthLabel(
        rule_id=rule_id,
        field_path=field_path,
        injected_value="test",
        expected_violation_type="test",
    )


def test_score_explanation_correct_case():
    label = _make_label(RuleId.CHARSET_VIOLATION, "FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/Nm")
    result = score_explanation(
        label, "The Debtor Name contains a character outside SWIFT character set X."
    )
    assert result.score == "correct"
    assert result.field_mentioned
    assert result.cause_mentioned


def test_score_explanation_partial_field_only():
    label = _make_label(RuleId.CHARSET_VIOLATION, "FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/Nm")
    result = score_explanation(label, "The Debtor Name field has a problem.")
    assert result.score == "partial"
    assert result.field_mentioned
    assert not result.cause_mentioned


def test_score_explanation_partial_cause_only():
    label = _make_label(RuleId.CHARSET_VIOLATION, "FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/Nm")
    result = score_explanation(label, "There is a character set issue somewhere in this message.")
    assert result.score == "partial"
    assert not result.field_mentioned
    assert result.cause_mentioned


def test_score_explanation_wrong():
    label = _make_label(RuleId.CHARSET_VIOLATION, "FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/Nm")
    result = score_explanation(label, "The settlement date appears to be incorrect.")
    assert result.score == "wrong"


def test_score_explanation_hallucinated():
    """Confidently describing a DIFFERENT rule's specific cause is a
    stronger failure than just missing it -- distinct from "wrong".
    """
    label = _make_label(RuleId.CHARSET_VIOLATION, "FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/Nm")
    result = score_explanation(
        label, "This address has too many free-format address lines, exceeding the limit."
    )
    assert result.score == "hallucinated"


def test_run_eval_with_good_mock_explainer_scores_well():
    """A mock explainer that echoes the deterministic Violation.message
    should score correct or partial across all rule types (correct
    where the message happens to mention the field, partial where it
    doesn't -- see module docstring for the charset_violation case).
    """
    def good_mock(violation: Violation) -> str:
        return violation.message

    result = run_eval(
        explain_fn=good_mock,
        schema_path=SCHEMA_PATH,
        fixtures_per_rule=2,
        write_results=False,
    )

    for rule_id, counts in result["summary"].items():
        assert counts["wrong"] == 0, f"{rule_id} unexpectedly scored 'wrong' with its own deterministic message"
        assert counts["hallucinated"] == 0
        assert counts["detector_failed_to_catch_injected_error"] == 0
        assert counts["correct"] + counts["partial"] == 2


def test_run_eval_with_bad_mock_explainer_scores_poorly():
    def bad_mock(violation: Violation) -> str:
        return "There seems to be a generic problem with this payment message."

    result = run_eval(
        explain_fn=bad_mock,
        schema_path=SCHEMA_PATH,
        fixtures_per_rule=2,
        write_results=False,
    )

    for rule_id, counts in result["summary"].items():
        assert counts["correct"] == 0
        assert counts["wrong"] == 2


def test_run_eval_covers_all_rule_ids_by_default():
    def mock(violation: Violation) -> str:
        return violation.message

    result = run_eval(explain_fn=mock, schema_path=SCHEMA_PATH, fixtures_per_rule=1, write_results=False)
    assert set(result["summary"].keys()) == {rid.value for rid in RuleId}


def test_run_eval_can_target_specific_rule_ids():
    def mock(violation: Violation) -> str:
        return violation.message

    result = run_eval(
        explain_fn=mock,
        schema_path=SCHEMA_PATH,
        rule_ids=[RuleId.CHARSET_VIOLATION],
        fixtures_per_rule=2,
        write_results=False,
    )
    assert set(result["summary"].keys()) == {"charset_violation"}


def test_run_eval_writes_valid_json_when_requested():
    def mock(violation: Violation) -> str:
        return violation.message

    run_eval(
        explain_fn=mock,
        schema_path=SCHEMA_PATH,
        rule_ids=[RuleId.XSD_STRUCTURAL],
        fixtures_per_rule=1,
        write_results=True,
    )

    json_files = list(EVAL_RESULTS_DIR.glob("*.json"))
    assert len(json_files) == 1

    data = json.loads(json_files[0].read_text())
    assert "summary" in data
    assert "results_by_rule" in data
    assert "xsd_structural" in data["summary"]
