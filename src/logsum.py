import argparse
import csv
import sys
from datetime import datetime

_OUTPUT_FIELDS = ['level', 'service', 'count', 'first_seen', 'last_seen']


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.strip())


def summarise(input_path: str, output_path: str) -> int:
    try:
        fh = open(input_path, newline='', encoding='utf-8')
    except OSError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1

    groups: dict[tuple[str, str], dict] = {}
    skipped = 0

    try:
        with fh:
            for row_num, row in enumerate(csv.DictReader(fh), start=2):
                raw_ts = (row.get('timestamp') or '').strip()
                try:
                    ts = _parse_ts(raw_ts)
                except (ValueError, AttributeError):
                    print(
                        f'WARNING: skipping row {row_num} — bad timestamp: "{raw_ts}"',
                        file=sys.stderr,
                    )
                    skipped += 1
                    continue

                raw_level = (row.get('level') or '').strip()
                level = raw_level.upper() if raw_level else 'UNKNOWN'
                service = (row.get('service') or '').strip()

                key = (level, service)
                if key in groups:
                    g = groups[key]
                    g['count'] += 1
                    if ts < g['first_seen']:
                        g['first_seen'] = ts
                    if ts > g['last_seen']:
                        g['last_seen'] = ts
                else:
                    groups[key] = {'count': 1, 'first_seen': ts, 'last_seen': ts}
    except OSError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2

    if skipped:
        print(f'skipped {skipped} row(s) due to bad timestamps', file=sys.stderr)

    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as out:
            writer = csv.DictWriter(out, fieldnames=_OUTPUT_FIELDS)
            writer.writeheader()
            for (level, service) in sorted(groups):
                g = groups[(level, service)]
                writer.writerow({
                    'level': level,
                    'service': service,
                    'count': g['count'],
                    'first_seen': g['first_seen'].isoformat(),
                    'last_seen': g['last_seen'].isoformat(),
                })
    except OSError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2

    if not groups:
        print('0 groups written', file=sys.stderr)

    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog='logsum')
    p.add_argument('input_file', nargs='?', default=None, metavar='INPUT')
    p.add_argument('output_file', nargs='?', default=None, metavar='OUTPUT')
    p.add_argument('--input', dest='flag_input', default='data/events.csv', metavar='FILE',
                   help='Path to input CSV  (default: data/events.csv)')
    p.add_argument('--output', dest='flag_output', default='summary.csv', metavar='FILE',
                   help='Path to output CSV (default: summary.csv)')
    args = p.parse_args(argv)
    input_path = args.input_file or args.flag_input
    output_path = args.output_file or args.flag_output
    return summarise(input_path, output_path)


if __name__ == '__main__':
    sys.exit(main())
