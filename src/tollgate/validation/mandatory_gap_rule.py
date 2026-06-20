"""Network-mandatory fields that the XSD itself leaves optional.

CORRECTION before implementation (2026-06-20): the original framing of
this rule (below, preserved for the record) cited specific legacy FAIM
tag numbers ({6100}, {6200}, etc.) as having "no equivalent" in MX,
sourced from a Fedwire FAIM-comparison table referenced in research
notes but never actually fetched or verified directly. Checking the
real, vendored XSD against pacs.008.001.08's full mandatory-field list
found no clean match for that framing -- none of CreditTransferTransaction39's
mandatory fields (PmtId, IntrBkSttlmAmt, ChrgBr, Dbtr, DbtrAgt, CdtrAgt,
Cdtr) are unusual or legacy-gap-shaped; they're the obvious basics any
payment message needs. Building a rule on an unverified secondary
citation risked exactly the kind of unsourced claim this project is
not supposed to make.

THE ACTUAL, VERIFIED GOTCHA (replaces the original framing): UETR
(Unique End-to-End Transaction Reference) has minOccurs="0" in the
real schema -- genuinely optional at the XSD level. But the Federal
Reserve's own ISO 20022 FAQ states UETR is a mandatory data element
for Fedwire-bound pacs.008/pacs.009/pacs.004 messages, and Fedwire
checks it for proper format (docs/SOURCES.md#uetr-fedwire-mandatory).
A message can omit UETR entirely, validate clean against the XSD, and
still get rejected by Fedwire specifically -- the same "schema allows
it, the real network doesn't" shape as charset_rule.py and
address_rule.py, just via a missing-mandatory-field mechanism instead
of a content-restriction mechanism.

ORIGINAL (UNVERIFIED) FRAMING, preserved for the record rather than
silently deleted: some fields are mandatory in pacs.008 but the legacy
FAIM format had no equivalent concept at all -- a genuine data gap,
not a truncation or mapping problem. If this claim is verified against
the actual Fedwire FAIM-comparison table in a future session, it can
be added back as a second, properly-sourced check in this module --
but it should not ship as a citation we never actually confirmed.

NOT YET IMPLEMENTED (for the verified UETR check). Planned approach:
  - Check whether PmtId/UETR is present in the message.
  - If absent: this is NOT an XSD violation (the schema permits it),
    so xsd_validator.py will not catch it. Flag it here as a separate,
    network-specific mandatory-field gap.
  - Be explicit in the explanation that this is a Fedwire-specific
    requirement layered on top of the schema, not a universal ISO
    20022 rule -- other networks may not require UETR the same way,
    even though SWIFT's broader UETR mandate for cross-border payments
    suggests it's increasingly universal in practice.
"""

from pathlib import Path

from lxml import etree

from tollgate.validation.models import RuleId, Violation


def _local_path(element: etree._Element, doc_root: etree._Element) -> str:
    """Same readable-path helper used in the other three rule modules."""
    parts = []
    node = element
    while node is not None and node != doc_root:
        parts.append(etree.QName(node.tag).localname)
        node = node.getparent()
    return "/".join(reversed(parts))


def check_mandatory_gaps(xml_input: str | Path) -> list[Violation]:
    """Checks for fields the XSD permits to be absent but that real
    networks (currently: Fedwire, for UETR) require in practice.
    Assumes input already passed XSD validation.
    """
    if isinstance(xml_input, Path):
        root = etree.parse(str(xml_input)).getroot()
    else:
        root = etree.fromstring(xml_input.encode("utf-8"))

    nsmap = {"p": root.nsmap.get(None)} if root.nsmap.get(None) else {}
    violations: list[Violation] = []

    if nsmap:
        tx_elements = root.findall(".//p:CdtTrfTxInf", nsmap)
    else:
        tx_elements = root.findall(".//CdtTrfTxInf")

    for tx in tx_elements:
        if nsmap:
            pmt_id = tx.find("p:PmtId", nsmap)
        else:
            pmt_id = tx.find("PmtId")

        if pmt_id is None:
            continue  # missing PmtId entirely is an XSD-level concern, not ours

        if nsmap:
            uetr = pmt_id.find("p:UETR", nsmap)
        else:
            uetr = pmt_id.find("UETR")

        if uetr is None:
            path = _local_path(pmt_id, root)
            violations.append(
                Violation(
                    rule_id=RuleId.MANDATORY_FIELD_GAP,
                    field_path=f"{path}/UETR",
                    message=(
                        "UETR is missing from PmtId. The ISO 20022 schema "
                        "permits this (UETR has minOccurs=0), so this will "
                        "NOT be caught by XSD validation. However, the "
                        "Federal Reserve's own Fedwire ISO 20022 FAQ states "
                        "UETR is a mandatory data element for Fedwire-bound "
                        "pacs.008 messages, and Fedwire checks it for proper "
                        "format. This is a Fedwire-specific requirement, not "
                        "a universal ISO 20022 rule -- confirm your target "
                        "network's actual requirement before treating this "
                        "as universally mandatory."
                    ),
                    severity="error",
                    source_ref="uetr-fedwire-mandatory",
                )
            )

    return violations
