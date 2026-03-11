# PRD: Explicit Tab Management

## Status

- Proposed
- Target phase: Phase 1

## Problem

The runtime currently assumes a single active tab (`browser.main_tab`). Real workflows often open new tabs/windows and require explicit control to avoid acting on the wrong page.

## Goals

- Introduce first-class tab lifecycle tools.
- Make active tab state explicit and queryable.
- Preserve backwards compatibility for existing single-tab flows.

## Non-goals

- No cross-browser window tiling or visual window management.
- No iframe-level tab abstraction (iframe support remains out of scope).

## Proposed MCP tools

1. `browser_tab_list`
   - Input: `session_id`
   - Output: `tabs[]` with `tab_id`, `url`, `title`, `active`

2. `browser_tab_new`
   - Input: `session_id`, `url="about:blank"`, `switch=true`, `wait_seconds=1.2`
   - Output: created `tab_id`, `url`, `title`, `active`

3. `browser_tab_switch`
   - Input: `session_id`, one of `tab_id` or `index`, `wait_seconds=0.4`
   - Output: active tab summary

4. `browser_tab_close`
   - Input: `session_id`, one of `tab_id` or `index`, `switch_to="last_active"`
   - Output: `closed_tab_id`, `new_active_tab_id`

5. `browser_tab_current`
   - Input: `session_id`
   - Output: `tab_id`, `url`, `title`

## Functional requirements

- Every browser action should execute against the current active tab.
- Tab identifiers must remain stable within a session.
- Closing the active tab should move focus to a deterministic fallback tab.
- If the last tab closes unexpectedly, return a clear error requiring session restart or new tab creation.

## Implementation notes

- Extend `BridgeBrowser` to track and switch `self.tab`.
- Add tab enumeration/mapping utilities and active tab metadata.
- Ensure observer scripts are installed on newly created tabs.
- Update runtime session summary to optionally include active tab info.

## Acceptance criteria

- Agent can open, switch, interact, and close tabs without ambiguity.
- Existing tools (click/type/query/snapshot/evaluate) target switched tab correctly.
- `browser_tab_list` reflects current active tab after each switch.

## Test plan

- Integration test with two tabs and cross-tab navigation/assertions.
- Regression tests ensuring single-tab workflows are unchanged.
- Attach-mode tests for tab list/switch behavior against an existing browser.

## Risks

- Nodriver tab identifiers may be unstable across reconnects in attach mode.
- New tab events might race with script injection if not synchronized.
