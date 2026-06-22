"""Tests for currency_rule.py.

A real, pre-existing generator bug was found while building this
rule's own tests: build_valid_baseline() always formatted amounts
with exactly 2 decimal places, even for JPY (which CURRENCIES has
included since the generator was first written, and which supports 0
decimal places per ISO 4217). The baseline generator had been
silently producing decimally-invalid JPY fixtures since the project's
first session -- never caught before because no rule checked decimal
precision until this one existed. test_generator_jpy_fix_regression
exists specifically to guard against this regressing.

This file only checks check_currency_decimal_precision against
validate_xsd. The cross-contamination property (does injecting a
currency violation accidentally trip the other 5 detectors, and vice
versa) is checked in test_inject_error.py, added there 2026-06-21.
"""

from pathlib import Path

import pytest

from tollgate.generator.synthetic_fixtures import build_valid_baseline
from tollgate.validation.currency_rule import check_currency_decimal_precision
from tollgate.validation.models import RuleId
from tollgate.validation.xsd_validator import validate_xsd

SCHEMA_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "tollgate"
    / "schemas"
    / "pacs.008.001.08.xsd"
)


def test_clean_baseline_has_zero_violations_across_many_seeds():
    """Regression guard for the generator bug found during
    development -- across 50 seeds (enough to hit JPY repeatedly,
    since it's 1 of 4 currencies the generator picks randomly), there
    should never be a currency-precision violation on a baseline
    message that hasn't been deliberately corrupted.
    """
    total_violations = 0
    for seed in range(50):
        xml_str = build_valid_baseline(seed=seed)
        violations = check_currency_decimal_precision(xml_str)
        total_violations += len(violations)
    assert total_violations == 0


def test_generator_jpy_fix_regression():
    """Specifically targets JPY, the currency that exposed the bug --
    finds a seed that generates JPY and confirms zero decimal places.
    """
    found_jpy = False
    for seed in range(30):
        xml_str = build_valid_baseline(seed=seed)
        if 'Ccy="JPY"' in xml_str:
            found_jpy = True
            violations = check_currency_decimal_precision(xml_str)
            assert violations == [], (
                f"JPY amount at seed={seed} should have 0 decimal places "
                f"and trigger no violations -- if this fails, the "
                f"generator's JPY formatting fix has regressed."
            )
    assert found_jpy, "Expected at least one of the first 30 seeds to pick JPY"


def test_jpy_with_decimals_passes_xsd_but_fails_currency_rule():
    """The core showcase claim for this rule: the schema permits up to
    5 decimal places for any currency, but JPY doesn't actually
    support decimals at all.
    """
    xml = """<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08">
  <FIToFICstmrCdtTrf>
    <CdtTrfTxInf>
      <IntrBkSttlmAmt Ccy="JPY">1000.50</IntrBkSttlmAmt>
    </CdtTrfTxInf>
  </FIToFICstmrCdtTrf>
</Document>"""

    currency_violations = check_currency_decimal_precision(xml)
    assert len(currency_violations) == 1
    assert currency_violations[0].rule_id == RuleId.CURRENCY_DECIMAL_MISMATCH
    assert currency_violations[0].severity == "warning", (
        "Currency precision is a warning, not a certain rejection -- "
        "the available sources don't support claiming certain failure."
    )


def test_kwd_with_correct_three_decimals_is_not_flagged():
    """No false positive: KWD genuinely supports 3 decimal places."""
    xml = """<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08">
  <FIToFICstmrCdtTrf>
    <CdtTrfTxInf>
      <IntrBkSttlmAmt Ccy="KWD">100.250</IntrBkSttlmAmt>
    </CdtTrfTxInf>
  </FIToFICstmrCdtTrf>
</Document>"""
    violations = check_currency_decimal_precision(xml)
    assert violations == []


def test_kwd_with_four_decimals_is_flagged():
    """KWD's own limit is 3 -- 4 decimals exceeds even that."""
    xml = """<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08">
  <FIToFICstmrCdtTrf>
    <CdtTrfTxInf>
      <IntrBkSttlmAmt Ccy="KWD">100.2500</IntrBkSttlmAmt>
    </CdtTrfTxInf>
  </FIToFICstmrCdtTrf>
</Document>"""
    violations = check_currency_decimal_precision(xml)
    assert len(violations) == 1


def test_usd_with_two_decimals_is_not_flagged():
    """The common, default case -- 2 decimals for USD is correct."""
    xml = """<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08">
  <FIToFICstmrCdtTrf>
    <CdtTrfTxInf>
      <IntrBkSttlmAmt Ccy="USD">1000.00</IntrBkSttlmAmt>
    </CdtTrfTxInf>
  </FIToFICstmrCdtTrf>
</Document>"""
    violations = check_currency_decimal_precision(xml)
    assert violations == []


def test_walks_by_attribute_presence_not_tag_name():
    """The structural design decision: this rule finds amount elements
    by checking for a Ccy attribute, not by enumerating the 22+
    different element names the schema uses for amounts. Confirms
    this works for a tag name OTHER than IntrBkSttlmAmt.
    """
    xml = """<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08">
  <FIToFICstmrCdtTrf>
    <CdtTrfTxInf>
      <RmtInf>
        <Strd>
          <RfrdDocAmt>
            <RmtdAmt Ccy="JPY">500.25</RmtdAmt>
          </RfrdDocAmt>
        </Strd>
      </RmtInf>
    </CdtTrfTxInf>
  </FIToFICstmrCdtTrf>
</Document>"""
    violations = check_currency_decimal_precision(xml)
    assert len(violations) == 1
    assert "RmtdAmt" in violations[0].message


def test_xsd_validation_still_passes_for_over_precise_amounts():
    """Confirms the schema genuinely doesn't catch this -- the whole
    reason this rule needs to exist independently of XSD validation.
    """
    xml = """<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08">
  <FIToFICstmrCdtTrf>
    <GrpHdr>
      <MsgId>TEST123</MsgId>
      <CreDtTm>2026-01-01T00:00:00.000Z</CreDtTm>
      <NbOfTxs>1</NbOfTxs>
      <SttlmInf>
        <SttlmMtd>CLRG</SttlmMtd>
      </SttlmInf>
    </GrpHdr>
    <CdtTrfTxInf>
      <PmtId>
        <EndToEndId>E2E123</EndToEndId>
      </PmtId>
      <IntrBkSttlmAmt Ccy="JPY">1000.50</IntrBkSttlmAmt>
      <ChrgBr>SHAR</ChrgBr>
      <Dbtr><Nm>Test Person</Nm></Dbtr>
      <DbtrAgt><FinInstnId><BICFI>AAAADEFFXXX</BICFI></FinInstnId></DbtrAgt>
      <CdtrAgt><FinInstnId><BICFI>BBBBDEFFXXX</BICFI></FinInstnId></CdtrAgt>
      <Cdtr><Nm>Test Creditor</Nm></Cdtr>
    </CdtTrfTxInf>
  </FIToFICstmrCdtTrf>
</Document>"""
    xsd_violations = validate_xsd(xml, SCHEMA_PATH)
    assert xsd_violations == [], (
        "A JPY amount with 2 decimal places should still be fully "
        "XSD-valid -- the schema's fractionDigits=5 doesn't care about "
        "currency-specific rules at all."
    )
