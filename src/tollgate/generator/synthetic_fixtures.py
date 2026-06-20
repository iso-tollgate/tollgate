"""Generates baseline-valid pacs.008 messages and labeled corrupted variants.

Structure below is grounded in the actual vendored XSD
(schemas/pacs.008.001.08.xsd), verified field-by-field on 2026-06-20 —
not assumed from memory. Specifically confirmed against the schema:

  Document
    FIToFICstmrCdtTrf (FIToFICustomerCreditTransferV08)
      GrpHdr (GroupHeader93)            -- mandatory
        MsgId, CreDtTm, NbOfTxs, SttlmInf  -- mandatory children
      CdtTrfTxInf (CreditTransferTransaction39), 1..unbounded
        PmtId (PaymentIdentification7) -- mandatory; EndToEndId mandatory within
        IntrBkSttlmAmt (w/ Ccy attr)   -- mandatory
        ChrgBr                         -- mandatory, enum DEBT/CRED/SHAR/SLEV
        DbtrAgt, CdtrAgt               -- mandatory
        Dbtr, Cdtr                     -- mandatory (PartyIdentification135)
        UltmtDbtr, InitgPty, UltmtCdtr -- optional, but hybrid-end-state
                                            address rules apply when present

PartyIdentification135.PstlAdr -> PostalAddress24, which has AdrLine
maxOccurs="7" (confirmed) -- more permissive than the Fedwire
hybrid-end-state 2-line limit, which is exactly why address_rule.py
needs to exist as a non-XSD check.

inject_error() corruption modes are deliberately limited to the rules
documented in docs/SOURCES.md -- don't add a corruption mode without
a traceable source.
"""

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree

from tollgate.validation.models import RuleId

NS = "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08"
NSMAP = {None: NS}

# Realistic but explicitly fictional data -- not modeled on any real
# bank or person. Plausible enough that a generated message resembles
# real-world output, which matters because unrealistic filler (e.g.
# "ACME Corp", "XXXXUS00XXX") makes it too easy for the AI explainer
# to "succeed" on fixtures that don't resemble anything a real
# conversion pipeline would produce.
FICTIONAL_DEBTOR_BANKS = [
    ("Meridian Trust Bank", "MTBKUS33XXX"),
    ("Cascade National Bank", "CSCDUS44XXX"),
    ("Harborview Federal Bank", "HBVWUS66"),
]
FICTIONAL_CREDITOR_BANKS = [
    ("Northbridge Commercial Bank", "NBCBDEFFXXX"),
    ("Lakeside Cooperative Bank", "LKSDGB2LXXX"),
    ("Summit Pacific Bank", "SMPCJPJTXXX"),
]
FICTIONAL_DEBTOR_NAMES = ["Helena Marsh", "Daniel Okafor", "Priya Chandrasekaran"]
FICTIONAL_CREDITOR_NAMES = ["Tomas Becker", "Aiko Fujimoto", "Liam O'Sullivan"]
CURRENCIES = ["USD", "EUR", "GBP", "JPY"]


@dataclass
class GroundTruthLabel:
    """What the eval harness scores the AI explanation against."""

    rule_id: RuleId
    field_path: str
    injected_value: str
    expected_violation_type: str


# Rule IDs whose injector targets UltmtDbtr, which only exists in a
# baseline built with include_ultimate_parties=True. Promoted here
# (2026-06-20) from what had been a duplicated test-local constant in
# tests/test_inject_error.py and tests/evals/eval_harness.py -- now
# that the CLI's `generate` command also needs this mapping, it gets
# one real source of truth instead of three independently-maintained
# copies that could silently drift out of sync.
REQUIRES_ULTIMATE_PARTIES_RULE_IDS = {RuleId.ADDRESS_FREEFORM_ONLY, RuleId.ADDRESS_TOO_MANY_LINES}


