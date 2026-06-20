"""Tests for mandatory_gap_rule.py.

This rule's premise was corrected before implementation: the original
docstring cited specific FAIM tag numbers as having "no equivalent" in
MX, sourced secondhand and never actually verified against a primary
document. That framing was replaced with the UETR finding below, which
IS independently verified against both the real vendored XSD (UETR is
optional, minOccurs=0) and a primary regulator source (the Federal
Reserve's own FAQ stating UETR is mandatory for Fedwire). See
docs/SOURCES.md#fedwire-faim-comparison for the unverified original
claim, kept visible rather than silently deleted.
"""

import re
from pathlib import Path

from tollgate.generator.synthetic_fixtures import build_valid_baseline
from tollgate.validation.mandatory_gap_rule import check_mandatory_gaps
from tollgate.validation.models import RuleId
from tollgate.validation.xsd_validator import validate_xsd

SCHEMA_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "tollgate"
    / "schemas"
    / "pacs.008.001.08.xsd"
)


def test_clean_baseline_with_uetr_has_zero_gaps():
    xml_str = build_valid_baseline(seed=42)
    assert "<UETR>" in xml_str, "Generator's baseline should include UETR by default"
    violations = check_mandatory_gaps(xml_str)
    assert violations == []


def test_missing_uetr_passes_xsd_but_fails_mandatory_gap_check():
    """The core showcase claim: UETR is genuinely optional in the XSD
    (minOccurs=0) but the Federal Reserve's own FAQ says it's
    mandatory for Fedwire-bound pacs.008 messages. A message without
    it should be schema-valid and still flagged here.
    """
    xml_str = build_valid_baseline(seed=42)
    broken = re.sub(r"<UETR>.*?</UETR>\n?\s*", "", xml_str)
    assert "<UETR>" not in broken

    xsd_violations = validate_xsd(broken, SCHEMA_PATH)
    gap_violations = check_mandatory_gaps(broken)

    assert xsd_violations == [], "UETR is genuinely optional at the schema level"
    assert len(gap_violations) >= 1
    assert all(v.rule_id == RuleId.MANDATORY_FIELD_GAP for v in gap_violations)


def test_violation_mentions_fedwire_specifically_not_universal():
    """The explanation must be honest about scope -- this is a
    Fedwire-specific requirement, not a universal ISO 20022 rule.
    Overclaiming here would be exactly the kind of thing the project
    is not supposed to do.
    """
    xml_str = build_valid_baseline(seed=42)
    broken = re.sub(r"<UETR>.*?</UETR>\n?\s*", "", xml_str)
    violations = check_mandatory_gaps(broken)

    assert len(violations) >= 1
    assert any("fedwire" in v.message.lower() for v in violations)
    assert any("not a universal" in v.message.lower() for v in violations)


def test_missing_pmtid_entirely_is_not_double_flagged():
    """If PmtId itself is missing, that's an XSD-level concern (PmtId
    is mandatory) -- this rule should not also try to flag a missing
    UETR inside a PmtId that doesn't exist.
    """
    xml_str = build_valid_baseline(seed=42)
    broken = re.sub(r"<PmtId>.*?</PmtId>\n?\s*", "", xml_str, flags=re.DOTALL)
    assert "<PmtId>" not in broken

    violations = check_mandatory_gaps(broken)
    assert violations == [], (
        "Should not flag a missing UETR when PmtId itself is absent -- "
        "that's a separate, XSD-level problem."
    )
