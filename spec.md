# logsum — specification

## 1. Group key

The output is grouped by the composite key `(level, service)`.
Output rows are sorted by `level` ascending, then `service` ascending.

## 2. Normalisation rules

| Field       | Rule                                                                 |
| ----------- | -------------------------------------------------------------------- |
| `level`     | Strip leading/trailing whitespace, then uppercase (`warn` → `WARN`). |
| `service`   | Strip leading/trailing whitespace; preserve original case otherwise. |
| `timestamp` | Strip leading/trailing whitespace; validate as ISO-8601 datetime.    |
| `message`   | Not used in grouping or output; ignored after parsing.               |

## 3. Aggregated columns

Each row in `summary.csv` contains:

| Column       | Description                                       |
| ------------ | ------------------------------------------------- |
| `level`      | Normalised level value (see §2).                  |
| `service`    | Normalised service name (see §2).                 |
| `count`      | Number of input rows belonging to this group.     |
| `first_seen` | Earliest valid timestamp in the group (ISO-8601). |
| `last_seen`  | Latest valid timestamp in the group (ISO-8601).   |

## 4. Missing level behaviour

A blank or absent `level` field is treated as the sentinel value `UNKNOWN`.
The row is **not** skipped; it is counted under `(UNKNOWN, <service>)`.

## 5. Malformed timestamp behaviour

If a row's `timestamp` cannot be parsed as ISO-8601:

- The row is **skipped** (not counted in any group).
- A warning is written to **stderr**: `WARNING: skipping row <n> — bad timestamp: "<value>"`.
- After processing, a summary line is written to stderr: `skipped <k> row(s) due to bad timestamps`.
- If every row is malformed the output is header-only and exit code is **0**.

## 6. Empty input behaviour

If the input file contains a header row but no data rows:

- `summary.csv` is written with the header row only.
- Stderr receives: `0 groups written`.
- Exit code is **0**.

## 7. CLI flags and exit codes

```
logsum [--input FILE] [--output FILE]

  --input  FILE   Path to input CSV  (default: data/events.csv)
  --output FILE   Path to output CSV (default: summary.csv)
  -h, --help      Show this message and exit
```

| Exit code | Meaning                                                |
| --------- | ------------------------------------------------------ |
| `0`       | Success (including empty-input and all-skipped cases). |
| `1`       | Input file not found or not readable.                  |
| `2`       | Unexpected runtime error.                              |

## 8. Out of scope

The following are explicitly **not** part of this tool:

- Filtering by date range, level, or service.
- Log formats other than the four-column CSV (`timestamp,level,service,message`).
- Streaming / tail mode.
- Any output format other than CSV.
- Third-party dependencies (stdlib only).
- Deduplication of identical messages within a group.

## §9 Minimum-count filter (--min-count N)

When `--min-count N` is supplied (N ≥ 1), only groups whose count is ≥ N are
written to the output file. The header row is always written. If no groups
satisfy the threshold the output contains the header only and exit code is 0.
Default behaviour (no flag or N = 0) is unchanged: all groups are output.

## Signed off Paweł Murawski 26.06.2026