def _el(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
    """Shorthand for creating a sub-element, optionally with text content."""
    child = etree.SubElement(parent, tag)
    if text is not None:
        child.text = text
    return child


def _build_postal_address(
    parent: etree._Element,
    *,
    town: str,
    country: str,
    street: str | None = None,
    building_number: str | None = None,
    post_code: str | None = None,
    address_lines: list[str] | None = None,
) -> etree._Element:
    """Builds a PostalAddress24 element. Order of children matters in
    XSD sequence validation -- this follows the schema's declared
    order exactly (StrtNm, BldgNb, ... PstCd, TwnNm, ... Ctry, AdrLine).
    """
    pstl_adr = etree.Element("PstlAdr")
    if street:
        _el(pstl_adr, "StrtNm", street)
    if building_number:
        _el(pstl_adr, "BldgNb", building_number)
    if post_code:
        _el(pstl_adr, "PstCd", post_code)
    _el(pstl_adr, "TwnNm", town)
    _el(pstl_adr, "Ctry", country)
    if address_lines:
        for line in address_lines:
            _el(pstl_adr, "AdrLine", line)
    parent.append(pstl_adr)
    return pstl_adr


def _build_party(
    name: str,
    *,
    town: str = "Brooklyn",
    country: str = "US",
    address_lines: list[str] | None = None,
) -> etree._Element:
    """Builds a PartyIdentification135-shaped element (Nm + PstlAdr).
    Caller is responsible for renaming/wrapping into the right tag
    (Dbtr, Cdtr, UltmtDbtr, etc.) since lxml elements carry their tag
    name at creation time.
    """
    party = etree.Element("_placeholder_")
    _el(party, "Nm", name)
    _build_postal_address(party, town=town, country=country, address_lines=address_lines)
    return party


def _build_agent(bank_name: str, bic: str) -> etree._Element:
    """Builds a BranchAndFinancialInstitutionIdentification6-shaped
    element using BICFI -- the simpler, more common path. The
    ClrSysMmbId/routing-number path (used for the US Treasury tax
    payment gotcha) is exercised separately in inject_error(), not
    in the baseline, since it's not the common case.
    """
    agt = etree.Element("_placeholder_")
    fin_instn_id = _el(agt, "FinInstnId")
    _el(fin_instn_id, "BICFI", bic)
    _el(fin_instn_id, "Nm", bank_name)
    return agt


def _retag(element: etree._Element, new_tag: str) -> etree._Element:
    """lxml has no direct rename; rebuild with the new tag, same children."""
    element.tag = new_tag
    return element


def build_valid_baseline(
    seed: int | None = None,
    *,
    include_ultimate_parties: bool = False,
    ultimate_debtor_address_lines: list[str] | None = None,
) -> str:
    """Builds one realistic, schema-valid pacs.008.001.08 message as
    a UTF-8 XML string. Single transaction (CdtTrfTxInf), no optional
    fields beyond what makes the message realistic by default.

    include_ultimate_parties=True adds UltmtDbtr and UltmtCdtr
    (PartyIdentification135-shaped, hybrid-end-state address roles)
    so address_rule.py has fixtures to exercise -- the schema element
    order is UltmtDbtr, InitgPty, Dbtr, ..., Cdtr, UltmtCdtr (verified
    against the vendored XSD), so these must be inserted at the
    correct position, not just appended after Cdtr.

    ultimate_debtor_address_lines lets a caller (typically
    inject_error or a test) directly control the UltmtDbtr's AdrLine
    content -- e.g. passing more than 2 lines to exercise the
    ADDRESS_TOO_MANY_LINES check, or omitting TwnNm/Ctry to exercise
    ADDRESS_FREEFORM_ONLY. Only meaningful when
    include_ultimate_parties=True.
    """
    rng = random.Random(seed)

    debtor_bank_name, debtor_bic = rng.choice(FICTIONAL_DEBTOR_BANKS)
    creditor_bank_name, creditor_bic = rng.choice(FICTIONAL_CREDITOR_BANKS)
    debtor_name = rng.choice(FICTIONAL_DEBTOR_NAMES)
    creditor_name = rng.choice(FICTIONAL_CREDITOR_NAMES)
    currency = rng.choice(CURRENCIES)
    amount = f"{rng.uniform(100, 50000):.2f}"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    msg_id = f"MSGID{rng.randint(10**9, 10**10 - 1)}"
    end_to_end_id = f"E2E{rng.randint(10**9, 10**10 - 1)}"

    document = etree.Element("Document", nsmap=NSMAP)
    fi_to_fi = _el(document, "FIToFICstmrCdtTrf")

    # GroupHeader93 -- mandatory children per schema: MsgId, CreDtTm,
    # NbOfTxs, SttlmInf (in that sequence order).
    grp_hdr = _el(fi_to_fi, "GrpHdr")
    _el(grp_hdr, "MsgId", msg_id)
    _el(grp_hdr, "CreDtTm", now)
    _el(grp_hdr, "NbOfTxs", "1")
    sttlm_inf = _el(grp_hdr, "SttlmInf")
    _el(sttlm_inf, "SttlmMtd", "CLRG")  # clearing-system settlement

    # CreditTransferTransaction39
    tx = _el(fi_to_fi, "CdtTrfTxInf")

    pmt_id = _el(tx, "PmtId")
    _el(pmt_id, "EndToEndId", end_to_end_id)
    _el(pmt_id, "UETR", str(uuid.uuid4()))

    intr_bk_sttlm_amt = _el(tx, "IntrBkSttlmAmt", amount)
    intr_bk_sttlm_amt.set("Ccy", currency)

    _el(tx, "ChrgBr", "SHAR")

    # Schema sequence order: UltmtDbtr, InitgPty, Dbtr, DbtrAgt, ...,
    # CdtrAgt, Cdtr, UltmtCdtr -- verified against the vendored XSD.
    if include_ultimate_parties:
        ultmt_dbtr = _retag(
            _build_party(
                debtor_name,
                town="Brooklyn",
                country="US",
                address_lines=ultimate_debtor_address_lines,
            ),
            "UltmtDbtr",
        )
        tx.append(ultmt_dbtr)

    dbtr = _retag(_build_party(debtor_name, town="Brooklyn", country="US"), "Dbtr")
    tx.append(dbtr)

    dbtr_agt = _retag(_build_agent(debtor_bank_name, debtor_bic), "DbtrAgt")
    tx.append(dbtr_agt)

    cdtr_agt = _retag(_build_agent(creditor_bank_name, creditor_bic), "CdtrAgt")
    tx.append(cdtr_agt)

    cdtr = _retag(_build_party(creditor_name, town="Berlin", country="DE"), "Cdtr")
    tx.append(cdtr)

    if include_ultimate_parties:
        ultmt_cdtr = _retag(
            _build_party(creditor_name, town="Berlin", country="DE"), "UltmtCdtr"
        )
        tx.append(ultmt_cdtr)

    return etree.tostring(
        document, xml_declaration=True, encoding="UTF-8", pretty_print=True
    ).decode("utf-8")


def _parse(xml_str: str) -> tuple[etree._Element, dict]:
    """Parses baseline XML and returns (root, nsmap_for_xpath) --
    nsmap_for_xpath has the default namespace bound to prefix 'p',
    since lxml's find()/findall() require a prefix (None doesn't work
    for the default namespace in XPath expressions).
    """
    root = etree.fromstring(xml_str.encode("utf-8"))
    default_ns = root.nsmap.get(None)
    nsmap = {"p": default_ns} if default_ns else {}
    return root, nsmap


def _serialize(root: etree._Element) -> str:
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=True
    ).decode("utf-8")


