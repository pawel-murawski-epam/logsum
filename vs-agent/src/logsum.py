import argparse
import csv
import sys
from datetime import datetime

_OUTPUT_FIELDS = ["level", "service", "count", "first_seen", "last_seen"]


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.strip())


def summarise(input_path: str, output_path: str, min_count: int = 0) -> int:
    groups: dict[tuple[str, str], dict] = {}
    skipped = 0

    try:
        fh = open(input_path, newline="", encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        reader = csv.DictReader(fh)
        for row_num, row in enumerate(reader, start=2):
            raw_ts = (row.get("timestamp") or "").strip()
            try:
                ts = _parse_ts(raw_ts)
            except (ValueError, TypeError):
                print(
                    f'WARNING: skipping row {row_num} — bad timestamp: "{raw_ts}"',
                    file=sys.stderr,
                )
                skipped += 1
                continue

            raw_level = (row.get("level") or "").strip()
            level = raw_level.upper() if raw_level else "UNKNOWN"
            service = (row.get("service") or "").strip()

            key = (level, service)
            if key not in groups:
                groups[key] = {"count": 1, "first_seen": ts, "last_seen": ts}
            else:
                g = groups[key]
                g["count"] += 1
                if ts < g["first_seen"]:
                    g["first_seen"] = ts
                if ts > g["last_seen"]:
                    g["last_seen"] = ts
    finally:
        fh.close()

    if skipped:
        print(f"skipped {skipped} row(s) due to bad timestamps", file=sys.stderr)

    if min_count > 0:
        groups = {k: v for k, v in groups.items() if v["count"] >= min_count}

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
                        "count": g["count"],
                        "first_seen": g["first_seen"].isoformat(),
                        "last_seen": g["last_seen"].isoformat(),
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
