"""Tollgate CLI.

    tollgate validate payment.xml --message-type pacs.008 --output report.md
    tollgate validate payment.xml --explain          # adds AI explanations (calls the Anthropic API)
    tollgate generate --count 5 --rule-id charset_violation

DESIGN NOTE on --explain: AI explanation is opt-in, not the default.
Deterministic checks (XSD, charset, address, truncation, mandatory-gap)
always run -- they're free, fast, and local. explain_violation() makes
a real, billed call to the Anthropic API per violation, and (as of
2026-06-20) has not been live-verified end-to-end -- see
tests/test_explainer.py. Defaulting to always calling it would mean
anyone running `tollgate validate` without an API key configured hits
an error immediately, even if they only wanted the deterministic
findings. With --explain and no key set, this fails clearly via the
same RuntimeError explain_violation() already raises.
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from tollgate.validation.address_rule import check_address_structure
from tollgate.validation.charset_rule import check_charset
from tollgate.validation.mandatory_gap_rule import check_mandatory_gaps
from tollgate.validation.models import Violation
from tollgate.validation.truncation_rule import check_truncation_signals
from tollgate.validation.xsd_validator import validate_xsd

app = typer.Typer(
    name="tollgate",
    help="Pre-submission safety gate for ISO 20022 payment messages.",
)
console = Console()

SCHEMA_PATH = Path(__file__).parent / "schemas" / "pacs.008.001.08.xsd"


def _run_all_checks(xml_path: Path) -> list[Violation]:
    """Runs all five deterministic rules in order. XSD runs first --
    if a message is too malformed to parse at all, the other four
    rules (which all assume well-formed XML) would raise confusing
    lxml parse errors rather than a clean validation result. Their own
    docstrings note this same assumption.
    """
    xml_str = xml_path.read_text(encoding="utf-8")

    violations: list[Violation] = []
    violations.extend(validate_xsd(xml_str, SCHEMA_PATH))

    # The remaining four rules all parse the document themselves via
    # lxml.etree.fromstring -- if the XML is malformed enough that XSD
    # validation already failed structurally, these may raise a parse
    # error rather than return cleanly. Catch that case explicitly so
    # the CLI degrades to "here's what XSD found" instead of crashing.
    try:
        violations.extend(check_charset(xml_str))
        violations.extend(check_address_structure(xml_str))
        violations.extend(check_truncation_signals(xml_str))
        violations.extend(check_mandatory_gaps(xml_str))
    except Exception as e:
        console.print(
            f"[yellow]Warning:[/yellow] could not run all checks -- the "
            f"document may be too malformed to parse beyond XSD validation. "
            f"({type(e).__name__}: {e})"
        )

    return violations


@app.command()
def validate(
    message_path: Path = typer.Argument(..., help="Path to the ISO 20022 XML message to check."),
    message_type: str = typer.Option(
        "pacs.008", "--message-type", help="Message type to validate against. v1 supports pacs.008 only."
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", help="Write a markdown report to this path instead of printing to console."
    ),
    explain: bool = typer.Option(
        False, "--explain", help="Add AI-generated plain-English explanations (calls the Anthropic API; requires ANTHROPIC_API_KEY)."
    ),
) -> None:
    """Run the full validation pipeline against a single message file."""
    if message_type != "pacs.008":
        console.print(
            f"[red]Unsupported message type '{message_type}'.[/red] "
            "v1 only supports pacs.008.001.08. See README for scope."
        )
        raise typer.Exit(code=1)

    if not message_path.exists():
        console.print(f"[red]File not found:[/red] {message_path}")
        raise typer.Exit(code=1)

    violations = _run_all_checks(message_path)

    explanations: dict[int, str] = {}
    if explain:
        from tollgate.explain.explainer import explain_violation

        for i, v in enumerate(violations):
            try:
                explanations[i] = explain_violation(v)
            except RuntimeError as e:
                console.print(f"[red]{e}[/red]")
                raise typer.Exit(code=1)

    if output:
        from tollgate.report.markdown_report import render_report

        pairs = [(v, explanations.get(i, "")) for i, v in enumerate(violations)]
        render_report(pairs, output)
        console.print(f"Report written to [bold]{output}[/bold] ({len(violations)} finding(s)).")
    else:
        _print_console_report(violations, explanations, message_path)

    if violations:
        raise typer.Exit(code=1)


def _print_console_report(
    violations: list[Violation], explanations: dict[int, str], message_path: Path
) -> None:
    if not violations:
        console.print(f"[green]✓[/green] {message_path} -- no issues found across all five checks.")
        return

    errors = [v for v in violations if v.severity == "error"]
    warnings = [v for v in violations if v.severity == "warning"]
    console.print(
        f"[red]{len(errors)} error(s)[/red], [yellow]{len(warnings)} warning(s)[/yellow] "
        f"found in {message_path}:\n"
    )

    for i, v in enumerate(violations):
        color = "red" if v.severity == "error" else "yellow"
        console.print(f"[{color}]{v.severity.upper()}[/{color}] {v.rule_id.value} -- {v.field_path}")
        console.print(f"  {v.message}")
        if i in explanations:
            console.print(f"  [dim]→ {explanations[i]}[/dim]")
        console.print()


@app.command()
def generate(
    count: int = typer.Option(10, "--count", help="Number of synthetic test fixtures to generate."),
    rule_id: Optional[str] = typer.Option(
        None, "--rule-id", help="Generate fixtures for a single RuleId only (e.g. charset_violation). Default: all rules."
    ),
    output_dir: Path = typer.Option(
        Path("tests/fixtures"), "--output-dir", help="Directory to write generated fixtures into."
    ),
) -> None:
    """Generate synthetic pacs.008 fixtures with labeled injected errors, for eval ground truth."""
    from tollgate.generator.synthetic_fixtures import (
        REQUIRES_ULTIMATE_PARTIES_RULE_IDS,
        build_valid_baseline,
        inject_error,
    )
    from tollgate.validation.models import RuleId

    if rule_id is not None:
        try:
            target_rule_ids = [RuleId(rule_id)]
        except ValueError:
            valid = ", ".join(r.value for r in RuleId)
            console.print(f"[red]Unknown rule_id '{rule_id}'.[/red] Valid values: {valid}")
            raise typer.Exit(code=1)
    else:
        target_rule_ids = list(RuleId)

    output_dir.mkdir(parents=True, exist_ok=True)
    written = 0

    for rid in target_rule_ids:
        needs_ultimate = rid in REQUIRES_ULTIMATE_PARTIES_RULE_IDS
        for i in range(count):
            baseline = build_valid_baseline(seed=i, include_ultimate_parties=needs_ultimate)
            corrupted_xml, label = inject_error(baseline, rid)
            file_path = output_dir / f"{rid.value}_{i}.xml"
            file_path.write_text(corrupted_xml, encoding="utf-8")
            written += 1

    console.print(f"[green]✓[/green] Wrote {written} fixture(s) to {output_dir}")


if __name__ == "__main__":
    app()
