# Architecture

`browser-bridge-mcp` is split into four layers:

1. `browser_bridge_mcp/browser.py`
   - Nodriver adapter.
   - Launch mode (owns browser process) and attach mode (connect to existing debugger endpoint).

2. `browser_bridge_mcp/actions.py`
   - Stateless action primitives:
     - navigate, query, click, type, scroll, wait, html, screenshot
   - In-page observers for console and fetch/xhr metadata.
   - Runtime payload normalization for nodriver evaluate responses.

3. `browser_bridge_mcp/runtime.py`
   - Session lifecycle and state:
     - start, attach, list, get, stop
   - Per-session action locking.
   - Connection resolution from host/port, ws URL, or state file.

4. `browser_bridge_mcp/server.py`
   - FastMCP tool surface for MCP clients.
   - Lifecycle cleanup hook that closes all sessions on shutdown.

## Capability highlights

- Explicit tab management (`browser_tab_*`).
- CDP-level network capture tools.
- Policy layer (domain allowlist/blocklist, read-only mode).
- Session trace recording and replay.
