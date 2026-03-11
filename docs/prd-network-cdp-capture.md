# PRD: CDP-Level Network Capture

## Status

- Proposed
- Target phase: Phase 3

## Problem

Current `browser_network_requests` captures only in-page `fetch`/`XMLHttpRequest` metadata. It misses browser-level traffic (document, script, CSS, image, redirects, failures, headers, and richer timing).

## Goals

- Capture richer network telemetry directly from CDP events.
- Support bounded retention and query filtering.
- Keep existing in-page network tool for lightweight use cases.

## Non-goals

- No full response body capture by default.
- No HAR export in v1 (can be a follow-up).

## Proposed MCP tools

1. `browser_network_capture_start`
   - Inputs:
     - `session_id`
     - `max_entries=2000`
     - `include_headers=true`
     - `include_post_data=false`
     - `url_regex: str | null`
   - Output: capture config + `started=true`

2. `browser_network_capture_get`
   - Inputs: `session_id`, `limit=200`, `clear=false`, `only_failures=false`
   - Output: captured request rows

3. `browser_network_capture_stop`
   - Inputs: `session_id`, `clear=false`
   - Output: `stopped=true`, final counts

4. `browser_network_capture_status`
   - Inputs: `session_id`
   - Output: enabled flag, buffer usage, filters

## Captured row schema (v1)

- `request_id`
- `ts_start`, `ts_end`, `duration_ms`
- `url`, `method`
- `resource_type`
- `status`, `ok`
- `request_headers` (optional)
- `response_headers` (optional)
- `initiator`
- `from_cache`
- `failed`, `failure_text`

## Functional requirements

- Capture must include top-level navigation requests and subresources.
- Buffer is bounded and drops oldest entries when full.
- Tool calls must work in both launch and attach sessions.
- Capture should be opt-in to minimize overhead.

## Implementation notes

- Extend `BridgeBrowser` to register/unregister CDP network listeners.
- Add session-level capture state and ring buffer.
- Add serializer for headers and optional fields.
- Keep `browser_network_requests` unchanged for backward compatibility.

## Acceptance criteria

- Network capture includes requests missing from in-page hooks (for example script/image).
- Failed requests are visible with failure reason.
- `clear=true` semantics are consistent with console/network event tools.

## Test plan

- Integration fixture page loading multiple resource types and intentional failures.
- Buffer limit tests to verify truncation behavior.
- Attach-mode validation with external browser instance.

## Risks

- CDP event volumes can be high on heavy pages; memory controls are required.
- Event ordering and partial responses may require careful correlation by request ID.
