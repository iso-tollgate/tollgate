"""Tests for inject_error() across the address/charset/truncation/mandatory-gap
RuleId values (5 of the project's 8 RuleId values -- xsd_structural is
tested separately since it's not an injector-driven rule the same way,
and currency_decimal_mismatch is NOT currently cross-checked here; see
test_currency_rule.py, which only verifies it against validate_xsd, not
against the other four detectors below).

The property that matters most for eval-harness trustworthiness: each
injected fixture must trigger EXACTLY its own corresponding rule and
no others. If an injector accidentally trips a second, unrelated rule,
the eval harness can't cleanly score "did the AI identify the injected
problem" -- it becomes ambiguous which violation the explanation was
supposed to address. Every test below checks all five of the detectors
imported here against each single-purpose injection, not just the one
it expects to fire.
"""

from pathlib import Path

import pytest

from tollgate.generator.synthetic_fixtures import (
    REQUIRES_ULTIMATE_PARTIES_RULE_IDS as REQUIRES_ULTIMATE_PARTIES,
    build_valid_baseline,
    inject_error,
)
from tollgate.validation.address_rule import check_address_structure
from tollgate.validation.charset_rule import check_charset
from tollgate.validation.mandatory_gap_rule import check_mandatory_gaps
from tollgate.validation.models import RuleId
from tollgate.validation.truncation_rule import check_truncation_signals
from tollgate.validation.xsd_validator import validate_xsd

SCHEMA_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "tollgate"
    / "schemas"
    / "pacs.008.001.08.xsd"
)

# Rule IDs that target UltmtDbtr and therefore require the baseline to
# be built with include_ultimate_parties=True. (Imported above as
# REQUIRES_ULTIMATE_PARTIES from the real module -- this comment is
# kept here as a pointer since the name is referenced throughout this
# file.)

ALL_RULE_IDS = [
    RuleId.XSD_STRUCTURAL,
    RuleId.CHARSET_VIOLATION,
    RuleId.ADDRESS_FREEFORM_ONLY,
    RuleId.ADDRESS_MISSING_TOWN_COUNTRY,
    RuleId.ADDRESS_TOO_MANY_LINES,
    RuleId.TRUNCATION_SUSPECTED,
    RuleId.MANDATORY_FIELD_GAP,
]


def _run_all_detectors(xml_str: str) -> dict[str, list]:
    return {
        "xsd": validate_xsd(xml_str, SCHEMA_PATH),
        "charset": check_charset(xml_str),
        "address": check_address_structure(xml_str),
        "truncation": check_truncation_signals(xml_str),
        "mandatory_gap": check_mandatory_gaps(xml_str),
    }


@pytest.mark.parametrize("rule_id", ALL_RULE_IDS)
def test_injector_triggers_its_own_rule(rule_id):
    baseline = build_valid_baseline(seed=1, include_ultimate_parties=rule_id in REQUIRES_ULTIMATE_PARTIES)
    corrupted, label = inject_error(baseline, rule_id)

    assert label.rule_id == rule_id
    assert label.field_path
    assert label.expected_violation_type

    results = _run_all_detectors(corrupted)
    detector_map = {
        RuleId.XSD_STRUCTURAL: "xsd",
        RuleId.CHARSET_VIOLATION: "charset",
        RuleId.ADDRESS_FREEFORM_ONLY: "address",
        RuleId.ADDRESS_MISSING_TOWN_COUNTRY: "address",
        RuleId.ADDRESS_TOO_MANY_LINES: "address",
        RuleId.TRUNCATION_SUSPECTED: "truncation",
        RuleId.MANDATORY_FIELD_GAP: "mandatory_gap",
    }
    own_detector = detector_map[rule_id]
    assert len(results[own_detector]) >= 1, (
        f"Injecting {rule_id} should trigger the {own_detector} detector, "
        f"but it found nothing."
    )


@pytest.mark.parametrize("rule_id", ALL_RULE_IDS)
def test_injector_does_not_trigger_unrelated_rules(rule_id):
    """The cross-contamination check: a clean single-purpose injection
    should not accidentally trip a different rule's detector.
    """
    baseline = build_valid_baseline(seed=1, include_ultimate_parties=rule_id in REQUIRES_ULTIMATE_PARTIES)
    corrupted, label = inject_error(baseline, rule_id)
    results = _run_all_detectors(corrupted)

    detector_map = {
        RuleId.XSD_STRUCTURAL: "xsd",
        RuleId.CHARSET_VIOLATION: "charset",
        RuleId.ADDRESS_FREEFORM_ONLY: "address",
        RuleId.ADDRESS_MISSING_TOWN_COUNTRY: "address",
        RuleId.ADDRESS_TOO_MANY_LINES: "address",
        RuleId.TRUNCATION_SUSPECTED: "truncation",
        RuleId.MANDATORY_FIELD_GAP: "mandatory_gap",
    }
    own_detector = detector_map[rule_id]

    for detector_name, violations in results.items():
        if detector_name == own_detector:
            continue
        assert violations == [], (
            f"Injecting {rule_id} unexpectedly triggered the unrelated "
            f"{detector_name} detector: {violations}. Each injector must "
            f"produce exactly one unambiguous problem."
        )


def test_address_injectors_raise_clear_error_without_ultimate_parties():
    """ADDRESS_FREEFORM_ONLY and ADDRESS_TOO_MANY_LINES target
    UltmtDbtr -- calling them on a baseline without
    include_ultimate_parties=True should fail clearly, not silently
    no-op.
    """
    baseline = build_valid_baseline(seed=1, include_ultimate_parties=False)

    with pytest.raises(ValueError, match="include_ultimate_parties"):
        inject_error(baseline, RuleId.ADDRESS_FREEFORM_ONLY)

    with pytest.raises(ValueError, match="include_ultimate_parties"):
        inject_error(baseline, RuleId.ADDRESS_TOO_MANY_LINES)


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("rule_id", ALL_RULE_IDS)
def test_injectors_work_across_multiple_seeds(rule_id, seed):
    """Tree-based modification (vs. string replacement) should be
    robust to whatever random data the generator produces for a given
    seed -- this is the whole reason tree manipulation was chosen over
    string matching during design.
    """
    baseline = build_valid_baseline(seed=seed, include_ultimate_parties=rule_id in REQUIRES_ULTIMATE_PARTIES)
    corrupted, label = inject_error(baseline, rule_id)
    assert corrupted != baseline
    assert label.rule_id == rule_id
