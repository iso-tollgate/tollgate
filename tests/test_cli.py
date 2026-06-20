"""Tests for cli.py, using Typer's CliRunner to invoke commands the
same way a real user would from the command line.

These tests exercise the full wiring end-to-end: real generated
fixtures -> real validation rules -> real CLI output/exit codes.
Confirms the project's pieces actually work TOGETHER, not just in
isolation (each rule module already has its own unit tests).
"""

from pathlib import Path

from typer.testing import CliRunner

from tollgate.cli import app
from tollgate.generator.synthetic_fixtures import build_valid_baseline, inject_error
from tollgate.validation.models import RuleId

runner = CliRunner()


def _write_fixture(tmp_path: Path, rule_id: RuleId | None, seed: int = 99) -> Path:
    needs_ultimate = rule_id in (RuleId.ADDRESS_FREEFORM_ONLY, RuleId.ADDRESS_TOO_MANY_LINES)
    baseline = build_valid_baseline(seed=seed, include_ultimate_parties=needs_ultimate)
    if rule_id is None:
        xml_str = baseline
    else:
        xml_str, _ = inject_error(baseline, rule_id)
    path = tmp_path / "payment.xml"
    path.write_text(xml_str, encoding="utf-8")
    return path


def test_validate_clean_message_exits_zero(tmp_path):
    path = _write_fixture(tmp_path, rule_id=None)
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 0
    # Rich's console wraps long lines, so normalize whitespace before
    # checking -- "no issues found" can be split across a line break
    # ("-- no\nissues found") depending on terminal width.
    normalized = " ".join(result.stdout.lower().split())
    assert "no issues found" in normalized


def test_validate_broken_message_exits_one(tmp_path):
    path = _write_fixture(tmp_path, rule_id=RuleId.CHARSET_VIOLATION)
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 1
    assert "charset_violation" in result.stdout


def test_validate_missing_file_exits_one():
    result = runner.invoke(app, ["validate", "this_file_does_not_exist.xml"])
    assert result.exit_code == 1
    assert "not found" in " ".join(result.stdout.lower().split())


def test_validate_unsupported_message_type_exits_one(tmp_path):
    path = _write_fixture(tmp_path, rule_id=None)
    result = runner.invoke(app, ["validate", str(path), "--message-type", "pacs.009"])
    assert result.exit_code == 1
    assert "unsupported" in " ".join(result.stdout.lower().split())


def test_validate_with_output_writes_markdown_report(tmp_path):
    path = _write_fixture(tmp_path, rule_id=RuleId.MANDATORY_FIELD_GAP)
    report_path = tmp_path / "report.md"

    result = runner.invoke(app, ["validate", str(path), "--output", str(report_path)])

    assert result.exit_code == 1  # violations found
    assert report_path.exists()
    content = report_path.read_text()
    assert "Tollgate Validation Report" in content
    assert "mandatory_field_gap" in content
    assert "not a SWIFT-certified compliance tool" in content


def test_validate_explain_without_api_key_fails_clearly(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    path = _write_fixture(tmp_path, rule_id=RuleId.CHARSET_VIOLATION)

    result = runner.invoke(app, ["validate", str(path), "--explain"])

    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.stdout


def test_generate_writes_fixtures_for_specific_rule(tmp_path):
    output_dir = tmp_path / "fixtures"
    result = runner.invoke(
        app,
        ["generate", "--count", "2", "--rule-id", "truncation_suspected", "--output-dir", str(output_dir)],
    )
    assert result.exit_code == 0
    files = list(output_dir.glob("truncation_suspected_*.xml"))
    assert len(files) == 2


def test_generate_rejects_unknown_rule_id(tmp_path):
    result = runner.invoke(
        app,
        ["generate", "--rule-id", "not_a_real_rule", "--output-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "unknown rule_id" in " ".join(result.stdout.lower().split())


def test_generate_default_covers_all_rule_ids(tmp_path):
    output_dir = tmp_path / "fixtures"
    result = runner.invoke(app, ["generate", "--count", "1", "--output-dir", str(output_dir)])
    assert result.exit_code == 0

    written_files = list(output_dir.glob("*.xml"))
    assert len(written_files) == len(list(RuleId))
