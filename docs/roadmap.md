# Product Roadmap

This roadmap turns the proposed feature set into a delivery plan that balances quick user value with foundational work.

## Guiding principles

- Keep tools composable and MCP-friendly (small, explicit actions).
- Preserve current simplicity of `session_*` + `browser_*` mental model.
- Prioritize reliability and debuggability over raw feature count.
- Ship in slices that can be tested end-to-end from an MCP client.

## Prioritized roadmap

### Phase 1: Fast wins (1-2 weeks)

1. Navigation helpers (completed)
   - Add `browser_back`, `browser_forward`, `browser_reload`.
   - Value: immediate usability for agent loops.
   - Completed with tests; PRD removed per completion workflow.

2. Advanced wait primitives (completed)
   - Add waits for URL, text, function predicate, and network-idle.
   - Value: reduces flaky automation and retry loops.
   - Completed with tests; PRD removed per completion workflow.

3. Explicit tab management (completed)
   - Add list/new/switch/close tab tools.
   - Value: required for multi-tab workflows and popups.
   - Completed with tests; PRD removed per completion workflow.

### Phase 2: Safety + workflow coverage (2-4 weeks)

4. Policy and guardrails (completed)
   - Domain allowlist/blocklist and read-only mode.
   - Value: safer automation in shared or production-like contexts.
   - Completed with tests; PRD removed per completion workflow.

5. Dialog, upload, and download support (completed)
   - Handle alerts/prompts, file inputs, and download tracking.
   - Value: unlocks common real-world test flows.
   - Completed with tests; PRD removed per completion workflow.

6. Cookie and storage management
   - First-class cookie/localStorage/sessionStorage tools.
   - Value: repeatable login/bootstrap state without brittle scripts.
   - PRD: `docs/prd-cookie-storage-management.md`

### Phase 3: Deep observability (3-5 weeks)

7. CDP-level network capture
   - Capture request/response metadata from browser protocol events.
   - Value: richer diagnostics than in-page fetch/xhr hooks.
   - PRD: `docs/prd-network-cdp-capture.md`

### Phase 4: Reproducibility platform (4-6 weeks)

8. Session trace recording and replay
   - Persist action timeline, artifacts, and replay flows.
   - Value: deterministic regression and debugging workflows.
   - PRD: `docs/prd-session-trace-replay.md`

## Dependency map

- Tab management should land before trace/replay (trace should include active tab context).
- Wait primitives should land before replay (replay requires robust waiting semantics).
- Policy guardrails should gate risky tools before broader workflow tooling.
- CDP network capture should precede advanced trace exports that include network artifacts.

## Exit criteria by phase

- Phase 1 complete when new tools are documented in `README.md` and covered by integration tests.
- Phase 2 complete when policy enforcement and file/dialog flows are stable in both launch and attach modes.
- Phase 3 complete when CDP capture is memory-bounded and queryable via MCP tools.
- Phase 4 complete when trace files can be replayed with deterministic step outcomes and clear failure reporting.
