"""SWIFT network character set restriction.

THE GOTCHA: ISO 20022 XML permits full UTF-8 Unicode at the schema level.
SWIFT's network layer separately restricts allowed characters to its
character set X for messages traveling over FIN/MX coexistence —
meaning a message can be 100% XSD-valid and still get rejected at the
network layer for a reason the schema has no way to express.

Character set X, per ECB/T2S documentation (docs/SOURCES.md#charset-x):
    a-z A-Z 0-9 / - ? : ( ) . , ' + and CR/LF

CAVEAT (be honest about this in any explanation text): the universality
of this restriction across all networks is not fully confirmed — some
market infrastructures have discussed extended character set proposals
(see UK Interoperability Working Group reference in research notes).
Confirm this is still the operative rule for your target network
(Fedwire vs CBPR+) before treating it as a hard universal rule rather
than a FIN/MX-coexistence-era default. Surface this caveat to the user
rather than asserting it unconditionally.

NOT YET IMPLEMENTED. Planned approach:
  - Extract text content from Nm, AdrLine, and remittance-info text
    fields (the field list should be derived from the XSD's Max*Text
    elements, not hardcoded, so it doesn't silently miss fields).
  - Regex-match against the allowlist above.
  - For each violation, return the specific offending character(s) and
    field path, not just "contains invalid characters" — the explainer
    needs the actual character to say something useful ("the 'ü' in
    Creditor Name will be rejected by SWIFT's character set X, even
    though it passed XML schema validation").
"""

import re
from pathlib import Path

from lxml import etree

from tollgate.validation.models import RuleId, Violation

# CORRECTED 2026-06-20: the original pattern below was missing a plain
# space character, which meant it flagged ordinary text like "Tomas
# Becker" as a violation -- caught by testing against real cases before
# trusting the docstring's claim. SWIFT's own character set X
# definition explicitly lists "Space" as a separate allowed character
# alongside the letters/digits/punctuation (see docs/SOURCES.md#charset-x
# and the Paiementor/SWIFT Standards MT sources cited there).
CHARSET_X_PATTERN = re.compile(r"^[a-zA-Z0-9/\-?:().,' +\r\n]*$")


def _local_path(element: etree._Element, doc_root: etree._Element) -> str:
    """Builds a readable, namespace-free path like
    'CdtTrfTxInf/Dbtr/Nm' instead of lxml's default XPath, which is
    unreadable with namespaces ('/*/*/*[2]/*/*[1]'). This is what
    Violation.field_path actually needs -- the explainer and eval
    harness reference these paths, so they have to be meaningful to a
    human, not just technically correct.
    """
    parts = []
    node = element
    while node is not None and node != doc_root:
        parts.append(etree.QName(node.tag).localname)
        node = node.getparent()
    return "/".join(reversed(parts))


def check_charset(xml_input: str | Path) -> list[Violation]:
    """Walks every text-bearing element in the parsed document and
    checks its content against SWIFT's character set X. Deliberately
    does NOT try to enumerate field names from the XSD's Max*Text type
    graph ahead of time (the original plan above) -- walking the
    actual document's text content is simpler, can't silently miss a
    field we didn't anticipate, and doesn't require understanding the
    full XSD type graph just to know where text might appear.

    Assumes the input already passed xsd_validator.validate_xsd() --
    this function does not re-validate structure, only character
    content of whatever text nodes exist.
    """
    if isinstance(xml_input, Path):
        root = etree.parse(str(xml_input)).getroot()
    else:
        root = etree.fromstring(xml_input.encode("utf-8"))

    violations: list[Violation] = []
    for element in root.iter():
        if element.text is None or not element.text.strip():
            continue

        text = element.text
        if CHARSET_X_PATTERN.match(text):
            continue

        offending_chars = sorted(
            {ch for ch in text if not CHARSET_X_PATTERN.match(ch)}
        )
        path = _local_path(element, root)

        violations.append(
            Violation(
                rule_id=RuleId.CHARSET_VIOLATION,
                field_path=path,
                message=(
                    f"Contains character(s) outside SWIFT's character set X: "
                    f"{', '.join(repr(c) for c in offending_chars)}. "
                    "This is schema-valid XML (ISO 20022 permits full Unicode) "
                    "but SWIFT's network layer restricts allowed characters "
                    "independently of the schema -- this will not be caught "
                    "by XSD validation alone."
                ),
                severity="error",
                raw_value=text,
                source_ref="charset-x",
                extra={"offending_chars": offending_chars},
            )
        )
    return violations
