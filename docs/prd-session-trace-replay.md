# PRD: Session Trace Recording and Replay

## Status

- Proposed
- Target phase: Phase 4

## Problem

When an agent flow fails, reproducing it is difficult without a structured execution log. Teams need deterministic traces that can be replayed for regression and debugging.

## Goals

- Record structured action traces for each session.
- Export traces as JSON for storage and CI artifacts.
- Replay traces with deterministic step reporting and clear failure boundaries.

## Non-goals

- No natural-language test generation from traces in v1.
- No visual timeline UI in v1.

## Proposed MCP tools

1. `session_trace_start`
   - Inputs:
     - `session_id`
     - `trace_id: str | null`
     - `capture_screenshot_on_error=true`
     - `capture_html_on_error=false`
   - Output: `trace_id`, `started=true`

2. `session_trace_stop`
   - Input: `session_id`
   - Output: final stats (`steps`, `errors`, `started_at`, `stopped_at`)

3. `session_trace_get`
   - Inputs: `session_id`, `limit=200`, `offset=0`
   - Output: trace events page

4. `session_trace_export`
   - Inputs: `session_id`, `output_path`
   - Output: `path`, `event_count`, checksum

5. `session_trace_replay`
   - Inputs:
     - `trace_path`
     - `session_id: str | null` (optional existing session)
     - `stop_on_error=true`
     - `dry_run=false`
   - Output: replay summary with per-step outcomes

## Trace event schema

- `index`
- `timestamp`
- `action`
- `inputs` (sanitized)
- `result` (sanitized)
- `url_before`, `url_after`
- `title_before`, `title_after`
- `duration_ms`
- `error` (optional)
- `artifacts` (optional screenshot/html paths)

## Functional requirements

- Recording should hook into `run_action` to capture all tool calls consistently.
- Inputs/results must be sanitized (for example mask obvious secrets in typed text).
- Replay should support dry-run validation of tool availability and schema shape.
- Replay summary must include deterministic pass/fail counts and first failure index.

## Implementation notes

- Add trace state to `BrowserSession` and append events in runtime wrapper.
- Implement artifact capture through existing screenshot/html actions on error paths.
- Add JSON trace serializer with versioned schema (`trace_version`).
- Keep replay executor strict: fail fast on unsupported/unknown actions unless `dry_run`.

## Acceptance criteria

- A recorded trace can be exported and replayed on a fresh session.
- Replay returns step-level statuses and clear failure diagnostics.
- Sensitive typed data is masked in stored trace payloads.

## Test plan

- Integration scenario: multi-step form flow with one intentional failure.
- Replay test in both stop-on-error and continue-on-error modes.
- Schema compatibility test for exported trace files.

## Risks

- Non-deterministic pages can cause replay divergence; waits and retries are critical.
- Trace payload growth can be large with artifacts; retention strategy is required.
