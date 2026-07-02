"""Black-box integration tests for vs-agent/src/logsum.py."""

import csv
import subprocess
import sys
import tempfile
from pathlib import Path

LOGSUM = [sys.executable, str(Path(__file__).parent.parent / "src" / "logsum.py")]
FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_logsum(*args):
    """Run logsum with the given arguments; return CompletedProcess."""
    return subprocess.run(
        LOGSUM + list(args),
        capture_output=True,
        text=True,
    )


def read_csv(path):
    """Return list of dicts from a CSV file."""
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows, fieldnames=None):
    """Write rows (list of dicts) to path; infer fieldnames from first row if not given."""
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# §1  Grouping
# ---------------------------------------------------------------------------


class TestGrouping:
    def test_groups_by_level_and_service(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        result = run_logsum(
            "--input", str(FIXTURES / "typical.csv"), "--output", out_path
        )
        assert result.returncode == 0
        rows = read_csv(out_path)
        keys = [(r["level"], r["service"]) for r in rows]
        # typical.csv has INFO/api-gateway (×3), WARN/db (×2), ERROR/auth (×1)
        assert ("INFO", "api-gateway") in keys
        assert ("WARN", "db") in keys
        assert ("ERROR", "auth") in keys
        assert len(rows) == 3

    def test_output_sorted_asc_level_then_service(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        run_logsum("--input", str(FIXTURES / "typical.csv"), "--output", out_path)
        rows = read_csv(out_path)
        keys = [(r["level"], r["service"]) for r in rows]
        assert keys == sorted(keys)

    def test_count_correct(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        run_logsum("--input", str(FIXTURES / "typical.csv"), "--output", out_path)
        rows = read_csv(out_path)
        by_key = {(r["level"], r["service"]): int(r["count"]) for r in rows}
        assert by_key[("INFO", "api-gateway")] == 3
        assert by_key[("WARN", "db")] == 2
        assert by_key[("ERROR", "auth")] == 1


# ---------------------------------------------------------------------------
# §2  Normalisation
# ---------------------------------------------------------------------------


class TestNormalisation:
    def test_level_uppercased(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        run_logsum("--input", str(FIXTURES / "typical.csv"), "--output", out_path)
        rows = read_csv(out_path)
        levels = {r["level"] for r in rows}
        # "warn" in typical.csv should become "WARN"
        assert "WARN" in levels
        assert "warn" not in levels

    def test_service_whitespace_stripped(self, tmp_path):
        inp = tmp_path / "svc_ws.csv"
        inp.write_text(
            "timestamp,level,service,message\n"
            "2024-01-01T08:00:00,INFO,  api  ,msg\n"
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        rows = read_csv(str(out))
        assert rows[0]["service"] == "api"


# ---------------------------------------------------------------------------
# §3  First / last seen
# ---------------------------------------------------------------------------


class TestFirstLastSeen:
    def test_first_and_last_seen(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        run_logsum("--input", str(FIXTURES / "typical.csv"), "--output", out_path)
        rows = read_csv(out_path)
        by_key = {(r["level"], r["service"]): r for r in rows}
        g = by_key[("INFO", "api-gateway")]
        # rows: 08:00, 10:00, 07:00 → first=07:00, last=10:00
        assert "07:00:00" in g["first_seen"]
        assert "10:00:00" in g["last_seen"]

    def test_single_row_group_first_equals_last(self, tmp_path):
        inp = tmp_path / "single.csv"
        inp.write_text(
            "timestamp,level,service,message\n"
            "2024-06-01T12:00:00,ERROR,db,oops\n"
        )
        out = tmp_path / "out.csv"
        run_logsum("--input", str(inp), "--output", str(out))
        rows = read_csv(str(out))
        assert rows[0]["first_seen"] == rows[0]["last_seen"]


# ---------------------------------------------------------------------------
# §4  Missing level
# ---------------------------------------------------------------------------


class TestMissingLevel:
    def test_blank_level_becomes_unknown(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        run_logsum(
            "--input", str(FIXTURES / "missing_levels.csv"), "--output", out_path
        )
        rows = read_csv(out_path)
        levels = {r["level"] for r in rows}
        assert "UNKNOWN" in levels

    def test_whitespace_level_becomes_unknown(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        run_logsum(
            "--input", str(FIXTURES / "missing_levels.csv"), "--output", out_path
        )
        rows = read_csv(out_path)
        # blank and whitespace rows both map to UNKNOWN/api — counted together
        by_key = {(r["level"], r["service"]): int(r["count"]) for r in rows}
        assert by_key[("UNKNOWN", "api")] == 2

    def test_missing_level_row_counted_not_skipped(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        result = run_logsum(
            "--input", str(FIXTURES / "missing_levels.csv"), "--output", out_path
        )
        assert result.returncode == 0
        rows = read_csv(out_path)
        total = sum(int(r["count"]) for r in rows)
        assert total == 3  # all 3 rows counted


# ---------------------------------------------------------------------------
# §5  Malformed timestamps
# ---------------------------------------------------------------------------


class TestMalformedTimestamp:
    def test_bad_rows_skipped_with_warning(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        result = run_logsum(
            "--input", str(FIXTURES / "all_bad_timestamps.csv"), "--output", out_path
        )
        assert result.returncode == 0
        assert "WARNING: skipping row" in result.stderr

    def test_warning_contains_row_number_and_value(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        result = run_logsum(
            "--input", str(FIXTURES / "all_bad_timestamps.csv"), "--output", out_path
        )
        assert "skipping row 2" in result.stderr
        assert "not-a-date" in result.stderr

    def test_summary_skipped_count_written(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        result = run_logsum(
            "--input", str(FIXTURES / "all_bad_timestamps.csv"), "--output", out_path
        )
        assert "skipped 3 row(s) due to bad timestamps" in result.stderr

    def test_all_bad_timestamps_header_only_exit_0(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        result = run_logsum(
            "--input", str(FIXTURES / "all_bad_timestamps.csv"), "--output", out_path
        )
        assert result.returncode == 0
        rows = read_csv(out_path)
        assert rows == []  # header written but no data rows

    def test_mixed_good_and_bad(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        result = run_logsum(
            "--input", str(FIXTURES / "mixed.csv"), "--output", out_path
        )
        assert result.returncode == 0
        rows = read_csv(out_path)
        # mixed.csv: row2 bad, row4 bad → 2 skipped; rows 1,3,5 good
        # row1: INFO/api  row3: INFO/api  row5: UNKNOWN/db
        by_key = {(r["level"], r["service"]): int(r["count"]) for r in rows}
        assert by_key[("INFO", "api")] == 2
        assert by_key[("UNKNOWN", "db")] == 1
        assert "skipped 2 row(s) due to bad timestamps" in result.stderr


# ---------------------------------------------------------------------------
# §6  Empty input
# ---------------------------------------------------------------------------


class TestEmptyInput:
    def test_empty_input_header_only_output(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        result = run_logsum(
            "--input", str(FIXTURES / "empty.csv"), "--output", out_path
        )
        assert result.returncode == 0
        rows = read_csv(out_path)
        assert rows == []

    def test_empty_input_stderr_message(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        result = run_logsum(
            "--input", str(FIXTURES / "empty.csv"), "--output", out_path
        )
        assert "0 groups written" in result.stderr

    def test_empty_input_exit_0(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        result = run_logsum(
            "--input", str(FIXTURES / "empty.csv"), "--output", out_path
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# §7  CLI flags and exit codes
# ---------------------------------------------------------------------------


class TestCLIFlags:
    def test_input_not_found_exit_1(self, tmp_path):
        out = tmp_path / "out.csv"
        result = run_logsum("--input", str(tmp_path / "nonexistent.csv"), "--output", str(out))
        assert result.returncode == 1

    def test_default_input_path(self):
        # Run from vs-agent directory so default data/events.csv is reachable
        vs_agent = Path(__file__).parent.parent
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        result = subprocess.run(
            LOGSUM + ["--output", out_path],
            capture_output=True,
            text=True,
            cwd=str(vs_agent),
        )
        assert result.returncode == 0

    def test_output_columns(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        run_logsum("--input", str(FIXTURES / "typical.csv"), "--output", out_path)
        with open(out_path, newline="") as fh:
            header = fh.readline().strip()
        assert header == "level,service,count,first_seen,last_seen"


# ---------------------------------------------------------------------------
# §9  --min-count
# ---------------------------------------------------------------------------


class TestMinCount:
    def test_min_count_filters_groups(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        run_logsum(
            "--input", str(FIXTURES / "typical.csv"),
            "--output", out_path,
            "--min-count", "2",
        )
        rows = read_csv(out_path)
        # INFO/api-gateway (3) and WARN/db (2) pass; ERROR/auth (1) filtered
        keys = {(r["level"], r["service"]) for r in rows}
        assert ("INFO", "api-gateway") in keys
        assert ("WARN", "db") in keys
        assert ("ERROR", "auth") not in keys

    def test_min_count_header_always_written(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        result = run_logsum(
            "--input", str(FIXTURES / "typical.csv"),
            "--output", out_path,
            "--min-count", "999",
        )
        assert result.returncode == 0
        with open(out_path, newline="") as fh:
            header = fh.readline().strip()
        assert header == "level,service,count,first_seen,last_seen"

    def test_min_count_zero_returns_all(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            out_path = out.name
        run_logsum(
            "--input", str(FIXTURES / "typical.csv"),
            "--output", out_path,
            "--min-count", "0",
        )
        rows = read_csv(out_path)
        assert len(rows) == 3