def _inject_xsd_structural(root: etree._Element, nsmap: dict) -> tuple[etree._Element, GroundTruthLabel]:
    """Removes the mandatory ChrgBr element entirely. Same corruption
    used throughout this project's own tests (xsd_validator.py) --
    reusing a known, unambiguous mandatory-element-missing case rather
    than inventing a new one.
    """
    chrg_br = root.find(".//p:ChrgBr", nsmap)
    parent = chrg_br.getparent()
    parent.remove(chrg_br)

    label = GroundTruthLabel(
        rule_id=RuleId.XSD_STRUCTURAL,
        field_path="FIToFICstmrCdtTrf/CdtTrfTxInf/ChrgBr",
        injected_value="(element removed entirely)",
        expected_violation_type="missing mandatory element (ChrgBr)",
    )
    return root, label


def _inject_charset_violation(root: etree._Element, nsmap: dict) -> tuple[etree._Element, GroundTruthLabel]:
    """Replaces the Debtor's name with one containing a character
    outside SWIFT's character set X. 'ü' chosen because it's the same
    case proven in charset_rule.py's own tests and the project's
    README showcase -- consistent, traceable example throughout.
    """
    dbtr_nm = root.find(".//p:Dbtr/p:Nm", nsmap)
    dbtr_nm.text = "Helena Müller"

    label = GroundTruthLabel(
        rule_id=RuleId.CHARSET_VIOLATION,
        field_path="FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/Nm",
        injected_value="Helena Müller",
        expected_violation_type="character outside SWIFT character set X ('ü')",
    )
    return root, label


