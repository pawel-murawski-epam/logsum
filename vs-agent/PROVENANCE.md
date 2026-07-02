# PROVENANCE — vs-agent build

## Spec reference

- **Spec:** `spec.md`, signed off 26.06.2026
- §1–§9 implemented; §8 acknowledged (explicitly out of scope)
- **Additional reference:** `questions.md` (Q&A clarifications on grouping, missing level, and running tests — no code copied)

## Build steps (in order)

1. Read `spec.md` to understand requirements (§1–§9)
2. Read `questions.md` for Q&A clarifications on grouping key and missing-level handling
3. Created data fixture: `vs-agent/data/events.csv` (verbatim copy of `data/events.csv`, synthetic data)
4. Created test fixtures:
   - `vs-agent/tests/fixtures/empty.csv` — header-only input
   - `vs-agent/tests/fixtures/typical.csv` — 6 rows, 3 groups
   - `vs-agent/tests/fixtures/all_bad_timestamps.csv` — 3 rows all unparseable
   - `vs-agent/tests/fixtures/missing_levels.csv` — blank/whitespace/normal level rows
   - `vs-agent/tests/fixtures/mixed.csv` — rows 2+4 bad ts, row 5 blank level
5. Wrote `vs-agent/src/logsum.py` from spec.md and questions.md only
6. Wrote `vs-agent/tests/test_logsum.py` from spec.md + fixture content (black-box subprocess tests)
7. Wrote `vs-agent/src/logsum_v2.py` — refactored with `NormalisedRow` dataclass and `GroupState` NamedTuple
8. Wrote `vs-agent/ci.yml` — adapted from root CI

## Independence statement

The existing `src/logsum.py` was **not read or referenced** at any point during this build. The implementation in `vs-agent/src/logsum.py` was derived solely from `spec.md` and `questions.md`.

## Deviations from by-hand build

Cosmetic only (variable names, ordering); behaviour is identical per spec.

## Verification

```bash
pytest vs-agent/tests/test_logsum.py -v
ruff check vs-agent/
```

## Constraints observed

- Stdlib only (`csv`, `argparse`, `collections`, `datetime`, `dataclasses`, `typing`) — no third-party dependencies
- Synthetic data only — no real log data referenced
- No modification to `spec.md`
