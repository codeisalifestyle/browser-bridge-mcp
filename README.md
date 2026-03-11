# browser-bridge-mcp

Stealth-capable browser bridge MCP server for custom `nodriver` instances.

This project lets MCP-enabled AI clients control either:

- a browser session launched by the MCP server, or
- an already running browser (attach mode via host/port, ws URL, or state file).

It is designed for automation development workflows where you need:

- persistent browser profiles,
- stealth-oriented runtime behavior,
- agentic inspection and control (DOM/query/click/type/scroll/html),
- quick observability (captured console and fetch/xhr network metadata).

## Features

- `session_start` / `session_attach` lifecycle
- Session isolation and per-session action locking
- Browser tools:
  - `browser_url`
  - `browser_navigate`
  - `browser_snapshot`
  - `browser_query`
  - `browser_click`
  - `browser_type`
  - `browser_scroll`
  - `browser_wait`
  - `browser_wait_for_selector`
  - `browser_html`
  - `browser_console_messages`
  - `browser_network_requests`
  - `browser_take_screenshot`
  - `browser_evaluate`

## Installation

Python `>=3.10,<3.14` (Python `3.14` is currently not supported due to an upstream `nodriver` issue).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run Server

### stdio transport (recommended for local MCP clients)

```bash
browser-bridge-mcp --transport stdio
```

### streamable-http transport

```bash
browser-bridge-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

## MCP Client Config Example

```json
{
  "mcpServers": {
    "browser-bridge-mcp": {
      "command": "/absolute/path/to/.venv/bin/browser-bridge-mcp",
      "args": ["--transport", "stdio"],
      "cwd": "/absolute/path/to/browser-bridge-mcp"
    }
  }
}
```

## Typical Flow

1. Call `session_start` (or `session_attach`).
2. Use browser tools to navigate and inspect state.
3. Call `session_stop` when done.

## Safety Notes

- Use this only on sites and accounts where you are authorized.
- Respect website Terms of Service and local regulations.
- Be cautious with high-frequency automation.