def _inject_address_freeform_only(root: etree._Element, nsmap: dict) -> tuple[etree._Element, GroundTruthLabel]:
    """Requires the baseline to have been built with
    include_ultimate_parties=True -- this injector targets UltmtDbtr,
    a hybrid-end-state role, and replaces its structured address
    (TwnNm/Ctry) with a free-format-only address (AdrLine), which is
    not permitted for hybrid-end-state roles per the Fedwire QRG.
    """
    ultmt_dbtr_pstl_adr = root.find(".//p:UltmtDbtr/p:PstlAdr", nsmap)
    if ultmt_dbtr_pstl_adr is None:
        raise ValueError(
            "ADDRESS_FREEFORM_ONLY injector requires a baseline built with "
            "include_ultimate_parties=True -- UltmtDbtr not found."
        )

    for child_tag in ("TwnNm", "Ctry"):
        child = ultmt_dbtr_pstl_adr.find(f"p:{child_tag}", nsmap)
        if child is not None:
            ultmt_dbtr_pstl_adr.remove(child)

    adr_line = etree.SubElement(ultmt_dbtr_pstl_adr, "AdrLine")
    adr_line.text = "123 Main Street"

    label = GroundTruthLabel(
        rule_id=RuleId.ADDRESS_FREEFORM_ONLY,
        field_path="FIToFICstmrCdtTrf/CdtTrfTxInf/UltmtDbtr/PstlAdr",
        injected_value="AdrLine present, TwnNm/Ctry removed",
        expected_violation_type="free-format-only address on a hybrid end-state role (UltmtDbtr)",
    )
    return root, label


def _inject_address_missing_town_country(root: etree._Element, nsmap: dict) -> tuple[etree._Element, GroundTruthLabel]:
    """Targets Dbtr, an interim-state role. Removes Ctry while leaving
    TwnNm, so the address is "structured" but incomplete -- interim-
    state rules require both TwnNm and Ctry as the minimum for a
    structured address.
    """
    dbtr_pstl_adr = root.find(".//p:Dbtr/p:PstlAdr", nsmap)
    ctry = dbtr_pstl_adr.find("p:Ctry", nsmap)
    dbtr_pstl_adr.remove(ctry)

    label = GroundTruthLabel(
        rule_id=RuleId.ADDRESS_MISSING_TOWN_COUNTRY,
        field_path="FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/PstlAdr",
        injected_value="(Ctry element removed)",
        expected_violation_type="structured address missing Country (Dbtr, interim-state role)",
    )
    return root, label


def _inject_address_too_many_lines(root: etree._Element, nsmap: dict) -> tuple[etree._Element, GroundTruthLabel]:
    """Requires include_ultimate_parties=True. Adds extra AdrLine
    entries to UltmtDbtr's address so the count exceeds the hybrid
    end-state limit (2), while staying within the schema's own
    maxOccurs=7 -- this is deliberately the schema-valid-but-
    guideline-invalid case verified in address_rule.py's own tests.
    """
    ultmt_dbtr_pstl_adr = root.find(".//p:UltmtDbtr/p:PstlAdr", nsmap)
    if ultmt_dbtr_pstl_adr is None:
        raise ValueError(
            "ADDRESS_TOO_MANY_LINES injector requires a baseline built with "
            "include_ultimate_parties=True -- UltmtDbtr not found."
        )

    line_count = 5  # > 2 (hybrid limit), <= 7 (schema max) -- same value used in address_rule.py tests
    for i in range(line_count):
        adr_line = etree.SubElement(ultmt_dbtr_pstl_adr, "AdrLine")
        adr_line.text = f"Line {i + 1}"

    label = GroundTruthLabel(
        rule_id=RuleId.ADDRESS_TOO_MANY_LINES,
        field_path="FIToFICstmrCdtTrf/CdtTrfTxInf/UltmtDbtr/PstlAdr",
        injected_value=f"{line_count} AdrLine entries added",
        expected_violation_type=(
            f"{line_count} free-format address lines on a hybrid end-state "
            "role (UltmtDbtr), exceeding the 2-line limit while remaining "
            "within the schema's own maxOccurs=7"
        ),
    )
    return root, label


