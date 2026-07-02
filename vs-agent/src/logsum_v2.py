"""logsum v2 — refactored with dataclass and NamedTuple; same public API."""

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple

_OUTPUT_FIELDS = ["level", "service", "count", "first_seen", "last_seen"]


@dataclass(frozen=True)
class NormalisedRow:
    timestamp: datetime
    level: str
    service: str


class GroupState(NamedTuple):
    count: int
    first_seen: datetime
    last_seen: datetime


def _warn_bad_row(row_num: int, raw_ts: str) -> None:
    print(
        f'WARNING: skipping row {row_num} — bad timestamp: "{raw_ts}"',
        file=sys.stderr,
    )


def parse_row(raw: dict, row_num: int) -> "NormalisedRow | None":
    raw_ts = (raw.get("timestamp") or "").strip()
    try:
        ts = datetime.fromisoformat(raw_ts)
    except (ValueError, TypeError):
        _warn_bad_row(row_num, raw_ts)
        return None
    raw_level = (raw.get("level") or "").strip()
    level = raw_level.upper() if raw_level else "UNKNOWN"
    service = (raw.get("service") or "").strip()
    return NormalisedRow(timestamp=ts, level=level, service=service)


def _accumulate(reader) -> tuple[dict[tuple[str, str], GroupState], int]:
    groups: dict[tuple[str, str], GroupState] = {}
    skipped = 0
    for row_num, raw in enumerate(reader, start=2):
        norm = parse_row(raw, row_num)
        if norm is None:
            skipped += 1
            continue
        key = (norm.level, norm.service)
        if key not in groups:
            groups[key] = GroupState(count=1, first_seen=norm.timestamp, last_seen=norm.timestamp)
        else:
            g = groups[key]
            groups[key] = GroupState(
                count=g.count + 1,
                first_seen=min(g.first_seen, norm.timestamp),
                last_seen=max(g.last_seen, norm.timestamp),
            )
    return groups, skipped


def summarise(input_path: str, output_path: str, min_count: int = 0) -> int:
    try:
        fh = open(input_path, newline="", encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        reader = csv.DictReader(fh)
        groups, skipped = _accumulate(reader)
    finally:
        fh.close()

    if skipped:
        print(f"skipped {skipped} row(s) due to bad timestamps", file=sys.stderr)

    if min_count > 0:
        groups = {k: v for k, v in groups.items() if v.count >= min_count}

    try:
        with open(output_path, "w", newline="", encoding="utf-8") as out:
            writer = csv.DictWriter(out, fieldnames=_OUTPUT_FIELDS)
            writer.writeheader()
            if not groups:
                print("0 groups written", file=sys.stderr)
                return 0
            for (level, service), g in sorted(groups.items()):
                writer.writerow(
                    {
                        "level": level,
                        "service": service,
                        "count": g.count,
                        "first_seen": g.first_seen.isoformat(),
                        "last_seen": g.last_seen.isoformat(),
                    }
                )
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="logsum")
    parser.add_argument("--input", default="data/events.csv", metavar="FILE")
    parser.add_argument("--output", default="summary.csv", metavar="FILE")
    parser.add_argument("--min-count", type=int, default=0, metavar="N")
    args = parser.parse_args(argv)
    return summarise(args.input, args.output, args.min_count)


if __name__ == "__main__":
    sys.exit(main())
