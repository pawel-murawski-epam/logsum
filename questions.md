# Q&A

## Where is the grouping rule?

The grouping rule is in src/logsum.py, lines 40–47.

Each CSV row is grouped by the combination of (level, service) — a two-field composite key (src/logsum.py:40). Both fields are
normalized before keying: level is uppercased (or set to 'UNKNOWN' if blank) (src/logsum.py:37), and service is stripped of  
 whitespace (src/logsum.py:38).

When a key is seen for the first time, a new group is created with count=1 and both first_seen and last_seen set to the current  
 timestamp (src/logsum.py:47). On subsequent rows with the same key, the count increments and the timestamp range is extended
(src/logsum.py:43–45).

The output is sorted lexicographically by this same (level, service) key (src/logsum.py:59).

## How is missing level handled?

    The handling is at src/logsum.py:36–37.


When a row's level field is absent or blank, raw_level evaluates to an empty string. The conditional if raw_level is false, so  
 level is set to the string 'UNKNOWN' instead of uppercasing the value. A present, non-blank level is uppercased (e.g. "error" →  
 "ERROR").

That 'UNKNOWN' value then becomes part of the group key like any other level — rows with missing level and the same service are  
 counted together under the ('UNKNOWN', service) group.

## How do I run tests and CI locally?

CI runs two steps in order: lint, then test (.github/workflows/ci.yml:22–25). To replicate locally:

1. Install dependencies (once):  
   pip install ruff pytest
1. (.github/workflows/ci.yml:19)
1. Lint:  
   ruff check .
1. (.github/workflows/ci.yml:22)
1. Run all tests:  
   pytest -v
1. (.github/workflows/ci.yml:25)
1. Run a single test file (from CLAUDE.md):  
   pytest tests/test_logsum.py  


CI targets Python 3.11 (.github/workflows/ci.yml:16). If you have multiple Python versions locally, ensure you're using 3.11.  