def _inject_truncation_suspected(root: etree._Element, nsmap: dict) -> tuple[etree._Element, GroundTruthLabel]:
    """Sets Dbtr/Nm to exactly 35 characters -- Nm allows up to 140,
    so landing exactly on the old MT line-length boundary is the
    suspicious case verified in truncation_rule.py's own tests.
    """
    dbtr_nm = root.find(".//p:Dbtr/p:Nm", nsmap)
    suspicious_value = "A" * 35
    dbtr_nm.text = suspicious_value

    label = GroundTruthLabel(
        rule_id=RuleId.TRUNCATION_SUSPECTED,
        field_path="FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/Nm",
        injected_value=suspicious_value,
        expected_violation_type="name truncated to exactly 35 characters (legacy MT line-length boundary), in a field that allows up to 140",
    )
    return root, label


def _inject_mandatory_field_gap(root: etree._Element, nsmap: dict) -> tuple[etree._Element, GroundTruthLabel]:
    """Removes UETR from PmtId. Schema permits this (minOccurs=0);
    Fedwire's own FAQ states it's mandatory in practice -- the same
    case verified in mandatory_gap_rule.py's own tests.
    """
    uetr = root.find(".//p:PmtId/p:UETR", nsmap)
    parent = uetr.getparent()
    parent.remove(uetr)

    label = GroundTruthLabel(
        rule_id=RuleId.MANDATORY_FIELD_GAP,
        field_path="FIToFICstmrCdtTrf/CdtTrfTxInf/PmtId/UETR",
        injected_value="(element removed entirely)",
        expected_violation_type="UETR missing -- schema-optional but Fedwire-mandatory",
    )
    return root, label


_INJECTORS = {
    RuleId.XSD_STRUCTURAL: _inject_xsd_structural,
    RuleId.CHARSET_VIOLATION: _inject_charset_violation,
    RuleId.ADDRESS_FREEFORM_ONLY: _inject_address_freeform_only,
    RuleId.ADDRESS_MISSING_TOWN_COUNTRY: _inject_address_missing_town_country,
    RuleId.ADDRESS_TOO_MANY_LINES: _inject_address_too_many_lines,
    RuleId.TRUNCATION_SUSPECTED: _inject_truncation_suspected,
    RuleId.MANDATORY_FIELD_GAP: _inject_mandatory_field_gap,
}


def inject_error(baseline_xml: str, rule_id: RuleId) -> tuple[str, GroundTruthLabel]:
    """Takes valid baseline XML, returns (corrupted_xml, ground_truth_label).

    Operates by parsing the baseline into an lxml tree and surgically
    modifying the target element via XPath, rather than string
    replacement -- string matching against generated content (random
    names, random amounts) is fragile across different seeds; tree
    manipulation finds the target by structural path regardless of
    what random data happens to be there.

    ADDRESS_FREEFORM_ONLY and ADDRESS_TOO_MANY_LINES require the
    baseline to have been built with include_ultimate_parties=True
    (they target UltmtDbtr) -- raises ValueError with a clear message
    if that role isn't present, rather than silently doing nothing.
    """
    if rule_id not in _INJECTORS:
        raise NotImplementedError(
            f"No injector implemented for {rule_id}. "
            "Add a case to _INJECTORS, sourced from docs/SOURCES.md."
        )

    root, nsmap = _parse(baseline_xml)
    modified_root, label = _INJECTORS[rule_id](root, nsmap)
    return _serialize(modified_root), label

