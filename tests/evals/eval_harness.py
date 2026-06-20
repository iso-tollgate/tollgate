"""Eval harness: scores AI explanations against injected-error ground truth.

Same pattern as the migration-drift project this repo's author has
built before — because the errors are injected by generator/, the
correct violation type is always known, so explanation quality is
scorable rather than judged by feel.

DESIGN NOTE (2026-06-20): the explain/ layer (explain_violation) is
NOT implemented yet -- only the validation rules and inject_error()
are real at this point. Rather than block this module on that, the
harness below is decoupled from the explainer's implementation: it
takes an `explain_fn` callable as a parameter rather than importing
explain_violation directly. This means:
  - The harness can be fully built and tested NOW, against mock
    explanation functions, without waiting on the AI layer.
  - When explain_violation() is implemented, running a real eval is a
    one-line change: run_eval(explain_fn=explain_violation).
  - Tests in tests/test_eval_harness.py use deliberately fake
    explainers (a "good" one, a "bad" one, a "hallucinating" one) to
    prove the SCORING logic is correct independent of the AI layer.

SCORING DESIGN, verified by hand before implementing (see session
notes): a literal substring match of the raw field_path against
explanation text fails even for genuinely good explanations, because
no one writes "FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/Nm" in prose -- they
say "Debtor Name". Scoring therefore uses a synonym map per field tag
and per RuleId, checking whether the explanation mentions the field
(by tag, parent role, or a known synonym) and separately whether it
mentions the right CAUSE (by RuleId-specific synonym terms), then
combines both signals into four categories:
  - "correct":      field mentioned AND cause mentioned
  - "partial":      exactly one of (field, cause) mentioned
  - "wrong":         neither mentioned, AND text doesn't claim a
                      violation that isn't in the ground truth
  - "hallucinated": explanation confidently describes a DIFFERENT
                      specific rule_id's cause terms without matching
                      the actual injected rule_id -- a stronger claim
                      than "wrong", since it means the explainer
                      asserted a specific wrong cause rather than just
                      missing the right one
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from tollgate.generator.synthetic_fixtures import (
    REQUIRES_ULTIMATE_PARTIES_RULE_IDS as REQUIRES_ULTIMATE_PARTIES,
    GroundTruthLabel,
    build_valid_baseline,
    inject_error,
)
from tollgate.validation.address_rule import check_address_structure
from tollgate.validation.charset_rule import check_charset
from tollgate.validation.mandatory_gap_rule import check_mandatory_gaps
from tollgate.validation.models import RuleId, Violation
from tollgate.validation.truncation_rule import check_truncation_signals
from tollgate.validation.xsd_validator import validate_xsd

EVAL_RESULTS_DIR = Path(__file__).parent / "eval_results"

# Synonym terms a human-written explanation would plausibly use for
# each field tag, since no one writes the raw XML path in prose.
# Extend this as new fields get checked by future rules -- don't let
# scoring silently degrade to "wrong" just because a synonym is missing.
FIELD_SYNONYMS: dict[str, list[str]] = {
    "Nm": ["name"],
    "AdrLine": ["address line", "free-format address", "free format address"],
    "TwnNm": ["town"],
    "Ctry": ["country"],
    "ChrgBr": ["charge bearer"],
    "UETR": ["uetr", "unique end-to-end", "transaction reference"],
    "EndToEndId": ["end-to-end id", "end to end id"],
    "UltmtDbtr": ["ultimate debtor"],
    "Dbtr": ["debtor"],
    "PstlAdr": ["postal address", "address"],
}

# Synonym terms for each RuleId's underlying cause -- what a correct
# explanation would plausibly say, not the enum value itself.
RULE_ID_SYNONYMS: dict[RuleId, list[str]] = {
    RuleId.XSD_STRUCTURAL: ["schema", "required element", "mandatory element", "xsd"],
    RuleId.CHARSET_VIOLATION: ["character set", "character", "swift network", "unicode", "accented", "basic latin"],
    RuleId.ADDRESS_FREEFORM_ONLY: ["free-format", "free format", "structured address", "hybrid end-state", "hybrid end state"],
    RuleId.ADDRESS_MISSING_TOWN_COUNTRY: ["town", "country", "structured address"],
    RuleId.ADDRESS_TOO_MANY_LINES: ["too many", "address lines", "exceeds", "line limit"],
    RuleId.TRUNCATION_SUSPECTED: ["truncat", "legacy", "mt line", "cut off", "cut-off", "boundary"],
    RuleId.MANDATORY_FIELD_GAP: ["mandatory", "fedwire", "network-specific", "network specific"],
}

DETECTOR_FOR_RULE: dict[RuleId, str] = {
    RuleId.XSD_STRUCTURAL: "xsd",
    RuleId.CHARSET_VIOLATION: "charset",
    RuleId.ADDRESS_FREEFORM_ONLY: "address",
    RuleId.ADDRESS_MISSING_TOWN_COUNTRY: "address",
    RuleId.ADDRESS_TOO_MANY_LINES: "address",
    RuleId.TRUNCATION_SUSPECTED: "truncation",
    RuleId.MANDATORY_FIELD_GAP: "mandatory_gap",
}


@dataclass
class EvalResult:
    rule_id: str
    field_path: str
    score: str  # "correct" | "partial" | "wrong" | "hallucinated"
    field_mentioned: bool
    cause_mentioned: bool
    explanation_text: str


def _field_mentioned(field_path: str, explanation: str) -> bool:
    """Checks whether the explanation references the violated field,
    by exact tag, parent role segment, or a known synonym -- NOT by
    literal raw-path substring match, which fails on realistic prose.
    """
    text_lower = explanation.lower()
    segments = field_path.split("/")
    for segment in segments:
        if segment.lower() in text_lower:
            return True
        for synonym in FIELD_SYNONYMS.get(segment, []):
            if synonym in text_lower:
                return True
    return False


def _cause_mentioned(rule_id: RuleId, explanation: str) -> bool:
    """Checks whether the explanation describes the actual underlying
    cause for this rule_id, via a synonym-term match against prose
    rather than expecting the enum value to appear literally.
    """
    text_lower = explanation.lower()
    return any(term in text_lower for term in RULE_ID_SYNONYMS.get(rule_id, []))


def _other_rule_mentioned(rule_id: RuleId, explanation: str) -> RuleId | None:
    """Checks whether the explanation's cause terms match a DIFFERENT
    rule_id more specifically than the correct one -- used to
    distinguish "hallucinated" (confidently asserted a different
    specific cause) from plain "wrong" (just missed it).
    """
    for other_id, terms in RULE_ID_SYNONYMS.items():
        if other_id == rule_id:
            continue
        text_lower = explanation.lower()
        if any(term in text_lower for term in terms):
            return other_id
    return None


def score_explanation(label: GroundTruthLabel, explanation: str) -> EvalResult:
    """Pure scoring function -- no AI call here, just comparison logic.
    Kept separate from run_eval() so it can be tested directly against
    hand-written explanation strings without needing fixtures or
    detectors at all.
    """
    field_hit = _field_mentioned(label.field_path, explanation)
    cause_hit = _cause_mentioned(label.rule_id, explanation)

    if field_hit and cause_hit:
        score = "correct"
    elif field_hit or cause_hit:
        score = "partial"
    else:
        wrong_rule = _other_rule_mentioned(label.rule_id, explanation)
        score = "hallucinated" if wrong_rule is not None else "wrong"

    return EvalResult(
        rule_id=label.rule_id.value,
        field_path=label.field_path,
        score=score,
        field_mentioned=field_hit,
        cause_mentioned=cause_hit,
        explanation_text=explanation,
    )


def _run_detector_for_rule(rule_id: RuleId, xml_str: str, schema_path: Path) -> list[Violation]:
    """Runs only the specific detector that corresponds to rule_id --
    the eval harness doesn't need every detector's output, just the
    one relevant to the fixture's injected error.
    """
    if rule_id == RuleId.XSD_STRUCTURAL:
        return validate_xsd(xml_str, schema_path)
    if rule_id == RuleId.CHARSET_VIOLATION:
        return check_charset(xml_str)
    if rule_id in (RuleId.ADDRESS_FREEFORM_ONLY, RuleId.ADDRESS_MISSING_TOWN_COUNTRY, RuleId.ADDRESS_TOO_MANY_LINES):
        return check_address_structure(xml_str)
    if rule_id == RuleId.TRUNCATION_SUSPECTED:
        return check_truncation_signals(xml_str)
    if rule_id == RuleId.MANDATORY_FIELD_GAP:
        return check_mandatory_gaps(xml_str)
    raise ValueError(f"No detector mapped for {rule_id}")


def run_eval(
    explain_fn: Callable[[Violation], str],
    schema_path: Path,
    rule_ids: list[RuleId] | None = None,
    fixtures_per_rule: int = 5,
    seed_start: int = 1000,
    write_results: bool = True,
) -> dict:
    """Runs the full eval loop: generate fixtures, run detectors,
    call explain_fn on each violation, score against ground truth.

    explain_fn is injected rather than imported directly -- pass the
    real explain_violation once it exists, or a mock for testing.
    seed_start defaults to 1000 specifically to avoid colliding with
    the low seeds (1-5) used throughout the existing rule test suites,
    so eval fixtures are distinct from unit-test fixtures.
    """
    target_rule_ids = rule_ids or list(RuleId)
    results_by_rule: dict[str, list[EvalResult]] = {rid.value: [] for rid in target_rule_ids}

    for rule_id in target_rule_ids:
        for i in range(fixtures_per_rule):
            seed = seed_start + i
            needs_ultimate = rule_id in REQUIRES_ULTIMATE_PARTIES
            baseline = build_valid_baseline(seed=seed, include_ultimate_parties=needs_ultimate)
            corrupted_xml, label = inject_error(baseline, rule_id)

            violations = _run_detector_for_rule(rule_id, corrupted_xml, schema_path)
            if not violations:
                # The detector itself failed to catch its own injected
                # error -- a regression in validation logic, not an
                # explainer problem. Surface it rather than silently
                # skipping, since this would otherwise hide a real bug.
                results_by_rule[rule_id.value].append(
                    EvalResult(
                        rule_id=rule_id.value,
                        field_path=label.field_path,
                        score="detector_failed_to_catch_injected_error",
                        field_mentioned=False,
                        cause_mentioned=False,
                        explanation_text="(no violation detected -- explainer was never called)",
                    )
                )
                continue

            explanation = explain_fn(violations[0])
            result = score_explanation(label, explanation)
            results_by_rule[rule_id.value].append(result)

    summary = _summarize(results_by_rule)

    if write_results:
        _write_results(results_by_rule, summary)

    return {"results_by_rule": results_by_rule, "summary": summary}


def _summarize(results_by_rule: dict[str, list[EvalResult]]) -> dict:
    summary = {}
    for rule_id, results in results_by_rule.items():
        counts = {"correct": 0, "partial": 0, "wrong": 0, "hallucinated": 0, "detector_failed_to_catch_injected_error": 0}
        for r in results:
            counts[r.score] = counts.get(r.score, 0) + 1
        summary[rule_id] = counts
    return summary


def _write_results(results_by_rule: dict[str, list[EvalResult]], summary: dict) -> None:
    EVAL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = EVAL_RESULTS_DIR / f"{timestamp}.json"

    serializable = {
        "timestamp": timestamp,
        "summary": summary,
        "results_by_rule": {
            rule_id: [asdict(r) for r in results]
            for rule_id, results in results_by_rule.items()
        },
    }
    output_path.write_text(json.dumps(serializable, indent=2))
