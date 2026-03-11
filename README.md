# browser-bridge-mcp

MCP browser bridge that gives AI clients full access to a live browser environment.

The core model is simple: your AI can either create a new browser session or attach to an existing one. That makes this ideal for autonomous web automation development and testing workflows. Under the hood, it uses `nodriver` as the browser automation runtime.

## MCP in 30 seconds

- **MCP (Model Context Protocol)** is a standard for giving AI clients access to tools.
- **This repo is an MCP server** that exposes browser automation tools.
- **Your AI client runs it as a command** (usually over `stdio` transport).

## Why integrate this into your AI client

- **Launch or attach sessions**: start a clean browser session with `session_start` or connect to an existing browser with `session_attach`.
- **Full browser control**: navigate, click, type, scroll, evaluate scripts, inspect DOM/HTML, and take screenshots.
- **Built for autonomous workflows**: useful for end-to-end automation building, regression checks, and web task execution loops.
- **Better observability for agents**: capture console logs and network request metadata while the agent acts.
- **Session-aware automation**: isolated session lifecycle (`start`, `list`, `get`, `stop`) and per-session action locking.

## Quick Start (recommended)

### 1) Install prerequisites

- Python `>=3.10,<3.14` (Python `3.14` is currently not supported due to an upstream `nodriver` issue)
- A Chromium-based browser installed (Chrome or Edge)
- Optional but recommended: `pipx` (for easy isolated CLI installs)

Install `pipx` (optional, recommended) on macOS:

```bash
brew install pipx
pipx ensurepath
```

Install `pipx` (optional, recommended) on Linux:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```

Install `pipx` (optional, recommended) on Windows (PowerShell):

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
```

### 2) Install `browser-bridge-mcp`

Option A (recommended): install with `pipx`

```bash
pipx install "git+https://github.com/codeisalifestyle/browser-bridge-mcp.git"
```

Option B (no `pipx`): install in a dedicated virtual environment

```bash
python3 -m venv ~/.venvs/browser-bridge-mcp
source ~/.venvs/browser-bridge-mcp/bin/activate
pip install "git+https://github.com/codeisalifestyle/browser-bridge-mcp.git"
```

Verify:

```bash
browser-bridge-mcp --help
```

### 3) Add it to your MCP client

Most MCP-enabled clients accept a config shaped like this:

```json
{
  "mcpServers": {
    "browser-bridge-mcp": {
      "command": "browser-bridge-mcp",
      "args": ["--transport", "stdio"]
    }
  }
}
```

If your client cannot find the command, use an absolute path:

```bash
# macOS / Linux
which browser-bridge-mcp

# Windows (PowerShell)
where.exe browser-bridge-mcp
```

Then set `"command"` to that full path.

If you used Option B, your command path is typically:

```bash
~/.venvs/browser-bridge-mcp/bin/browser-bridge-mcp
```

### 4) First-use test in your AI client

After reloading/restarting your AI client, ask it:

1. "Call `session_start` with default settings."
2. "Call `browser_navigate` to `https://example.com`."
3. "Call `browser_snapshot`."
4. "Call `session_stop`."

If these succeed, installation is complete.

## Alternative: local dev install (for contributors)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
browser-bridge-mcp --transport stdio
```

Client config for this mode:

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

## Core tools exposed

### Session lifecycle

- `session_start`
- `session_attach`
- `session_list`
- `session_get`
- `session_set_policy`
- `session_get_policy`
- `session_set_download_dir`
- `session_stop`
- `session_stop_all`

### Browser actions

- `browser_url`
- `browser_navigate`
- `browser_back`
- `browser_forward`
- `browser_reload`
- `browser_tab_list`
- `browser_tab_new`
- `browser_tab_switch`
- `browser_tab_close`
- `browser_tab_current`
- `browser_snapshot`
- `browser_query`
- `browser_click`
- `browser_type`
- `browser_handle_dialog`
- `browser_set_file_input`
- `browser_scroll`
- `browser_wait`
- `browser_wait_for_selector`
- `browser_wait_for_url`
- `browser_wait_for_text`
- `browser_wait_for_function`
- `browser_wait_for_network_idle`
- `browser_html`
- `browser_console_messages`
- `browser_network_requests`
- `browser_network_capture_start`
- `browser_network_capture_get`
- `browser_network_capture_stop`
- `browser_network_capture_status`
- `browser_downloads`
- `browser_cookies_get`
- `browser_cookies_set`
- `browser_cookies_save`
- `browser_cookies_clear`
- `browser_storage_get`
- `browser_storage_set`
- `browser_storage_clear`
- `browser_take_screenshot`
- `browser_evaluate`

## Product planning docs

- Roadmap: `docs/roadmap.md`
- Navigation helpers: completed (PRD removed)
- Advanced wait primitives: completed (PRD removed)
- Tab management: completed (PRD removed)
- Policy and guardrails: completed (PRD removed)
- Dialog/upload/download: completed (PRD removed)
- Cookie/storage management: completed (PRD removed)
- CDP network capture: completed (PRD removed)
- PRD (session trace + replay): `docs/prd-session-trace-replay.md`

## Typical flow

1. Start or attach a session (`session_start` or `session_attach`).
2. Use browser tools to automate and inspect state.
3. Stop the session (`session_stop`) when done.

## Troubleshooting

- **"command not found: browser-bridge-mcp"**
  - Run `pipx ensurepath`, restart terminal and AI client, then retry.
  - Use absolute command path from `which browser-bridge-mcp`.
- **Python 3.14 errors**
  - Use Python 3.13 or lower.
- **Browser fails to launch in restricted environments**
  - Try `session_start` with `sandbox=false`.
- **MCP client does not show tools**
  - Confirm JSON syntax is valid.
  - Confirm transport is `stdio`.
  - Fully restart the AI client after editing MCP config.

## Run server manually

### stdio transport (recommended for local MCP clients)

```bash
browser-bridge-mcp --transport stdio
```

### streamable-http transport

```bash
browser-bridge-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

## Safety notes

- Use this only on sites and accounts where you are authorized.
- Respect website Terms of Service and local regulations.
- Be cautious with high-frequency automation.
