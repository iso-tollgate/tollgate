"""Tollgate CLI.

    tollgate validate payment.xml --message-type pacs.008 --output report.md
    tollgate validate payment.xml --explain          # adds AI explanations (calls the Anthropic API)
    tollgate validate payment.xml --json             # machine-readable output for CI/scripts
    tollgate validate-dir payments/ --recursive       # check every .xml file in a folder
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

REFACTORED (2026-06-20) to call tollgate.api instead of containing its
own copy of the check-assembly logic. Previously this file had its own
_run_all_checks() that duplicated exactly what a library caller would
need -- now that tollgate.api.check_file()/check_message() exist as
the real public API, the CLI is a thin presentation layer on top of
them: one source of truth for "how does the pipeline run," the CLI
just decides how to print/format the result.

validate-dir is a SEPARATE command from validate, not validate
detecting "oh, this path is a directory" automatically -- explicit
command names avoid surprising behavior changes based on what kind of
path happens to be passed.
"""

import json as json_module
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from tollgate.api import BatchCheckResult, CheckResult, check_directory, check_file
from tollgate.validation.models import Violation

app = typer.Typer(
    name="tollgate",
    help="Pre-submission safety gate for ISO 20022 payment messages.",
)
console = Console()


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
    as_json: bool = typer.Option(
        False, "--json", help="Print machine-readable JSON instead of a human-readable console report. For CI/scripting use; incompatible with --output."
    ),
) -> None:
    """Run the full validation pipeline against a single message file."""
    if not message_path.exists():
        console.print(f"[red]File not found:[/red] {message_path}")
        raise typer.Exit(code=1)

    if message_path.is_dir():
        console.print(f"[red]This is a directory, not a file:[/red] {message_path}")
        raise typer.Exit(code=1)

    if as_json and output:
        console.print("[red]--json and --output cannot be used together.[/red] --json prints to stdout.")
        raise typer.Exit(code=1)

    try:
        result = check_file(message_path, message_type=message_type, explain=explain)
    except ValueError as e:
        # check_message()/check_file() raise ValueError for an
        # unsupported message_type, rather than the CLI handling this
        # itself -- one validation point, in the library, not
        # duplicated logic in every caller (CLI included).
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)
    except UnicodeDecodeError:
        console.print(
            f"[red]Could not read {message_path} as UTF-8 text.[/red] "
            "This usually means the file is binary, not XML -- check that "
            "you're pointing at the right file."
        )
        raise typer.Exit(code=1)
    except PermissionError:
        console.print(f"[red]Permission denied reading:[/red] {message_path}")
        raise typer.Exit(code=1)
    except RuntimeError as e:
        # explain_violation() raises this for a missing API key when
        # explain=True -- surfaced here rather than inside check_file
        # so the library function itself doesn't need to know about
        # console printing.
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    if as_json:
        print(json_module.dumps(result.to_dict(), indent=2))
    elif output:
        from tollgate.report.markdown_report import render_report

        pairs = [(v, result.explanations.get(i, "")) for i, v in enumerate(result.violations)]
        render_report(pairs, output)
        console.print(f"Report written to [bold]{output}[/bold] ({len(result.violations)} finding(s)).")
    else:
        _print_console_report(result, message_path)

    if result.has_errors:
        raise typer.Exit(code=1)


def _print_console_report(result: CheckResult, message_path: Path) -> None:
    if result.is_clean:
        console.print(f"[green]✓[/green] {message_path} -- no issues found across all five checks.")
        return

    errors = [v for v in result.violations if v.severity == "error"]
    warnings = [v for v in result.violations if v.severity == "warning"]
    console.print(
        f"[red]{len(errors)} error(s)[/red], [yellow]{len(warnings)} warning(s)[/yellow] "
        f"found in {message_path}:\n"
    )

    for i, v in enumerate(result.violations):
        color = "red" if v.severity == "error" else "yellow"
        console.print(f"[{color}]{v.severity.upper()}[/{color}] {v.rule_id.value} -- {v.field_path}")
        console.print(f"  {v.message}")
        if i in result.explanations:
            console.print(f"  [dim]\u2192 {result.explanations[i]}[/dim]")
        console.print()


@app.command(name="validate-dir")
def validate_dir(
    directory: Path = typer.Argument(..., help="Directory containing ISO 20022 XML files to check."),
    pattern: str = typer.Option("*.xml", "--pattern", help="Glob pattern for files to check within the directory."),
    recursive: bool = typer.Option(
        False, "--recursive", help="Also check files in subdirectories. Off by default to avoid accidentally scanning far more than intended."
    ),
    message_type: str = typer.Option("pacs.008", "--message-type", help="Message type to validate against. v1 supports pacs.008 only."),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON instead of a human-readable console summary."),
) -> None:
    """Check every matching file in a directory. One bad/unreadable
    file does not prevent the rest from being checked -- each file's
    outcome (clean, has violations, or unreadable) is reported
    independently.
    """
    if not directory.exists():
        console.print(f"[red]Directory not found:[/red] {directory}")
        raise typer.Exit(code=1)

    if not directory.is_dir():
        console.print(f"[red]Not a directory:[/red] {directory}")
        raise typer.Exit(code=1)

    try:
        batch = check_directory(directory, pattern=pattern, recursive=recursive, message_type=message_type)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    if batch.total_files == 0:
        console.print(f"[yellow]No files matching '{pattern}' found in {directory}.[/yellow]")
        raise typer.Exit(code=1)

    if as_json:
        print(json_module.dumps(batch.to_dict(), indent=2))
    else:
        _print_batch_console_report(batch)

    if batch.has_any_errors:
        raise typer.Exit(code=1)


def _print_batch_console_report(batch: BatchCheckResult) -> None:
    console.print(
        f"Checked [bold]{batch.total_files}[/bold] file(s): "
        f"[green]{len(batch.clean_files)} clean[/green], "
        f"[red]{len(batch.files_with_errors)} with errors[/red]\n"
    )

    for entry in batch.entries:
        if entry.read_error:
            console.print(f"[red]UNREADABLE[/red] {entry.file_path} -- {entry.read_error}")
        elif entry.has_errors:
            error_count = len([v for v in entry.result.violations if v.severity == "error"])
            warning_count = len([v for v in entry.result.violations if v.severity == "warning"])
            console.print(f"[red]ISSUES[/red] {entry.file_path} -- {error_count} error(s), {warning_count} warning(s)")
        else:
            console.print(f"[green]OK[/green] {entry.file_path}")


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

    console.print(f"[green]\u2713[/green] Wrote {written} fixture(s) to {output_dir}")


if __name__ == "__main__":
    app()
