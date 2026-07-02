# by-hand vs agent — logsum build comparison

## What both produced

Both approaches produced working implementations of the full spec (§1–§9): grouping,
normalisation, first/last seen, UNKNOWN sentinel, bad-timestamp skipping with stderr
warnings, empty-input handling, `--min-count` filtering, and correct exit codes.

Both are ~95 lines of stdlib-only Python, structured identically: `_parse_ts`,
`summarise`, `main`. Both have a test suite with 8 classes covering the same spec
sections, and both pass all tests with `ruff check` clean.

---

## Where the agent saved time

The agent produced all files — implementation, five fixtures, 24 tests, a refactored
v2, CI config, and a provenance note — in a single session with no iteration. By hand,
the same build was spread across multiple commits and PRs (first commit → CI → refactor
→ `--min-count`), took multiple rounds of linting fixes, and required back-and-forth
on the spec to clarify edge cases.

The agent also needed no scaffolding decisions — it inferred directory layout, naming
conventions, and test structure directly from the spec and existing project shape.

---

## Where the agent went wrong or shorter

**Tests are significantly shorter and shallower.**
By-hand: 744 lines, 45 tests. Agent: 346 lines, 24 tests.

The agent leaned heavily on shared fixture files rather than building purpose-built
inline data for each test. Most agent tests work by running against `typical.csv` and
checking indirect results, whereas the by-hand tests each construct exact minimal input
with `write_csv()` and pin specific output values. Concrete gaps:

- No test that `warn`/`WARN`/`Warn` all merge into one group (normalisation merging).
- No test for timestamp whitespace stripping (a row with `"  2024-01-01T00:00:00  "`
  is valid — agent skips this edge case entirely).
- No test that `--output` default is `summary.csv` written in the CWD.
- No `--help` flag tests.
- `first_seen`/`last_seen` are checked loosely (`"07:00:00" in g["first_seen"]`) rather
  than as exact ISO strings.
- `TestMinCount` has no `_make_input` helper — each test re-runs against `typical.csv`
  meaning count values are coupled to fixture content rather than being explicit.

**One subtle implementation difference.**
The agent caught `(ValueError, TypeError)` on timestamp parsing; by-hand caught
`(ValueError, AttributeError)`. Both are defensive, but the reasoning differs and
neither was derived from the spec — the spec just says "cannot be parsed as ISO-8601".

**`main()` is narrower.**
The by-hand version accepts optional positional `INPUT`/`OUTPUT` args in addition to
`--input`/`--output` flags, which makes the tool slightly more ergonomic at the command
line. The agent implemented flags only, which matches the spec literally but misses a
usability improvement the by-hand author added.

---

## What the agent did better

The agent's `run_logsum()` helper returns the full `CompletedProcess` object, which is
correct but verbose. The by-hand version returns `(returncode, stdout, stderr)` — more
ergonomic but a leaky abstraction if you ever need other fields. Neither is strictly
better; this is a style call.

The agent's `"0 groups written"` placement is arguably more correct: it is printed
*inside* the output `with` block, immediately before returning, making the control flow
explicit. The by-hand version prints it *after* the output block closes, which works
but reads as an afterthought.

---

## What I learned about supervised vs async

The plan used here was **supervised** — a detailed, step-by-step plan was written and
approved before any code was generated, with explicit constraints (read spec only, do
not read existing `src/logsum.py`).

That level of supervision produced a correct implementation in one shot, but it
required a well-specified plan to get there. Without the plan, an async agent given
only "build logsum from spec.md" would almost certainly have read the existing source
and reproduced it. The plan is what made the parallel build genuinely independent.

The test quality gap reveals the limit of supervision: the plan specified what test
classes to write and which spec sections to cover, but it did not specify that tests
should use inline data rather than fixtures. That design decision — which significantly
affects test precision — was left to the agent, and the agent chose the path of least
resistance (reuse fixtures).

---

## What I would do differently next time

**Specify the test data strategy explicitly in the plan.** The difference between
`write_csv()` inline data and shared fixture files is not obvious from a spec, but it
has a large effect on test granularity. The plan should say which tests use fixtures and
which build their own data.

**Include Step 4 (refactor) only if you want to compare refactor approaches.** The
refactor step was added to the plan to mirror the by-hand build history (commit
`52f1c07 Refactor summarise() for clarity`). It produced a valid `logsum_v2.py` with
`NormalisedRow` and `GroupState`, but since the test suite only tests `logsum.py` there
is no verification that `logsum_v2.py` is behaviourally equivalent. If the goal is
comparison, the refactor step adds noise without adding signal unless a second test run
against `logsum_v2.py` is also planned.

**Run the agent against a spec that has a few deliberate ambiguities.** Both builds
resolved edge cases the same way (e.g., `UNKNOWN` grouping, all-bad-timestamps → exit
0) because those were clarified in `questions.md`. A more interesting comparison would
be to run the agent against the spec *before* the Q&A and see where it diverges.
