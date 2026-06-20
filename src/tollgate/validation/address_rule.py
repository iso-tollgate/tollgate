"""Postal address structure rules — hybrid end-state enforcement.

THE DEADLINE THIS MATTERS FOR: November 2026, unstructured free-text
addresses stop being accepted across SWIFT cross-border payments and
several clearing networks including Fedwire, CHIPS, SEPA, CHAPS-UK,
TARGET2-Euro, and SAMOS (docs/SOURCES.md#address-deadline-2026).
This is the single highest-value check in v1 given the dated, narrow,
approaching deadline.

TWO DIFFERENT RULE SETS APPLY DEPENDING ON PARTY ROLE
(source: Fedwire ISO 20022 Quick Reference Guide, docs/SOURCES.md#fedwire-qrg):

Interim-state roles (Debtor, Creditor, Debtor Agent, Creditor Agent,
Intermediary Agent 1-3, Previous Instructing Agent 1-3, Charges
Information Agent):
  - Name required to use Postal Address at all.
  - EITHER structured address alone OR free-format AdrLine alone —
    never both.
  - If structured: minimum TwnNm + Ctry.
  - If free-format: up to 3 lines, 35 chars each.

Hybrid-end-state roles (Ultimate Debtor, Initiating Party, Ultimate
Creditor, Originator):
  - Name required.
  - Structured alone, OR structured + free-format combined.
    Free-format ALONE is not permitted for these roles.
  - TwnNm + Ctry always required, even when AdrLine is also used.
  - Free-format lines: up to 2 lines, 70 chars each (note: NOT 35 —
    this differs from the interim limit and is a likely source of
    truncation bugs in systems that hardcode the legacy 35-char MT
    line limit across all address fields uniformly).

NOT YET IMPLEMENTED. Planned approach:
  - Maintain the role->ruleset mapping as data (not scattered if/else),
    since it's the kind of table that needs to stay easy to audit
    against the source document.
  - For each role present in the message, determine interim vs
    hybrid-end-state bucket, check structured/free-form presence and
    TwnNm/Ctry presence accordingly.
  - Flag RuleId.ADDRESS_FREEFORM_ONLY when a hybrid-end-state role has
    AdrLine present but TwnNm or Ctry absent.

VERIFIED AGAINST THE ACTUAL VENDORED XSD (2026-06-20): PostalAddress24
defines AdrLine with maxOccurs="7", type Max70Text — the schema itself
permits up to 7 free-format lines of 70 characters each, which is MORE
permissive than the Fedwire hybrid-end-state limit of 2 lines. A
message with, say, 5 AdrLine entries is fully schema-valid XML and
still violates the usage guideline. This is concrete, schema-level
proof that this rule earns its place as a separate, non-XSD check —
XSD validation alone cannot catch this class of violation, because the
schema is deliberately more permissive than any single network's
usage guidelines layered on top of it. Codeable rule: also flag
AdrLine count > 2 for hybrid-end-state roles, not just the
presence/absence check above.

STRUCTURAL CORRECTION found before implementation (2026-06-20):
the original INTERIM_STATE_ROLES set below included "ChrgsInf" as if
it had a PstlAdr directly underneath it. Verified against the actual
schema: ChrgsInf (Charges7) is Amt + Agt, with NO PstlAdr of its own
-- the address, if present, lives at ChrgsInf/Agt/FinInstnId/PstlAdr,
three levels deep. Similarly, agent roles (DbtrAgt, CdtrAgt,
IntrmyAgt1-3, PrvsInstgAgt1-3) use
BranchAndFinancialInstitutionIdentification6, where PstlAdr lives at
ROLE/FinInstnId/PstlAdr -- one level deeper than party roles (Dbtr,
Cdtr, UltmtDbtr, InitgPty, UltmtCdtr), where PstlAdr sits directly
under the role tag. A naive "role_tag/PstlAdr" search would silently
miss every agent-role address. Fix: search for PstlAdr ANYWHERE
beneath the role element (.//PstlAdr) rather than assuming a fixed
depth per role -- verified this finds the address correctly regardless
of whether it's one level deep or two.
"""

from pathlib import Path

from lxml import etree

from tollgate.validation.models import RuleId, Violation

INTERIM_STATE_ROLES = {
    "Dbtr", "Cdtr", "DbtrAgt", "CdtrAgt",
    "IntrmyAgt1", "IntrmyAgt2", "IntrmyAgt3",
    "PrvsInstgAgt1", "PrvsInstgAgt2", "PrvsInstgAgt3",
    # ChrgsInf removed (2026-06-20) -- it has no PstlAdr of its own,
    # see correction note above. Its nested Agt would need separate
    # handling if charges-agent addresses are ever in scope; not in v1.
}

HYBRID_END_STATE_ROLES = {
    "UltmtDbtr", "InitgPty", "UltmtCdtr",
}

# Per the Fedwire QRG (docs/SOURCES.md#fedwire-qrg), hybrid end-state
# roles allow at most 2 free-format address lines; interim-state roles
# allow at most 3. The schema's own AdrLine maxOccurs=7 is permissive
# enough to violate either limit, which is the whole reason this check
# needs to exist independently of XSD validation.
HYBRID_END_STATE_MAX_ADRLINES = 2
INTERIM_STATE_MAX_ADRLINES = 3


