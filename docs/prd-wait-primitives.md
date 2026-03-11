# PRD: Advanced Wait Primitives

## Status

- Proposed
- Target phase: Phase 1

## Problem

Current waiting support (`browser_wait`, `browser_wait_for_selector`) is not enough for dynamic pages that depend on URL transitions, text rendering, asynchronous JS state, or in-flight network activity.

## Goals

- Reduce flaky workflows by adding semantic wait tools.
- Provide explicit timeouts and predictable polling behavior.
- Keep results easy for agents to reason about (`matched/found/idle` flags).

## Non-goals

- No visual diff or screenshot-based waiting in v1.
- No hard dependency on CDP network capture for initial implementation.

## Proposed MCP tools

1. `browser_wait_for_url`
   - Inputs: `session_id`, `url_contains` or `url_regex`, `timeout_seconds=10`, `poll_interval_seconds=0.2`
   - Output: `matched`, `url`, `title`, `waited_ms`

2. `browser_wait_for_text`
   - Inputs: `session_id`, `text`, `selector="body"`, `case_sensitive=false`, `timeout_seconds=10`, `poll_interval_seconds=0.2`
   - Output: `found`, `selector`, `url`, `title`, `waited_ms`

3. `browser_wait_for_function`
   - Inputs: `session_id`, `script`, `timeout_seconds=10`, `poll_interval_seconds=0.2`
   - Output: `truthy`, `result`, `url`, `title`, `waited_ms`

4. `browser_wait_for_network_idle`
   - Inputs: `session_id`, `idle_ms=500`, `timeout_seconds=10`, `max_inflight=0`
   - Output: `idle`, `inflight_peak`, `waited_ms`, `url`, `title`

## Functional requirements

- Each wait tool must return structured success state instead of only raising on timeout.
- Timeout behavior should include a machine-parseable error string when unsuccessful.
- Poll intervals must be bounded to avoid CPU-heavy loops.
- Network-idle wait should rely on in-page instrumentation in v1 and evolve to CDP later.

## Implementation notes

- Add action functions in `browser_bridge_mcp/actions.py`.
- Use shared helper for polling with timeout and elapsed timing.
- Reuse `normalize_evaluate_payload` for JS result handling.
- Expose new tools in `browser_bridge_mcp/server.py`.

## Acceptance criteria

- URL wait succeeds on redirect-heavy pages with predictable timeout behavior.
- Text wait can detect async-rendered content.
- Function wait handles both primitive and object return values.
- Network-idle wait reports idle success on pages with bursty fetch/XHR activity.

## Test plan

- Unit tests for timeout and polling helper.
- Integration tests using controlled pages that delay URL/text/network conditions.
- Negative tests where conditions never match and structured timeout payload is returned.

## Risks

- In-page network idle may miss non-fetch/XHR traffic until CDP capture lands.
- User-provided predicate scripts may throw; errors must be sanitized and returned.
