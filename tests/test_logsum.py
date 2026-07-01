"""Tests for logsum CLI — every rule in spec.md covered.

Sections map to spec headings:
  §1  Grouping & sorting
  §2  Normalisation
  §3  Aggregated columns (first_seen / last_seen)
  §4  Missing level → UNKNOWN
  §5  Malformed timestamp behaviour
  §6  Empty input
  §7  CLI flags & exit codes
"""

import csv
import re
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LOGSUM = [sys.executable, str(Path(__file__).parent.parent / "src" / "logsum.py")]
FIXTURES = Path(__file__).parent / "fixtures"


def run_logsum(*args, cwd=None):
    """Invoke logsum; return (returncode, stdout, stderr)."""
    result = subprocess.run(
        LOGSUM + list(args),
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result.returncode, result.stdout, result.stderr


def write_csv(path: Path, rows, header=("timestamp", "level", "service", "message")):
    """Write a CSV file at *path* and return the path."""
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path


def read_csv(path: Path) -> list[dict]:
    """Return list-of-dicts from a CSV file."""
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# §1  Grouping & sorting
# ---------------------------------------------------------------------------


class TestGrouping:
    def test_single_group(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("2024-01-01T00:00:00", "INFO", "svc", "a"),
                ("2024-01-01T01:00:00", "INFO", "svc", "b"),
            ],
        )
        out = tmp_path / "out.csv"
        rc, _, _ = run_logsum("--input", str(inp), "--output", str(out))
        assert rc == 0
        rows = read_csv(out)
        assert len(rows) == 1
        assert rows[0]["level"] == "INFO"
        assert rows[0]["service"] == "svc"

    def test_multiple_groups(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("2024-01-01T00:00:00", "INFO", "api", "x"),
                ("2024-01-01T01:00:00", "WARN", "db", "y"),
                ("2024-01-01T02:00:00", "INFO", "api", "z"),
            ],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        rows = read_csv(out)
        assert len(rows) == 2
        keys = {(r["level"], r["service"]) for r in rows}
        assert ("INFO", "api") in keys
        assert ("WARN", "db") in keys

    def test_count_aggregated_per_group(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("2024-01-01T00:00:00", "INFO", "svc", "a"),
                ("2024-01-01T01:00:00", "INFO", "svc", "b"),
                ("2024-01-01T02:00:00", "INFO", "svc", "c"),
                ("2024-01-01T03:00:00", "WARN", "svc", "d"),
            ],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        rows = read_csv(out)
        by_level = {r["level"]: r for r in rows}
        assert by_level["INFO"]["count"] == "3"
        assert by_level["WARN"]["count"] == "1"

    def test_sorted_by_level_ascending(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("2024-01-01T00:00:00", "WARN", "svc", "x"),
                ("2024-01-01T01:00:00", "ERROR", "svc", "x"),
                ("2024-01-01T02:00:00", "INFO", "svc", "x"),
            ],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        levels = [r["level"] for r in read_csv(out)]
        assert levels == sorted(levels)

    def test_sorted_by_service_within_same_level(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("2024-01-01T00:00:00", "INFO", "zebra", "x"),
                ("2024-01-01T01:00:00", "INFO", "apple", "x"),
                ("2024-01-01T02:00:00", "INFO", "mango", "x"),
            ],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        services = [r["service"] for r in read_csv(out)]
        assert services == sorted(services)

    def test_sorted_level_then_service_combined(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("2024-01-01T00:00:00", "WARN", "beta", "x"),
                ("2024-01-01T01:00:00", "INFO", "zebra", "x"),
                ("2024-01-01T02:00:00", "ERROR", "alpha", "x"),
                ("2024-01-01T03:00:00", "INFO", "apple", "x"),
            ],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        rows = read_csv(out)
        pairs = [(r["level"], r["service"]) for r in rows]
        assert pairs == sorted(pairs)

    def test_fixture_typical(self, tmp_path):
        """Fixture: 6 rows → 3 groups (INFO/api-gateway, WARN/db, ERROR/auth)."""
        out = tmp_path / "out.csv"
        rc, _, _ = run_logsum(
            "--input", str(FIXTURES / "typical.csv"), "--output", str(out)
        )
        assert rc == 0
        rows = read_csv(out)
        assert len(rows) == 3
        keys = {(r["level"], r["service"]) for r in rows}
        assert ("INFO", "api-gateway") in keys
        assert ("WARN", "db") in keys
        assert ("ERROR", "auth") in keys

    def test_output_has_all_required_columns(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [("2024-01-01T00:00:00", "INFO", "svc", "msg")],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        rows = read_csv(out)
        assert set(rows[0].keys()) >= {"level", "service", "count", "first_seen", "last_seen"}


# ---------------------------------------------------------------------------
# §2  Normalisation
# ---------------------------------------------------------------------------


class TestNormalisation:
    def test_level_lowercased_input_uppercased_in_output(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [("2024-01-01T00:00:00", "warn", "svc", "msg")],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        assert read_csv(out)[0]["level"] == "WARN"

    def test_level_mixed_case_uppercased(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [("2024-01-01T00:00:00", "Info", "svc", "msg")],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        assert read_csv(out)[0]["level"] == "INFO"

    def test_level_whitespace_stripped_and_uppercased(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [("2024-01-01T00:00:00", "  info  ", "svc", "msg")],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        assert read_csv(out)[0]["level"] == "INFO"

    def test_normalisation_merges_case_variants_into_one_group(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("2024-01-01T00:00:00", "warn", "svc", "a"),
                ("2024-01-01T01:00:00", "WARN", "svc", "b"),
                ("2024-01-01T02:00:00", "Warn", "svc", "c"),
            ],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        rows = read_csv(out)
        assert len(rows) == 1
        assert rows[0]["count"] == "3"
        assert rows[0]["level"] == "WARN"

    def test_service_whitespace_stripped(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [("2024-01-01T00:00:00", "INFO", "  my-api  ", "msg")],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        assert read_csv(out)[0]["service"] == "my-api"

    def test_service_case_preserved(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [("2024-01-01T00:00:00", "INFO", "MyService", "msg")],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        assert read_csv(out)[0]["service"] == "MyService"

    def test_service_with_different_cases_is_two_groups(self, tmp_path):
        """'Api' and 'api' are different services (case preserved)."""
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("2024-01-01T00:00:00", "INFO", "Api", "a"),
                ("2024-01-01T01:00:00", "INFO", "api", "b"),
            ],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        rows = read_csv(out)
        assert len(rows) == 2

    def test_timestamp_whitespace_stripped_row_not_skipped(self, tmp_path):
        """Leading/trailing spaces on a valid ISO timestamp → row is counted."""
        inp = write_csv(
            tmp_path / "in.csv",
            [("  2024-01-01T00:00:00  ", "INFO", "svc", "msg")],
        )
        out = tmp_path / "out.csv"
        rc, _, stderr = run_logsum("--input", str(inp), "--output", str(out))
        assert rc == 0
        rows = read_csv(out)
        assert len(rows) == 1
        assert rows[0]["count"] == "1"


# ---------------------------------------------------------------------------
# §3  first_seen / last_seen
# ---------------------------------------------------------------------------


class TestFirstLastSeen:
    def test_first_seen_is_earliest_timestamp(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("2024-01-01T10:00:00", "INFO", "svc", "a"),
                ("2024-01-01T08:00:00", "INFO", "svc", "b"),
                ("2024-01-01T12:00:00", "INFO", "svc", "c"),
            ],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        assert read_csv(out)[0]["first_seen"] == "2024-01-01T08:00:00"

    def test_last_seen_is_latest_timestamp(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("2024-01-01T10:00:00", "INFO", "svc", "a"),
                ("2024-01-01T08:00:00", "INFO", "svc", "b"),
                ("2024-01-01T12:00:00", "INFO", "svc", "c"),
            ],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        assert read_csv(out)[0]["last_seen"] == "2024-01-01T12:00:00"

    def test_single_row_first_equals_last(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [("2024-06-15T14:30:00", "INFO", "svc", "msg")],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        row = read_csv(out)[0]
        assert row["first_seen"] == row["last_seen"]

    def test_first_last_seen_are_per_group(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("2024-01-01T01:00:00", "INFO", "a", "x"),
                ("2024-01-01T05:00:00", "INFO", "a", "x"),
                ("2024-01-01T02:00:00", "WARN", "b", "x"),
                ("2024-01-01T08:00:00", "WARN", "b", "x"),
            ],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        rows = {(r["level"], r["service"]): r for r in read_csv(out)}
        assert rows[("INFO", "a")]["first_seen"] == "2024-01-01T01:00:00"
        assert rows[("INFO", "a")]["last_seen"] == "2024-01-01T05:00:00"
        assert rows[("WARN", "b")]["first_seen"] == "2024-01-01T02:00:00"
        assert rows[("WARN", "b")]["last_seen"] == "2024-01-01T08:00:00"

    def test_fixture_typical_info_group_timestamps(self, tmp_path):
        """Fixture: INFO/api-gateway has 3 rows; earliest=07:00, latest=10:00."""
        out = tmp_path / "out.csv"
        run_logsum(
            "--input", str(FIXTURES / "typical.csv"), "--output", str(out)
        )
        rows = {(r["level"], r["service"]): r for r in read_csv(out)}
        info = rows[("INFO", "api-gateway")]
        assert info["first_seen"] == "2024-01-01T07:00:00"
        assert info["last_seen"] == "2024-01-01T10:00:00"
        assert info["count"] == "3"


# ---------------------------------------------------------------------------
# §4  Missing level → UNKNOWN
# ---------------------------------------------------------------------------


class TestMissingLevel:
    def test_blank_level_becomes_unknown(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [("2024-01-01T00:00:00", "", "svc", "msg")],
        )
        out = tmp_path / "out.csv"
        rc, _, _ = run_logsum("--input", str(inp), "--output", str(out))
        assert rc == 0
        assert read_csv(out)[0]["level"] == "UNKNOWN"

    def test_whitespace_only_level_becomes_unknown(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [("2024-01-01T00:00:00", "   ", "svc", "msg")],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        assert read_csv(out)[0]["level"] == "UNKNOWN"

    def test_blank_level_row_is_counted_not_skipped(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("2024-01-01T00:00:00", "", "svc", "a"),
                ("2024-01-01T01:00:00", "", "svc", "b"),
            ],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        rows = read_csv(out)
        assert len(rows) == 1
        assert rows[0]["count"] == "2"

    def test_unknown_grouped_by_service(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("2024-01-01T00:00:00", "", "alpha", "a"),
                ("2024-01-01T01:00:00", "", "beta", "b"),
            ],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        rows = read_csv(out)
        assert len(rows) == 2
        keys = {(r["level"], r["service"]) for r in rows}
        assert ("UNKNOWN", "alpha") in keys
        assert ("UNKNOWN", "beta") in keys

    def test_unknown_coexists_with_named_levels(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("2024-01-01T00:00:00", "",     "svc", "a"),
                ("2024-01-01T01:00:00", "INFO", "svc", "b"),
                ("2024-01-01T02:00:00", "WARN", "svc", "c"),
            ],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        levels = {r["level"] for r in read_csv(out)}
        assert "UNKNOWN" in levels
        assert "INFO" in levels
        assert "WARN" in levels

    def test_fixture_missing_levels(self, tmp_path):
        """Fixture: blank + whitespace level → UNKNOWN; INFO row stays INFO."""
        out = tmp_path / "out.csv"
        rc, _, _ = run_logsum(
            "--input", str(FIXTURES / "missing_levels.csv"), "--output", str(out)
        )
        assert rc == 0
        rows = read_csv(out)
        levels = {r["level"] for r in rows}
        assert "UNKNOWN" in levels
        assert "INFO" in levels
        unknown_rows = [r for r in rows if r["level"] == "UNKNOWN"]
        assert len(unknown_rows) == 1
        assert unknown_rows[0]["count"] == "2"


# ---------------------------------------------------------------------------
# §5  Malformed timestamp
# ---------------------------------------------------------------------------


class TestMalformedTimestamp:
    def test_bad_timestamp_row_is_skipped(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("not-a-date",          "INFO", "svc", "bad"),
                ("2024-01-01T00:00:00", "INFO", "svc", "good"),
            ],
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        rows = read_csv(out)
        assert rows[0]["count"] == "1"

    def test_bad_timestamp_warning_on_stderr(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("not-a-date",          "INFO", "svc", "bad"),
                ("2024-01-01T00:00:00", "INFO", "svc", "ok"),
            ],
        )
        out = tmp_path / "out.csv"
        _, _, stderr = run_logsum("--input", str(inp), "--output", str(out))
        assert "WARNING" in stderr
        assert "bad timestamp" in stderr

    def test_bad_timestamp_warning_includes_bad_value(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("TOTALLY_WRONG",       "INFO", "svc", "bad"),
                ("2024-01-01T00:00:00", "INFO", "svc", "ok"),
            ],
        )
        out = tmp_path / "out.csv"
        _, _, stderr = run_logsum("--input", str(inp), "--output", str(out))
        assert "TOTALLY_WRONG" in stderr

    def test_bad_timestamp_warning_includes_row_number(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("2024-01-01T00:00:00", "INFO", "svc", "ok"),
                ("bad-ts",              "INFO", "svc", "bad"),
            ],
        )
        out = tmp_path / "out.csv"
        _, _, stderr = run_logsum("--input", str(inp), "--output", str(out))
        # Some row number must appear in the warning line
        assert re.search(r"WARNING.*\d+", stderr)

    def test_bad_timestamp_summary_line_on_stderr(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("bad1",                "INFO", "svc", "x"),
                ("bad2",                "INFO", "svc", "x"),
                ("2024-01-01T00:00:00", "INFO", "svc", "x"),
            ],
        )
        out = tmp_path / "out.csv"
        _, _, stderr = run_logsum("--input", str(inp), "--output", str(out))
        assert "skipped 2 row(s) due to bad timestamps" in stderr

    def test_single_bad_timestamp_summary_line(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("bad-ts",              "INFO", "svc", "x"),
                ("2024-01-01T00:00:00", "INFO", "svc", "x"),
            ],
        )
        out = tmp_path / "out.csv"
        _, _, stderr = run_logsum("--input", str(inp), "--output", str(out))
        assert "skipped 1 row(s) due to bad timestamps" in stderr

    def test_all_bad_timestamps_output_is_header_only(self, tmp_path):
        out = tmp_path / "out.csv"
        rc, _, _ = run_logsum(
            "--input", str(FIXTURES / "all_bad_timestamps.csv"),
            "--output", str(out),
        )
        assert rc == 0
        rows = read_csv(out)
        assert rows == []

    def test_all_bad_timestamps_exit_code_zero(self, tmp_path):
        out = tmp_path / "out.csv"
        rc, _, _ = run_logsum(
            "--input", str(FIXTURES / "all_bad_timestamps.csv"),
            "--output", str(out),
        )
        assert rc == 0

    def test_all_bad_timestamps_output_has_header(self, tmp_path):
        out = tmp_path / "out.csv"
        run_logsum(
            "--input", str(FIXTURES / "all_bad_timestamps.csv"),
            "--output", str(out),
        )
        content = out.read_text()
        assert "level" in content
        assert "service" in content

    def test_mixed_fixture_two_bad_timestamps(self, tmp_path):
        """Fixture: rows 2 & 4 have bad timestamps; 2 good rows → 2 groups."""
        out = tmp_path / "out.csv"
        rc, _, stderr = run_logsum(
            "--input", str(FIXTURES / "mixed.csv"), "--output", str(out)
        )
        assert rc == 0
        assert "skipped 2 row(s) due to bad timestamps" in stderr
        rows = read_csv(out)
        assert len(rows) == 2  # (INFO, api) and (UNKNOWN, db)

    def test_slash_separated_date_is_bad_timestamp(self, tmp_path):
        """2024/01/01 00:00:00 is not valid ISO-8601 → skipped."""
        inp = write_csv(
            tmp_path / "in.csv",
            [
                ("2024/01/01 00:00:00", "INFO", "svc", "bad"),
                ("2024-01-01T00:00:00", "INFO", "svc", "good"),
            ],
        )
        out = tmp_path / "out.csv"
        _, _, stderr = run_logsum("--input", str(inp), "--output", str(out))
        assert "skipped 1 row(s) due to bad timestamps" in stderr


# ---------------------------------------------------------------------------
# §6  Empty input
# ---------------------------------------------------------------------------


class TestEmptyInput:
    def test_empty_input_exit_code_zero(self, tmp_path):
        out = tmp_path / "out.csv"
        rc, _, _ = run_logsum(
            "--input", str(FIXTURES / "empty.csv"), "--output", str(out)
        )
        assert rc == 0

    def test_empty_input_output_is_header_only(self, tmp_path):
        out = tmp_path / "out.csv"
        run_logsum("--input", str(FIXTURES / "empty.csv"), "--output", str(out))
        rows = read_csv(out)
        assert rows == []

    def test_empty_input_output_file_has_header_columns(self, tmp_path):
        out = tmp_path / "out.csv"
        run_logsum("--input", str(FIXTURES / "empty.csv"), "--output", str(out))
        content = out.read_text()
        for col in ("level", "service", "count", "first_seen", "last_seen"):
            assert col in content

    def test_empty_input_stderr_zero_groups(self, tmp_path):
        out = tmp_path / "out.csv"
        _, _, stderr = run_logsum(
            "--input", str(FIXTURES / "empty.csv"), "--output", str(out)
        )
        assert "0 groups written" in stderr

    def test_dynamically_created_empty_input(self, tmp_path):
        inp = write_csv(tmp_path / "in.csv", [])  # header only, zero data rows
        out = tmp_path / "out.csv"
        rc, _, stderr = run_logsum("--input", str(inp), "--output", str(out))
        assert rc == 0
        assert read_csv(out) == []
        assert "0 groups written" in stderr


# ---------------------------------------------------------------------------
# §7  CLI flags & exit codes
# ---------------------------------------------------------------------------


class TestCLIFlags:
    def test_missing_input_file_exit_code_1(self, tmp_path):
        out = tmp_path / "out.csv"
        rc, _, _ = run_logsum(
            "--input", str(tmp_path / "nonexistent.csv"),
            "--output", str(out),
        )
        assert rc == 1

    def test_help_flag_exit_code_zero(self):
        rc, stdout, _ = run_logsum("--help")
        assert rc == 0

    def test_help_mentions_input_flag(self):
        _, stdout, _ = run_logsum("--help")
        assert "--input" in stdout

    def test_help_mentions_output_flag(self):
        _, stdout, _ = run_logsum("--help")
        assert "--output" in stdout

    def test_successful_run_exit_code_zero(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [("2024-01-01T00:00:00", "INFO", "svc", "msg")],
        )
        out = tmp_path / "out.csv"
        rc, _, _ = run_logsum("--input", str(inp), "--output", str(out))
        assert rc == 0

    def test_explicit_output_path_creates_file(self, tmp_path):
        inp = write_csv(
            tmp_path / "in.csv",
            [("2024-01-01T00:00:00", "INFO", "svc", "msg")],
        )
        out = tmp_path / "result.csv"
        assert not out.exists()
        run_logsum("--input", str(inp), "--output", str(out))
        assert out.exists()

    def test_default_output_path_is_summary_csv(self, tmp_path):
        """When --output is omitted, summary.csv is written in the CWD."""
        inp = write_csv(
            tmp_path / "in.csv",
            [("2024-01-01T00:00:00", "INFO", "svc", "msg")],
        )
        rc, _, _ = run_logsum("--input", str(inp), cwd=str(tmp_path))
        assert rc == 0
        assert (tmp_path / "summary.csv").exists()

    def test_all_bad_timestamps_exit_code_zero(self, tmp_path):
        """All-skipped case still exits 0 per spec §5."""
        out = tmp_path / "out.csv"
        rc, _, _ = run_logsum(
            "--input", str(FIXTURES / "all_bad_timestamps.csv"),
            "--output", str(out),
        )
        assert rc == 0

    def test_empty_input_exit_code_zero_via_flag(self, tmp_path):
        """Empty-input case exits 0 per spec §6."""
        out = tmp_path / "out.csv"
        rc, _, _ = run_logsum(
            "--input", str(FIXTURES / "empty.csv"),
            "--output", str(out),
        )
        assert rc == 0
