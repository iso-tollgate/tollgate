"""Deterministic XSD structural validation.

TARGET SCHEMA: pacs.008.001.08 (FIToFICustomerCreditTransferV08)
Confirmed download (verified working 2026-06-20):
  https://www.iso20022.org/message/14231/download
This version was superseded in the live catalogue (current is .14)
and now lives in the ISO 20022 Messages Archive, under "Payments
Clearing and Settlement V09" (archived 01 Feb 2019). Fedwire and
CBPR+ guidance both reference .08 as of this research even though
it's no longer the catalogue's newest — pin to .08 unless you've
confirmed your target network has moved on. See docs/SOURCES.md#xsd-
source for both the current-catalogue and archive URLs.

Do not depend on a third-party GitHub mirror staying available or
unmodified — pull from the URL above directly.

VERIFIED 2026-06-20: a generator-built baseline message (see
generator/synthetic_fixtures.py) validates clean against this exact
vendored XSD with zero errors, and a deliberately broken variant
(mandatory ChrgBr removed) is correctly caught with a specific,
actionable error and XML path. The approach below is proven, not
theoretical.
"""

from pathlib import Path

import xmlschema

from tollgate.validation.models import RuleId, Violation


def validate_xsd(xml_input: str | Path, schema_path: str | Path) -> list[Violation]:
    """Validates xml_input (a path or raw XML string) against the XSD
    at schema_path. Collects ALL errors in one pass via iter_errors(),
    not just the first -- a report with "found 1 error, fix it and
    rerun" is a worse experience than "here are all 4 things wrong."

    This stage is the foundation every other rule module assumes ran
    first and passed (or at least didn't find a structural problem in
    the specific area that rule cares about) -- a malformed document
    should be caught here, not cause a confusing downstream failure in
    charset_rule or address_rule trying to parse something invalid.

    BUG FOUND AND FIXED during a deliberate review pass (2026-06-20):
    the docstring above already claimed malformed documents would be
    "caught here," but the original implementation never actually
    handled that case -- xmlschema.iter_errors() raises
    XMLResourceParseError (and similar) for input that isn't valid XML
    at all, rather than returning it as a normal validation error. A
    user pointing the CLI at a non-XML file (or any file with a
    well-formedness problem, not just a schema-conformance problem)
    got a raw Python stack trace instead of a clean message. This is
    exactly the gap between an aspirational docstring and verified
    behavior -- caught only by deliberately testing with garbage input
    rather than trusting the comment.

    SECOND BUG FOUND in the same review pass: an empty string/file
    input produces b"" once encoded, and xmlschema's resource loader
    apparently treats empty bytes as "no source provided" rather than
    "empty document" -- it falls back to resolving the current working
    directory as a file:// URL, raising a confusing "Is a directory"
    OSError that tells the user nothing about their actual problem
    (an empty file). Checked explicitly for and reported with a clear
    message before reaching xmlschema at all.
    """
    schema = xmlschema.XMLSchema(str(schema_path))

    is_empty = (
        (isinstance(xml_input, Path) and xml_input.stat().st_size == 0)
        or (isinstance(xml_input, str) and xml_input.strip() == "")
    )
    if is_empty:
        return [
            Violation(
                rule_id=RuleId.XSD_STRUCTURAL,
                field_path="(document root)",
                message=(
                    "This file is empty. It contains no XML content to "
                    "validate -- check that the file was generated or "
                    "downloaded correctly."
                ),
                severity="error",
                source_ref="iso20022-xsd-pacs008-001-08",
            )
        ]

    if isinstance(xml_input, Path):
        source = str(xml_input)
    else:
        # Raw XML string -- xmlschema's iter_errors accepts bytes or
        # a file-like source; encode explicitly rather than relying on
        # implicit encoding detection.
        source = xml_input.encode("utf-8")

    violations: list[Violation] = []
    try:
        for error in schema.iter_errors(source):
            violations.append(
                Violation(
                    rule_id=RuleId.XSD_STRUCTURAL,
                    field_path=error.path or "(unknown path)",
                    message=error.reason or str(error),
                    severity="error",
                    source_ref="iso20022-xsd-pacs008-001-08",
                )
            )
    except Exception as e:
        # Catches well-formedness failures (not valid XML at all) and
        # any other parse-level exception xmlschema/lxml might raise
        # before schema-conformance checking even begins. Reported as
        # a single Violation rather than letting a stack trace reach
        # the CLI.
        #
        # BUG FOUND AND FIXED (2026-06-20), while testing the exact
        # README quickstart example a new user would run: a plain
        # string with no '<' character (e.g. "not even xml") makes
        # xmlschema's resource loader treat it as a potential file
        # PATH rather than literal content, raising
        # XMLResourceOSError with a confusing "can't access to
        # resource...No such file or directory" message that even
        # echoed back a local filesystem path. The underlying
        # exception type/text is no longer surfaced to the user --
        # we already know definitively this branch means "not parseable
        # as XML," so a clean, fixed message is both more honest about
        # what we actually know and avoids leaking confusing internal
        # detail (or, in this case, local path fragments) into a
        # validation message.
        violations.append(
            Violation(
                rule_id=RuleId.XSD_STRUCTURAL,
                field_path="(document root)",
                message=(
                    "This could not be parsed as XML at all. It may not be "
                    "XML, may be empty, or may be corrupted/truncated."
                ),
                severity="error",
                source_ref="iso20022-xsd-pacs008-001-08",
            )
        )
    return violations

