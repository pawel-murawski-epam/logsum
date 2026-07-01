# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

`logsum` is a tiny CLI that reads `data/events.csv` (columns: `timestamp`, `level`, `service`, `message`) and prints a counted summary grouped by level and service.

## Conventions

- Source code lives in `src/`, tests in `tests/`, sample data in `data/`.
- Use Python 3.11 standard library only (`csv`, `argparse`, `collections`).
- Lint with `ruff check .`; run tests with `pytest`.
- Single test: `pytest tests/test_<name>.py`.

## Escalation gates

- **Stop before adding any third-party dependency** — ask first.
- **Use synthetic data only** — never reference or import real log data.
- **Do not modify `spec.md` after sign-off** without explicit user confirmation.
