---
name: browser-bridge-mcp-usage
description: Uses browser-bridge-mcp as the primary browser control channel for web scraping, deterministic automation development, debugging stale selectors or changed UI/API behavior, reproducing failures, and one-time browser execution tasks. Apply whenever the user or agent needs browser control.
---

# Browser Bridge MCP

## Purpose

Use this skill whenever browser control is needed. `browser-bridge-mcp` is the
default interface for:

1. developing deterministic automation scripts,
2. debugging broken or drifting automations,
3. running one-time browser tasks without script authoring.

This skill enforces an evidence-driven loop: inspect state, execute one action,
verify result, then codify.

## Invocation Policy

- Invoke `browser-bridge-mcp` anytime the user or agent requires browser control.
- Do not bypass MCP for ad-hoc browser operations when MCP tools can perform them.
- Treat MCP as the preferred path-discovery method before writing/updating scripts.

## Preflight: Installation and Environment Check

Run a quick preflight before browser actions:

1. Confirm MCP server availability and required tools are discoverable.
2. Confirm a browser session can be listed, started/attached, and stopped.
3. Confirm write targets exist for outputs (for example `/results`) when needed.
4. Confirm cookie/profile paths used by the task are accessible.

If any preflight check fails, report the blocker and stop before partial execution.

## Profile and Browser Config Management

`browser-bridge-mcp` owns runtime browser/session lifecycle and should be treated
as the source of truth for active automation state.

- Prefer attaching to intended existing sessions/profiles when continuity matters
  (authenticated workflows, user-context tasks).
- Prefer clean/new sessions for deterministic automation validation.
- Keep one active session per task unless parallelism is explicitly required.
- Persist or export cookies/storage only when the task requests it.
- Avoid cross-task state leakage: stop sessions created for the task when done.
- When auth-sensitive behavior differs, inspect cookies/storage/profile context
  before changing selectors or waits.

## Core Principles

- Keep browser work evidence-driven: observe before and after each action.
- Change one variable at a time (selector, wait, navigation, input payload).
- Prefer deterministic behavior over best-effort heuristics.
- Capture enough artifacts to explain and reproduce failures.
- Finish with script-level verification, not only manual MCP success.

## Primary MCP Workflow

1. Session lifecycle:
   - list sessions,
   - start or attach one session,
   - stop sessions when done.
2. Baseline state inspection:
   - URL/title,
   - DOM snapshot/query,
   - cookies/storage/profile context if auth-sensitive.
3. Single-step mutation:
   - navigate, click, type, scroll, evaluate.
4. Verification:
   - wait for URL/selector/text,
   - re-snapshot and confirm expected state transition.
5. Extraction:
   - gather structured output via evaluation or targeted queries.

## Tooling Guardrails

- Use `browser-bridge-mcp` tools as the default browser interface.
- When using Cursor `CallMcpTool`, pass parameters inside `arguments`.
- Keep one active session per task unless parallel sessions are explicitly needed.
- On completion, stop sessions created during the task to avoid orphan browsers.
- For script debugging, always run the script in terminal first to collect logs.

## Development Modes

### 1) New Automation Development

Use this when implementing a new flow or extending an existing flow.

1. Describe objective and translate it into browser-level milestones.
2. Use MCP browser control to iterate until the correct path is verified.
3. At each milestone, verify exact state transitions and capture evidence.
4. Repeat on edge cases until behavior is stable and reproducible.
5. Transcribe the successful path into deterministic script code.
6. Run the script from terminal and verify parity with MCP-observed behavior.

Expected output from the agent:
- deterministic function/script steps,
- explicit waits/assertions,
- structured extraction payload contract,
- verification notes.

### 2) Maintenance and Bug Fixing

Use this when existing automation breaks or drifts due to UI/API changes.

1. Describe objective and failing behavior.
2. Execute the failing script in terminal first.
3. Read logs/traces to isolate failing step and failure type.
4. Recreate script flow actions with MCP and iterate until correct path is verified.
5. Identify root cause (selector drift, timing, auth/session, changed endpoint, etc.).
6. Update the script with a deterministic fix.
7. Re-run script end-to-end and verify expected output.

Expected output from the agent:
- concise root-cause statement,
- code fix with rationale,
- verification run results,
- residual risks or follow-up tests.

## One-Time Tasks (No Script Development)

Use this mode for direct browser task execution by the agent without building a
new automation script.

Process:
1. Confirm objective and output format/location.
2. Run preflight checks.
3. Execute via MCP actions with stepwise verification.
4. Produce requested artifacts and confirm completion.
5. Stop any sessions created for the task.

Examples:
- Open main browser session and save cookies for X.com, Instagram, and LinkedIn
  to the default cookies location.
- Open a target website, collect the latest 10 articles, and write structured
  article datapoints as JSON in `/results`.

## Deterministic Automation Checklist

- Entry state is validated (URL/auth/session preconditions).
- Selectors are stable and specific (avoid fragile generated classes).
- Every state-changing action has explicit post-conditions.
- Waits are condition-based when possible (URL/selector/text/network-idle).
- Error handling is explicit (timeout, missing element, unexpected redirects).
- Output schema is structured and consistent across runs.
- Session cleanup is handled so no stale browser sessions remain.

## Recommended Feedback Loop

For each suspect step:

1. Inspect (`url` + snapshot/query + relevant session/profile context).
2. Execute one action.
3. Verify expected change.
4. If mismatch, capture evidence and adjust only one thing.
5. Repeat until stable, then codify (or complete one-time task output).
