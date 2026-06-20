"""Legacy MT-to-MX truncation heuristic.

THE GOTCHA: SWIFT's own CBPR+ pilot testing used a named test category
called "truncation and warning" scenarios (docs/SOURCES.md#truncation-
pilot), confirming this is a recognized class of problem, not a
hypothetical. Legacy MT fields have hard line-length limits (commonly
35 characters); MX fields are typically longer (Max70Text, Max140Text).
Data converted from MT to MX, or MX-native data later squeezed back
through an MT-shaped integration, can be silently truncated.

THE HEURISTIC (not a hard rule, hence "suspected" not "violation"):
a field value landing at EXACTLY a known legacy boundary (35 or 70
chars) is a meaningfully stronger truncation signal than a field that's
merely under its XSD max length — coincidentally hitting an old MT line
limit exactly is unlikely. This is exactly the "explain why, not just
that" case: XSD validation alone would not flag this at all, since a
35-char value is well within Max70Text's limit and schema-valid.

NOT YET IMPLEMENTED. Planned approach:
  - For text fields with Max*Text constraints, check actual value
    length against the known legacy boundary set {35, 70}.
  - Flag as RuleId.TRUNCATION_SUSPECTED with severity="warning" (this
    is a heuristic, not a certain violation — be honest about that
    distinction in both the code and any user-facing explanation).

FALSE-POSITIVE TRAP FOUND BEFORE IMPLEMENTING (2026-06-20): the plan
above, taken literally, would flag ANY field at exactly 35 or 70 chars
-- but several real fields genuinely have a schema max of 35
(EndToEndId, TwnNm) or 70 (AdrLine). A value using the FULL legitimate
length of a Max35Text field is normal usage, not a truncation signal.
The heuristic only makes sense for fields whose ACTUAL schema max is
LARGER than the boundary being checked -- e.g. Nm (Max140Text) landing
at exactly 35 chars is suspicious (an unrelated, larger field
mysteriously stopping at an old MT line limit); EndToEndId (Max35Text)
landing at exactly 35 chars is just someone using the field's full
allowed length.

Fix: maintain a per-field actual-max lookup (verified against the
vendored XSD below) and only flag when actual_length == boundary AND
field_max > boundary. Don't flag fields whose own max equals the
boundary being checked.

Verified field types relevant to this rule, from the actual XSD
(2026-06-20):
  Nm          -> Max140Text  (max 140) -- flaggable at 35 or 70
  EndToEndId  -> Max35Text   (max 35)  -- NOT flaggable at 35 (own max)
  TwnNm       -> Max35Text   (max 35)  -- NOT flaggable at 35 (own max)
  AdrLine     -> Max70Text   (max 70)  -- flaggable at 35, NOT at 70
  Ustrd       -> Max140Text  (max 140) -- flaggable at 35 or 70
"""

from pathlib import Path

from lxml import etree

from tollgate.validation.models import RuleId, Violation

LEGACY_MT_LINE_BOUNDARIES = (35, 70)

# field_tag -> actual schema max length, for the fields this rule
# checks. Sourced directly from the vendored XSD, not assumed -- see
# docstring above for the verification. Only include fields here once
# their actual max has been checked against the schema; don't guess.
FIELD_ACTUAL_MAX_LENGTH = {
    "Nm": 140,
    "EndToEndId": 35,
    "TwnNm": 35,
    "AdrLine": 70,
    "Ustrd": 140,
}


def _local_path(element: etree._Element, doc_root: etree._Element) -> str:
    """Same readable-path helper used in charset_rule.py and
    address_rule.py. See address_rule.py's note on why this is
    duplicated rather than shared -- worth promoting to a common
    utils module once a fourth rule needs it, not before.
    """
    parts = []
    node = element
    while node is not None and node != doc_root:
        parts.append(etree.QName(node.tag).localname)
        node = node.getparent()
    return "/".join(reversed(parts))


def check_truncation_signals(xml_input: str | Path) -> list[Violation]:
    """Flags fields whose value length lands at EXACTLY a known legacy
    MT line-length boundary (35 or 70), but only when that boundary is
    SMALLER than the field's own actual schema maximum -- otherwise a
    value at the field's real full length would be falsely flagged as
    suspicious. severity="warning", not "error": this is a heuristic
    signal, not a certain violation, and the explainer must say so
    plainly rather than presenting it as a definite failure.
    """
    if isinstance(xml_input, Path):
        root = etree.parse(str(xml_input)).getroot()
    else:
        root = etree.fromstring(xml_input.encode("utf-8"))

    violations: list[Violation] = []
    for element in root.iter():
        tag = etree.QName(element.tag).localname
        if tag not in FIELD_ACTUAL_MAX_LENGTH:
            continue
        if element.text is None:
            continue

        text = element.text
        actual_max = FIELD_ACTUAL_MAX_LENGTH[tag]

        for boundary in LEGACY_MT_LINE_BOUNDARIES:
            if boundary >= actual_max:
                continue  # boundary isn't smaller than the field's own max -- not suspicious
            if len(text) == boundary:
                path = _local_path(element, root)
                violations.append(
                    Violation(
                        rule_id=RuleId.TRUNCATION_SUSPECTED,
                        field_path=path,
                        message=(
                            f"{tag} is exactly {boundary} characters long, "
                            f"matching a legacy MT line-length limit, even "
                            f"though this field allows up to {actual_max}. "
                            "This is a heuristic signal, not a certain "
                            "failure -- it may simply be coincidence, but "
                            "landing exactly on an old MT boundary in a "
                            "field with a larger modern limit is a common "
                            "sign of silent truncation during MT-to-MX "
                            "conversion."
                        ),
                        severity="warning",
                        raw_value=text,
                        source_ref="truncation-pilot",
                        extra={"boundary": boundary, "field_actual_max": actual_max},
                    )
                )
                break  # one violation per field is enough; don't double-flag same value at multiple boundaries
    return violations
