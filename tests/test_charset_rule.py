"""Tests for charset_rule.py.

These tests specifically guard against the regex bug found during
development: the original pattern was missing a plain space character,
which meant it falsely flagged ordinary text like "Tomas Becker" as a
violation. test_no_false_positive_on_plain_text exists specifically to
catch a regression back to that bug.
"""

from tollgate.generator.synthetic_fixtures import build_valid_baseline
from tollgate.validation.charset_rule import check_charset
from tollgate.validation.models import RuleId


def test_clean_baseline_has_zero_violations():
    xml_str = build_valid_baseline(seed=42)
    violations = check_charset(xml_str)
    assert violations == []


def test_umlaut_in_name_is_caught():
    xml_str = build_valid_baseline(seed=42)
    broken = xml_str.replace("Helena Marsh", "Helena Müller")
    violations = check_charset(broken)

    assert len(violations) >= 1
    assert all(v.rule_id == RuleId.CHARSET_VIOLATION for v in violations)
    assert any("ü" in v.extra["offending_chars"] for v in violations)


def test_passes_xsd_but_fails_charset():
    """The core showcase claim from the project brief, proven as a
    test rather than just asserted in prose: a message can be 100%
    XSD-valid and still violate SWIFT's network-layer character set
    restriction, because the restriction lives outside the schema.
    """
    from pathlib import Path

    from tollgate.validation.xsd_validator import validate_xsd

    schema_path = (
        Path(__file__).parent.parent
        / "src"
        / "tollgate"
        / "schemas"
        / "pacs.008.001.08.xsd"
    )

    xml_str = build_valid_baseline(seed=42)
    broken = xml_str.replace("Helena Marsh", "Helena Müller")

    xsd_violations = validate_xsd(broken, schema_path)
    charset_violations = check_charset(broken)

    assert xsd_violations == [], "Expected the umlaut variant to still be XSD-valid"
    assert len(charset_violations) >= 1, "Expected the umlaut to be caught by charset_rule"


def test_no_false_positive_on_apostrophe():
    """Apostrophes are part of character set X (e.g. O'Sullivan) --
    must not be flagged. This is a real risk for any character-set
    check; a false positive here erodes trust in the whole tool.
    """
    xml_str = build_valid_baseline(seed=1)
    with_apostrophe = xml_str.replace("Tomas Becker", "Liam O'Sullivan")
    violations = check_charset(with_apostrophe)
    assert violations == []


def test_no_false_positive_on_plain_text():
    """Regression guard for the space-character bug found during
    development -- the original pattern flagged plain text with
    ordinary spaces as a violation.
    """
    xml_str = build_valid_baseline(seed=42)
    violations = check_charset(xml_str)
    assert violations == [], (
        "Plain generated text should never trigger a charset violation. "
        "If this fails, check whether the space character was dropped "
        "from CHARSET_X_PATTERN again."
    )


def test_field_path_is_human_readable():
    """field_path must be a clean, namespace-free path like
    'CdtTrfTxInf/Dbtr/Nm', not lxml's default XPath output
    ('/*/*/*[2]/*/*[1]'), since the explainer and eval harness
    reference this path and need it to mean something to a human.
    """
    xml_str = build_valid_baseline(seed=42)
    broken = xml_str.replace("Helena Marsh", "Helena Müller")
    violations = check_charset(broken)

    assert len(violations) >= 1
    for v in violations:
        assert "*" not in v.field_path
        assert "[" not in v.field_path
        assert "/" in v.field_path or v.field_path  # path-shaped or single tag


def test_offending_chars_are_specific_not_generic():
    """The explainer needs the actual offending character, not a
    generic 'contains invalid characters' message -- this is explicit
    in the original docstring's design rationale.
    """
    xml_str = build_valid_baseline(seed=42)
    broken = xml_str.replace("Helena Marsh", "Helena Müller")
    violations = check_charset(broken)

    assert len(violations) >= 1
    v = violations[0]
    assert v.extra["offending_chars"] == ["ü"]
    assert "ü" in v.message
