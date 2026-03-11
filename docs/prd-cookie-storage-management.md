# PRD: Cookie and Web Storage Management

## Status

- Proposed
- Target phase: Phase 2

## Problem

Session bootstrap often depends on reusable auth/application state. While cookie import exists on `session_start`, there is no complete lifecycle for reading, updating, exporting, or managing local/session storage.

## Goals

- Provide complete cookie lifecycle tools.
- Add first-class localStorage/sessionStorage read and write support.
- Keep payload formats simple and script-free for agent reliability.

## Non-goals

- No encrypted secret vault in v1.
- No browser profile sync between machines.

## Proposed MCP tools

1. `browser_cookies_get`
   - Input: `session_id`
   - Output: `cookies[]`

2. `browser_cookies_set`
   - Inputs: `session_id`, `cookies[]`, `fallback_domain: str | null`
   - Output: `applied_count`, `skipped_count`

3. `browser_cookies_save`
   - Inputs: `session_id`, `output_path`, `wrap_object=true`
   - Output: `path`, `saved_count`

4. `browser_cookies_clear`
   - Inputs: `session_id`, `domain: str | null`
   - Output: `cleared_count`

5. `browser_storage_get`
   - Inputs: `session_id`, `kind=("local"|"session"|"both")`, `origin: str | null`
   - Output: key/value maps by storage kind

6. `browser_storage_set`
   - Inputs: `session_id`, `kind=("local"|"session")`, `entries: dict[str, str]`, `clear_first=false`
   - Output: `applied_count`

7. `browser_storage_clear`
   - Inputs: `session_id`, `kind=("local"|"session"|"both")`
   - Output: `cleared=true`

## Functional requirements

- Cookie set/save must reuse existing normalization conventions from `cookies.py`.
- Storage read/write should operate in current tab origin context unless `origin` override is provided.
- All storage APIs must provide deterministic ordering (for test stability).
- Large payloads should be bounded with safe limits and truncation indicators.

## Implementation notes

- Reuse `BridgeBrowser.get_cookies()` and `set_cookies()` as base primitives.
- Add helper methods in `actions.py` for storage scripts and normalization.
- Add JSON file writing helper for `browser_cookies_save`.
- Document format compatibility with `session_start(cookie_file=...)`.

## Acceptance criteria

- Cookies can be round-tripped: get -> save -> session_start(cookie_file) -> authenticated page.
- Storage values can be written and later retrieved exactly.
- Clear tools remove targeted state without affecting unrelated origin data.

## Test plan

- Unit tests for cookie save format and normalization.
- Integration tests with a fixture page that reads/writes localStorage/sessionStorage.
- Regression test ensuring `session_start(cookie_file=...)` remains compatible.

## Risks

- Storage operations are origin-scoped and may confuse users when current URL changes.
- High-volume cookie payloads can impact response size and client parsing.
