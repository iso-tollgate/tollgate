"""Tests for address_rule.py.

Several tests here specifically guard against bugs found and fixed
during development before any code shipped:
  - ChrgsInf was wrongly included in INTERIM_STATE_ROLES as if it had
    a PstlAdr directly underneath; it doesn't (Charges7 is Amt + Agt).
  - Agent roles (DbtrAgt, CdtrAgt, IntrmyAgt*, PrvsInstgAgt*) have
    PstlAdr nested one level deeper (under FinInstnId) than party
    roles (Dbtr, Cdtr, UltmtDbtr) -- a naive "role_tag/PstlAdr" search
    would silently miss every agent-role address.
"""

from pathlib import Path

import pytest

from tollgate.generator.synthetic_fixtures import build_valid_baseline
from tollgate.validation.address_rule import check_address_structure
from tollgate.validation.models import RuleId
from tollgate.validation.xsd_validator import validate_xsd

SCHEMA_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "tollgate"
    / "schemas"
    / "pacs.008.001.08.xsd"
)


def test_clean_structured_only_baseline_has_zero_violations():
    xml_str = build_valid_baseline(seed=42, include_ultimate_parties=True)
    violations = check_address_structure(xml_str)
    assert violations == []


def test_too_many_adrlines_on_hybrid_role_is_caught():
    """The core showcase claim: schema allows AdrLine maxOccurs=7,
    Fedwire hybrid end-state guideline allows only 2. A message with
    5 lines is schema-valid and still violates the guideline.
    """
    xml_str = build_valid_baseline(
        seed=42,
        include_ultimate_parties=True,
        ultimate_debtor_address_lines=[
            "Line one", "Line two", "Line three", "Line four", "Line five",
        ],
    )

    xsd_violations = validate_xsd(xml_str, SCHEMA_PATH)
    addr_violations = check_address_structure(xml_str)

    assert xsd_violations == [], "5 AdrLines should still be schema-valid (max is 7)"
    assert len(addr_violations) >= 1
    assert any(v.rule_id == RuleId.ADDRESS_TOO_MANY_LINES for v in addr_violations)


def test_freeform_only_on_hybrid_role_is_caught():
    """Hybrid end-state roles (UltmtDbtr, InitgPty, UltmtCdtr) require
    TwnNm + Ctry even when AdrLine is also used -- free-format alone
    is not permitted for these roles, unlike interim-state roles.
    """
    xml_str = build_valid_baseline(seed=42, include_ultimate_parties=True)
    broken = xml_str.replace(
        "<TwnNm>Brooklyn</TwnNm>\n          <Ctry>US</Ctry>",
        "<AdrLine>123 Main Street</AdrLine>",
    )

    violations = check_address_structure(broken)
    assert any(v.rule_id == RuleId.ADDRESS_FREEFORM_ONLY for v in violations)


def test_agent_role_address_depth_is_found_correctly():
    """Regression guard for the depth bug: agent roles (DbtrAgt etc.)
    have PstlAdr nested under FinInstnId, not directly under the role
    tag. If this regresses to a naive role_tag/PstlAdr search, this
    test's violation count drops to zero and the field_path assertion
    fails.
    """
    xml_str = build_valid_baseline(seed=42)
    broken = xml_str.replace(
        "<BICFI>HBVWUS66</BICFI>\n          <Nm>Harborview Federal Bank</Nm>",
        (
            "<BICFI>HBVWUS66</BICFI>\n          <Nm>Harborview Federal Bank</Nm>"
            "\n          <PstlAdr><TwnNm>Seattle</TwnNm><Ctry>US</Ctry>"
            "<AdrLine>456 Pine Street</AdrLine></PstlAdr>"
        ),
    )

    xsd_violations = validate_xsd(broken, SCHEMA_PATH)
    violations = check_address_structure(broken)

    assert xsd_violations == []
    assert len(violations) >= 1
    assert any("DbtrAgt/FinInstnId/PstlAdr" in v.field_path for v in violations), (
        "Expected field_path to show the nested FinInstnId/PstlAdr depth. "
        "If this fails, the depth-search logic may have regressed to "
        "assuming PstlAdr sits directly under the role tag."
    )


def test_chrgsinf_is_not_treated_as_having_direct_postal_address():
    """ChrgsInf (Charges7) is Amt + Agt with no PstlAdr of its own --
    it must not be in INTERIM_STATE_ROLES as if it had a direct
    address. This test exists to catch that specific regression.
    """
    from tollgate.validation.address_rule import INTERIM_STATE_ROLES

    assert "ChrgsInf" not in INTERIM_STATE_ROLES, (
        "ChrgsInf has no PstlAdr directly underneath it (Charges7 is "
        "Amt + Agt) -- including it here was a bug found and fixed "
        "before this code shipped. See module docstring for the "
        "correction note."
    )


def test_interim_role_combining_structured_and_freeform_is_caught():
    xml_str = build_valid_baseline(seed=42)
    broken = xml_str.replace(
        "<TwnNm>Brooklyn</TwnNm>\n          <Ctry>US</Ctry>",
        "<TwnNm>Brooklyn</TwnNm>\n          <Ctry>US</Ctry>\n          <AdrLine>Extra free line</AdrLine>",
    )

    violations = check_address_structure(broken)
    assert any(
        v.rule_id == RuleId.ADDRESS_FREEFORM_ONLY and "Dbtr" in v.field_path
        for v in violations
    )


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_generator_with_ultimate_parties_always_valid_across_seeds(seed):
    xml_str = build_valid_baseline(seed=seed, include_ultimate_parties=True)
    xsd_violations = validate_xsd(xml_str, SCHEMA_PATH)
    addr_violations = check_address_structure(xml_str)
    assert xsd_violations == []
    assert addr_violations == []