def _local_path(element: etree._Element, doc_root: etree._Element) -> str:
    """Same readable-path helper used in charset_rule.py -- duplicated
    rather than imported to keep each rule module's test suite able to
    run in isolation without cross-module coupling for something this
    small. If a third rule module needs this, it's worth promoting to
    a shared utils module at that point, not before.
    """
    parts = []
    node = element
    while node is not None and node != doc_root:
        parts.append(etree.QName(node.tag).localname)
        node = node.getparent()
    return "/".join(reversed(parts))


def check_address_structure(xml_input: str | Path) -> list[Violation]:
    """Checks every present role from both INTERIM_STATE_ROLES and
    HYBRID_END_STATE_ROLES against the address-structure rule that
    applies to its bucket. Assumes input already passed XSD validation
    -- does not re-check structure, only the usage-guideline rules
    layered on top of what the schema allows.
    """
    if isinstance(xml_input, Path):
        root = etree.parse(str(xml_input)).getroot()
    else:
        root = etree.fromstring(xml_input.encode("utf-8"))

    nsmap = {"p": root.nsmap.get(None)} if root.nsmap.get(None) else {}
    violations: list[Violation] = []

    def find_role_elements(role_tag: str) -> list[etree._Element]:
        if nsmap:
            return root.findall(f".//p:{role_tag}", nsmap)
        return root.findall(f".//{role_tag}")

    def find_postal_address(role_element: etree._Element) -> etree._Element | None:
        if nsmap:
            return role_element.find(".//p:PstlAdr", nsmap)
        return role_element.find(".//PstlAdr")

    def get_child_text(parent: etree._Element, tag: str) -> str | None:
        if nsmap:
            child = parent.find(f"p:{tag}", nsmap)
        else:
            child = parent.find(tag)
        return child.text if child is not None else None

    def get_adrlines(parent: etree._Element) -> list[str]:
        if nsmap:
            lines = parent.findall("p:AdrLine", nsmap)
        else:
            lines = parent.findall("AdrLine")
        return [el.text or "" for el in lines]

    def check_role(role_tag: str, *, is_hybrid_end_state: bool) -> None:
        for role_el in find_role_elements(role_tag):
            pstl_adr = find_postal_address(role_el)
            if pstl_adr is None:
                continue  # no address at all is a separate (XSD-level) concern

            twn_nm = get_child_text(pstl_adr, "TwnNm")
            ctry = get_child_text(pstl_adr, "Ctry")
            adr_lines = get_adrlines(pstl_adr)
            path = _local_path(pstl_adr, root)

            if is_hybrid_end_state:
                if adr_lines and (not twn_nm or not ctry):
                    violations.append(
                        Violation(
                            rule_id=RuleId.ADDRESS_FREEFORM_ONLY,
                            field_path=path,
                            message=(
                                f"{role_tag} uses free-format address lines without "
                                "both Town Name and Country. Hybrid end-state rules "
                                "(effective for this role) require TwnNm and Ctry "
                                "to always be present, even when AdrLine is also "
                                "used -- free-format alone is not permitted for "
                                f"{role_tag}."
                            ),
                            severity="error",
                            source_ref="fedwire-qrg",
                        )
                    )
                if len(adr_lines) > HYBRID_END_STATE_MAX_ADRLINES:
                    violations.append(
                        Violation(
                            rule_id=RuleId.ADDRESS_TOO_MANY_LINES,
                            field_path=path,
                            message=(
                                f"{role_tag} has {len(adr_lines)} free-format address "
                                f"lines; the hybrid end-state limit for this role is "
                                f"{HYBRID_END_STATE_MAX_ADRLINES}. The schema itself "
                                "permits up to 7 lines, so this is schema-valid XML "
                                "that still violates the usage guideline."
                            ),
                            severity="error",
                            source_ref="fedwire-qrg",
                            extra={"line_count": len(adr_lines)},
                        )
                    )
            else:
                # Interim-state: structured XOR free-format, not both.
                has_structured = bool(twn_nm or ctry)
                has_freeform = bool(adr_lines)
                if has_structured and has_freeform:
                    violations.append(
                        Violation(
                            rule_id=RuleId.ADDRESS_FREEFORM_ONLY,
                            field_path=path,
                            message=(
                                f"{role_tag} combines structured address fields "
                                "(TwnNm/Ctry) with free-format AdrLine. Interim-state "
                                "rules for this role require one or the other, not "
                                "both."
                            ),
                            severity="error",
                            source_ref="fedwire-qrg",
                        )
                    )
                if has_structured and not (twn_nm and ctry):
                    violations.append(
                        Violation(
                            rule_id=RuleId.ADDRESS_MISSING_TOWN_COUNTRY,
                            field_path=path,
                            message=(
                                f"{role_tag} uses a structured address but is "
                                "missing Town Name or Country -- interim-state "
                                "rules require both as a minimum when using the "
                                "structured form."
                            ),
                            severity="error",
                            source_ref="fedwire-qrg",
                        )
                    )
                if len(adr_lines) > INTERIM_STATE_MAX_ADRLINES:
                    violations.append(
                        Violation(
                            rule_id=RuleId.ADDRESS_TOO_MANY_LINES,
                            field_path=path,
                            message=(
                                f"{role_tag} has {len(adr_lines)} free-format address "
                                f"lines; the interim-state limit for this role is "
                                f"{INTERIM_STATE_MAX_ADRLINES}."
                            ),
                            severity="error",
                            source_ref="fedwire-qrg",
                            extra={"line_count": len(adr_lines)},
                        )
                    )

    for role_tag in INTERIM_STATE_ROLES:
        check_role(role_tag, is_hybrid_end_state=False)
    for role_tag in HYBRID_END_STATE_ROLES:
        check_role(role_tag, is_hybrid_end_state=True)

    return violations
