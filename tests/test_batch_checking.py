"""Tests for tollgate.api.check_directory and BatchCheckResult.

The central property tested throughout: one bad/unreadable file in a
batch must never prevent the rest of the batch from being checked --
matching the proven pattern already used in
.github/actions/validate/scripts/run_validation.py.
"""

import pytest

from tollgate import BatchCheckResult, check_directory
from tollgate.generator.synthetic_fixtures import build_valid_baseline, inject_error
from tollgate.validation.models import RuleId


def _make_mixed_directory(tmp_path):
    """Clean file, broken file, unreadable (binary) file, and a nested
    file in a subdirectory -- the same mix used to verify the CLI
    command manually before writing these tests.
    """
    (tmp_path / "clean.xml").write_text(build_valid_baseline(seed=1), encoding="utf-8")

    baseline = build_valid_baseline(seed=2)
    broken, _ = inject_error(baseline, RuleId.CHARSET_VIOLATION)
    (tmp_path / "broken.xml").write_text(broken, encoding="utf-8")

    (tmp_path / "garbage.xml").write_bytes(b"\x00\x01\xff\xfe")

    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "nested.xml").write_text(build_valid_baseline(seed=3), encoding="utf-8")

    return tmp_path


def test_check_directory_finds_top_level_files_only_by_default(tmp_path):
    _make_mixed_directory(tmp_path)
    batch = check_directory(tmp_path)

    assert isinstance(batch, BatchCheckResult)
    assert batch.total_files == 3  # excludes the nested file


def test_check_directory_recursive_includes_subdirectories(tmp_path):
    _make_mixed_directory(tmp_path)
    batch = check_directory(tmp_path, recursive=True)
    assert batch.total_files == 4


def test_check_directory_reports_clean_and_broken_files_correctly(tmp_path):
    _make_mixed_directory(tmp_path)
    batch = check_directory(tmp_path)

    clean_names = {p.split("/")[-1] for p in batch.clean_files}
    error_names = {p.split("/")[-1] for p in batch.files_with_errors}

    assert "clean.xml" in clean_names
    assert "broken.xml" in error_names
    assert "garbage.xml" in error_names  # unreadable counts as an error


def test_unreadable_file_does_not_abort_the_batch(tmp_path):
    """The central property: garbage.xml being unreadable must not
    prevent clean.xml and broken.xml from being checked normally.
    """
    _make_mixed_directory(tmp_path)
    batch = check_directory(tmp_path)

    assert batch.total_files == 3  # all three top-level files still processed

    garbage_entry = next(e for e in batch.entries if "garbage.xml" in e.file_path)
    assert garbage_entry.read_error is not None
    assert garbage_entry.result is None
    assert garbage_entry.has_errors  # unreadable counts as having errors

    clean_entry = next(e for e in batch.entries if "clean.xml" in e.file_path)
    assert clean_entry.read_error is None
    assert clean_entry.result is not None
    assert not clean_entry.has_errors


def test_has_any_errors_true_when_any_file_has_errors(tmp_path):
    _make_mixed_directory(tmp_path)
    batch = check_directory(tmp_path)
    assert batch.has_any_errors is True


def test_has_any_errors_false_when_all_clean(tmp_path):
    (tmp_path / "a.xml").write_text(build_valid_baseline(seed=10), encoding="utf-8")
    (tmp_path / "b.xml").write_text(build_valid_baseline(seed=11), encoding="utf-8")

    batch = check_directory(tmp_path)
    assert batch.has_any_errors is False
    assert len(batch.clean_files) == 2


def test_check_directory_raises_for_non_directory(tmp_path):
    file_path = tmp_path / "not_a_dir.xml"
    file_path.write_text(build_valid_baseline(seed=1), encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        check_directory(file_path)


def test_check_directory_with_no_matching_files_returns_empty_batch(tmp_path):
    batch = check_directory(tmp_path, pattern="*.xml")
    assert batch.total_files == 0
    assert batch.has_any_errors is False


def test_check_directory_respects_custom_pattern(tmp_path):
    (tmp_path / "payment.xml").write_text(build_valid_baseline(seed=1), encoding="utf-8")
    (tmp_path / "notes.txt").write_text("irrelevant", encoding="utf-8")

    batch = check_directory(tmp_path, pattern="*.txt")
    assert batch.total_files == 1
    assert batch.entries[0].file_path.endswith("notes.txt")


def test_batch_result_to_dict_is_json_serializable(tmp_path):
    import json

    _make_mixed_directory(tmp_path)
    batch = check_directory(tmp_path)
    d = batch.to_dict()

    serialized = json.dumps(d)  # must not raise
    assert d["total_files"] == 3
    assert d["has_any_errors"] is True
