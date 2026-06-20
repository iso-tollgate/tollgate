"""Renders a list of (Violation, explanation) pairs into report.md.

Errors before warnings, since a schema-level failure is generally
more urgent than a heuristic signal. Each finding shows the
deterministic message and the AI explanation (if any) as visually
distinct blocks, so a reader can tell fact from narration at a
glance -- per the project's deterministic-check/AI-narration split.

DATA HANDLING NOTE (2026-06-20): this report includes
Violation.raw_value when present (e.g. the actual name or address
fragment that triggered a charset or truncation finding). This is
intentional and fine -- this report stays entirely local, written to
the user's own filesystem for the user who ran the check on their own
data. The restriction that matters is specifically about NOT sending
raw_value across the network to a third-party API -- see
explain/explainer.py and explain/prompts.py for that boundary. Don't
confuse the two: a local report showing a user their own data back is
not the same risk as an API call sending that data elsewhere.
"""

from datetime import datetime, timezone
from pathlib import Path

from tollgate.validation.models import Violation

SCOPE_DISCLAIMER = (
    "Tollgate is not a SWIFT-certified compliance tool and does not "
    "replace MyStandards testing. It covers pacs.008.001.08 only and "
    "checks a deliberately narrow, sourced set of common gotchas -- "
    "see docs/SOURCES.md for what each rule does and doesn't cover."
)


def render_report(violations_with_explanations: list[tuple[Violation, str]], output_path: Path) -> None:
    """Renders findings as markdown and writes to output_path."""
    errors = [(v, e) for v, e in violations_with_explanations if v.severity == "error"]
    warnings = [(v, e) for v, e in violations_with_explanations if v.severity == "warning"]

    lines: list[str] = []
    lines.append("# Tollgate Validation Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    if not violations_with_explanations:
        lines.append("No issues found across all five checks.")
    else:
        lines.append(f"**{len(errors)} error(s), {len(warnings)} warning(s)** found.")
        lines.append("")

        if errors:
            lines.append("## Errors")
            lines.append("")
            for v, explanation in errors:
                lines.extend(_render_finding(v, explanation))

        if warnings:
            lines.append("## Warnings")
            lines.append("")
            for v, explanation in warnings:
                lines.extend(_render_finding(v, explanation))

    lines.append("---")
    lines.append("")
    lines.append(SCOPE_DISCLAIMER)
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def _render_finding(violation: Violation, explanation: str) -> list[str]:
    lines = [
        f"### `{violation.rule_id.value}` -- {violation.field_path}",
        "",
        f"**What was checked:** {violation.message}",
        "",
    ]
    if violation.raw_value:
        lines.append(f"**Offending value:** `{violation.raw_value}`")
        lines.append("")
    if explanation:
        lines.append(f"**Why it matters:** {explanation}")
        lines.append("")
    if violation.source_ref:
        lines.append(f"_Source: docs/SOURCES.md#{violation.source_ref}_")
        lines.append("")
    return lines
