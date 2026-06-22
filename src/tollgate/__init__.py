"""Tollgate: pre-submission safety gate for ISO 20022 payment messages.

v1 scope: pacs.008.001.08 (FI to FI Customer Credit Transfer) only.
See docs/SOURCES.md for the source behind every validation rule.

Library usage:
    from tollgate import check_message, check_file, check_directory

    result = check_message(xml_string)
    if result.has_errors:
        ...

    batch = check_directory("payments/")
    if batch.has_any_errors:
        print(batch.files_with_errors)

See tollgate.api for the full public API and its design rationale.
"""

from tollgate.api import BatchCheckResult, CheckResult, check_directory, check_file, check_message

__version__ = "0.1.1"

__all__ = [
    "check_message",
    "check_file",
    "check_directory",
    "CheckResult",
    "BatchCheckResult",
    "__version__",
]
