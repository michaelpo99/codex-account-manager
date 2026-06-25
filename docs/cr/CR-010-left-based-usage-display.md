# CR-010: Left-based usage display for status and GUI

Status: Proposed

## 1. Summary

Official Codex surfaces now present rate limits as remaining usage, for example `85% left`.
This repository still presents `cx status`, `cx best`, and the GUI table as used percentages such as `15% used`.

That difference makes the same account look inverted across tools and is easy to misread.

This CR changes the user-facing presentation to remaining usage while preserving the current internal data model and ranking behavior.

## 2. Goals

1. Change human-readable CLI output from `% used` to `% left`.
2. Change GUI rate-limit column headers and values to reflect remaining usage.
3. Keep internal status fields based on `usedPercent` from Codex app-server.
4. Keep `rank` and `best` behavior unchanged.
5. Update docs and tests to match the new display language.

## 3. Non-goals

1. Do not change `cx_ranking.py` scoring, blocked detection, or sort keys.
2. Do not rename JSON fields such as `primary_used` or `secondary_used`.
3. Do not change the app-server integration or replace it with stdout parsing.
4. Do not add a compatibility flag for old `% used` output.

## 4. Design

### 4.1 Data model

Codex app-server currently returns `usedPercent`.
`cx` should keep storing and transporting those values as `primary_used` and `secondary_used`.

The remaining view is derived only at render time:

```text
left = clamp(100 - used, 0, 100)
```

### 4.2 CLI output

`cx status` and `cx best` human-readable output should print:

```text
5h: 85% left | reset 2026-06-25 13:51
7d: 98% left | reset 2026-07-02 10:19
```

Blocked accounts should still be considered blocked when internal `used >= 100`.
Only the wording changes.

### 4.3 GUI output

The table should keep using the same JSON payload, but display remaining percentages.

Suggested column labels:

```text
5h left
7d left
```

The reset columns can stay unchanged.

## 5. Impact

### 5.1 Ranking and best

No ranking code should change.
`rank` and `best` must continue to use the current `used`-based internal fields and reset timestamps.

### 5.2 JSON compatibility

`cx status --json` should remain backward compatible and continue exposing `primary_used` / `secondary_used`.

### 5.3 Documentation

README and spec examples should be updated so examples match the new display language and no longer show `% used` for status output examples.

## 6. Verification

1. Add or update CLI tests to verify `% left` output for `cx status` and `cx best`.
2. Keep JSON output tests asserting the internal `primary_used` value.
3. Update GUI formatter tests to verify remaining percentage rendering.
4. Run targeted tests for status, best, GUI formatting, and manual/docs text if touched.
