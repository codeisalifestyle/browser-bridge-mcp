# PRD: Policy and Guardrails Layer

## Status

- Proposed
- Target phase: Phase 2

## Problem

The server currently executes all tools when requested, which is risky for shared environments or sensitive targets. Teams need enforceable constraints (domain boundaries and read-only operation) at runtime.

## Goals

- Add session-level policies that gate tool execution.
- Provide clear, machine-readable denial reasons.
- Keep defaults permissive to avoid breaking existing users.

## Non-goals

- No user auth/RBAC system in v1.
- No central policy server; policy remains session-local.

## Proposed MCP tools

1. `session_set_policy`
   - Inputs:
     - `session_id`
     - `allowed_domains: list[str] | null`
     - `blocked_domains: list[str] | null`
     - `read_only: bool`
     - `allow_evaluate: bool`
   - Output: normalized policy object

2. `session_get_policy`
   - Input: `session_id`
   - Output: active policy object

3. Optional `session_clear_policy`
   - Input: `session_id`
   - Output: reset confirmation

## Enforcement requirements

- `read_only=true` blocks mutating actions:
  - `browser_click`
  - `browser_type`
  - `browser_tab_close`
  - `browser_tab_new` (configurable; default blocked)
  - any future mutating tool
- `allow_evaluate=false` blocks `browser_evaluate`.
- `allowed_domains` restricts navigations and other cross-origin transitions.
- `blocked_domains` always denies even if allowlisted.
- Denials must include:
  - `allowed=false`
  - `reason_code` (for example `read_only_block`, `domain_not_allowed`)
  - `action`
  - `session_id`

## Implementation notes

- Add policy state to `BrowserSession` in `browser_bridge_mcp/runtime.py`.
- Add pre-action guard in `run_action` before operation execution.
- Add URL-domain extraction helper for navigate and tab actions.
- Ensure errors are safe for MCP client display.

## Acceptance criteria

- Policy can be set, retrieved, and enforced in the same session.
- Blocked actions return deterministic denial payloads.
- Allowed actions continue to work without behavior regressions.
- Policy behavior is consistent in launch and attach modes.

## Test plan

- Unit tests for domain matching (subdomains, ports, malformed URLs).
- Runtime tests verifying deny/allow paths per action category.
- Regression tests ensuring default policy does not alter existing behavior.

## Risks

- Overly strict domain matching can break legitimate redirects.
- Future tools may bypass policy if mutating classification is not maintained.
