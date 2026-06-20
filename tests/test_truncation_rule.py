"""Tests for truncation_rule.py.

The central design risk this rule had, found and fixed before any
code shipped: naively flagging ANY field at exactly 35 or 70 chars
would false-positive on fields whose OWN schema max equals that
boundary (EndToEndId and TwnNm are genuinely Max35Text; AdrLine is
genuinely Max70Text). The false-positive tests below exist
specifically to guard against that regressing.
"""

from tollgate.generator.synthetic_fixtures import build_valid_baseline
from tollgate.validation.models import RuleId
from tollgate.validation.truncation_rule import check_truncation_signals


def test_clean_baseline_has_zero_signals():
    xml_str = build_valid_baseline(seed=42)
    violations = check_truncation_signals(xml_str)
    assert violations == []


def test_name_at_exactly_35_chars_is_flagged():
    """Nm allows up to 140 chars -- landing at exactly 35 (an old MT
    line limit) is a real suspicion signal, not normal usage.
    """
    xml_str = build_valid_baseline(seed=42)
    suspicious_name = "A" * 35
    broken = xml_str.replace("Helena Marsh", suspicious_name, 1)

    violations = check_truncation_signals(broken)
    assert len(violations) >= 1
    assert all(v.rule_id == RuleId.TRUNCATION_SUSPECTED for v in violations)
    assert all(v.severity == "warning" for v in violations), (
        "Truncation signals are heuristics, not certain violations -- "
        "must be severity=warning, never severity=error."
    )


def test_name_at_exactly_70_chars_is_also_flagged():
    """Nm allows up to 140 -- both 35 and 70 are legacy MT boundaries
    smaller than Nm's own max, so both should be flaggable.
    """
    xml_str = build_valid_baseline(seed=42)
    suspicious_name = "B" * 70
    broken = xml_str.replace("Helena Marsh", suspicious_name, 1)

    violations = check_truncation_signals(broken)
    assert len(violations) >= 1


def test_end_to_end_id_at_its_own_max_is_not_a_false_positive():
    """Regression guard: EndToEndId is genuinely Max35Text. A value
    using its full legitimate 35 chars must NOT be flagged -- that's
    normal usage, not a truncation signal. This is the exact
    false-positive trap found during design.
    """
    import re

    xml_str = build_valid_baseline(seed=42)
    match = re.search(r"<EndToEndId>(.*?)</EndToEndId>", xml_str)
    old_id = match.group(1)
    new_id = "E" * 35

    broken = xml_str.replace(f"<EndToEndId>{old_id}</EndToEndId>", f"<EndToEndId>{new_id}</EndToEndId>")
    violations = check_truncation_signals(broken)

    assert violations == [], (
        "False positive: EndToEndId at exactly 35 chars is using its OWN "
        "schema maximum, not hitting a legacy boundary smaller than its "
        "real limit. Flagging this would be wrong."
    )


def test_town_name_at_its_own_max_is_not_a_false_positive():
    """Same trap, different field: TwnNm is genuinely Max35Text."""
    xml_str = build_valid_baseline(seed=42)
    broken = xml_str.replace("Brooklyn", "B" * 35, 1)
    violations = check_truncation_signals(broken)
    assert violations == []


def test_adrline_at_its_own_max_70_is_not_a_false_positive():
    """AdrLine is genuinely Max70Text -- a 70-char line is normal
    full-length usage, not suspicious.
    """
    xml_str = build_valid_baseline(
        seed=42, include_ultimate_parties=True, ultimate_debtor_address_lines=["A" * 70]
    )
    violations = check_truncation_signals(xml_str)
    assert violations == []


def test_adrline_at_35_is_flagged_since_its_own_max_is_70():
    """AdrLine's own max is 70, so landing at exactly 35 IS suspicious
    -- this is the asymmetric case: same field, different boundary,
    different outcome depending on the field's actual schema max.
    """
    xml_str = build_valid_baseline(
        seed=42, include_ultimate_parties=True, ultimate_debtor_address_lines=["B" * 35]
    )
    violations = check_truncation_signals(xml_str)
    assert len(violations) >= 1
    assert any(v.rule_id == RuleId.TRUNCATION_SUSPECTED for v in violations)


def test_field_path_is_human_readable():
    xml_str = build_valid_baseline(seed=42)
    broken = xml_str.replace("Helena Marsh", "A" * 35, 1)
    violations = check_truncation_signals(broken)

    assert len(violations) >= 1
    for v in violations:
        assert "*" not in v.field_path
        assert "[" not in v.field_path
