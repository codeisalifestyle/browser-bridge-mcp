# browser-bridge-mcp

🚀 MCP server that gives AI clients full access to a live Chromium browser environment.

Your AI client can intelligently create a new browser session or attach to an existing system Chromium instance. It is built for autonomous automation, developer workflows, and production-style browser operations, powered by `nodriver-reforged`.

## Demo Video

[Watch demo video](https://gumlet.tv/watch/69c5aa1eb365493ac0849b50/)

## 🌟 Product Highlights

`browser-bridge-mcp` turns browser automation into a reliable MCP service your agents can trust in real workflows, not just demos.

### 🧠 Intelligent Chromium orchestration

- Launch fresh sessions instantly with `session_start`, or attach to existing system Chromium instances with `session_attach`.
- Connect the way your environment requires: host/port, websocket URL, or saved state file.
- Run with confidence using robust session lifecycle controls (`start`, `list`, `get`, `stop`, `stop_all`) and per-session action locking.
- Keep long-running workflows alive by reconnecting and continuing work instead of restarting from zero.

### 🤖 Built for autonomous agents and fast-moving teams

- Give agents deterministic control over navigate/query/click/type/wait/evaluate/screenshot flows.
- Ship faster with first-class support for E2E prototyping, scraping pipelines, regression checks, and interactive debugging.
- Get live operational visibility with console output, request metadata, and CDP-level network capture.
- Reduce flaky runs and shorten feedback loops across development and QA.

### 👤 Durable browser identity and session state

- Centralize reusable browser state under one roof: `profiles/`, `cookies/`, and `configs/`.
- Start sessions with profile-aware defaults, account aliases, and cookie jars built in.
- Fine-tune launch behavior with configurable browser flags, executable paths, headless/sandbox settings, and proxy-ready arguments.
- Preserve realistic, persistent browser identity across sessions for multi-account and high-continuity automation.

### 🕵️ Stealth foundation with nodriver-reforged + CDP

- Powered by `nodriver-reforged`: a maintained no-WebDriver/no-Selenium Chromium automation runtime.
- Includes anti-bot oriented capabilities, including Cloudflare Turnstile solving through `browser_solve_cloudflare`.
- Built on direct CDP control for low-level precision, observability, and flexibility.
- Better suited for modern websites where reliability under anti-automation pressure matters.

## Quick Start (recommended)

### 1) Install prerequisites

- Python `>=3.10` (Python `3.14+` is supported with the latest `nodriver-reforged`)
- A Chromium-based browser installed (Chrome, Brave or Edge)
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

## Choosing a launch mode

`browser-bridge-mcp` exposes six well-defined launch recipes. Always pick one
explicitly before calling `session_start` or `session_attach`. The MCP itself
returns the same catalog at runtime via `session_launch_modes`.

The MCP **always spawns a brand-new browser process**. It never attaches to or
takes over the user's currently running browser. When given an external
`user_data_dir`, the runtime first clones the auth-critical files into an
ephemeral location using `clone_strategy` (default `auth_only`), so the user's
live browser is never touched.

| Mode | Tool | When to use | Example args |
| --- | --- | --- | --- |
| `ephemeral_fresh` | `session_start` | Fresh isolated browser, no identity. Default for scraping/E2E. | `{}` |
| `headless_scrape` | `session_start` | Background scraping in CI / no UI. | `{ "headless": true }` |
| `managed_profile` | `session_start` | Reusable persistent identity stored in the state root. | `{ "profile": "twitter_main" }` |
| `live_profile_clone` | `session_start` | Spawn a NEW browser with the user's REAL logged-in identity. Auto-clones any external `user_data_dir`. Default `clone_strategy=auth_only` is sub-second and cross-platform. | `{ "user_data_dir": "~/Library/Application Support/Google/Chrome", "browser_executable_path": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" }` |
| `attach_existing_with_new_tab` | `session_attach` | Advanced. The user manually launched a browser with `--remote-debugging-port`. | `{ "host": "127.0.0.1", "port": 9222 }` |
| `attach_existing_take_over` | `session_attach` | Advanced. Explicitly drive the user's foreground tab. | `{ "host": "127.0.0.1", "port": 9222, "new_tab": false }` |

### `clone_strategy` for `live_profile_clone`

| Strategy | Platform | Cost | Fidelity | Notes |
| --- | --- | --- | --- | --- |
| `auth_only` (default) | macOS / Windows / Linux | sub-second, tens of MB | Cookies, Login Data, Preferences. No extensions/history. | Uses SQLite online backup, so it's safe even when the source browser is open. Recommended for almost all flows. |
| `cow` | macOS only (APFS) | near-instant, near-zero disk | Full profile incl. extensions | Uses `cp -Rc` (copy-on-write clonefile). Falls back to `auth_only` on non-Darwin or non-APFS volumes. |
| `full` | All | slow (GBs) | Full profile | Legacy `shutil.copytree`. Escape hatch only. |

Common gotchas avoided by these recipes:

- Multi-GB profile copies on every session start — fixed: `auth_only` is now the default `clone_strategy`, copying only the small files needed for authentication.
- Source browser locking the cookie SQLite while we read it — fixed: `auth_only` uses SQLite's online backup API, which co-exists safely with the running browser.
- Stale `SingletonLock` carried over from a CoW clone causing "profile in use" — fixed: cloned profiles have `SingletonLock`, `SingletonCookie`, and `SingletonSocket` stripped before launch.
- Multiple windows opening when launching with `--profile-directory` but no `user_data_dir` — fixed: the flag is now only appended when an explicit `user_data_dir` is in play.
- The MCP "hijacking" the user's foreground tab on attach — fixed: `session_attach` defaults to opening a fresh blank tab. Pass `new_tab=false` only when you want the legacy take-over behavior.
- `browser_cookies_set` mid-session navigating the page to `about:blank` — fixed: the helper no longer navigates by default. Cookie application during initial session startup still navigates first to ensure the page state is clean.
- Lingering Chromium processes after `session_stop` — fixed: the close path now waits on `browser.stopped()` and unconditionally cleans up any ephemeral cloned `user_data_dir`.

Use `session_preflight` to debug failures before opening a session:

```jsonc
// AI client invocation
{
  "tool": "session_preflight",
  "arguments": {
    "host": "127.0.0.1",
    "port": 9222,
    "browser_executable_path": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "user_data_dir": "~/Library/Application Support/Google/Chrome"
  }
}
```

It returns: detected Chromium binaries on the host, whether `nodriver` imports cleanly, whether the optional DevTools endpoint is reachable, and whether the optional `user_data_dir` exists / looks locked by another browser.

## Centralized browser state store

`browser-bridge-mcp` now keeps reusable browser state in one place:

- Default root: `~/.browser-bridge-mcp`
- Override with env var: `BROWSER_BRIDGE_MCP_HOME=/custom/path`
- Override per server run: `browser-bridge-mcp --state-root /custom/path`

Within that root:

- `profiles/` stores persistent Chromium profile directories (user data dirs)
- `cookies/` stores reusable cookie jar JSON files
- `configs/` stores launch configs used by `session_start`

`session_start` supports optional `profile`, `cookie_name`, and `launch_config` inputs.
It resolves launch settings in this order:

1. Built-in defaults
2. Saved default launch config (`configs/default.json`)
3. Profile-linked launch config (if profile defines one)
4. Selected `launch_config` (if provided)
5. Profile `launch_overrides`
6. Explicit `session_start` arguments

This lets your AI client map account-oriented tasks to stable browser identities (profile + cookies + launch settings) without repeatedly passing raw paths.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pytest -q
browser-bridge-mcp --transport stdio
```

Client config for this mode:

```json
{
  "mcpServers": {
    "browser-bridge-mcp": {
      "command": "/absolute/path/to/browser-bridge-mcp",
      "args": ["--transport", "stdio"]
    }
  }
}
```

## Core tools exposed

### Session lifecycle

- `session_start`
- `session_attach`
- `session_launch_modes`
- `session_preflight`
- `session_list`
- `session_get`
- `session_state_paths`
- `session_profile_list`
- `session_profile_get`
- `session_profile_set`
- `session_profile_delete`
- `session_launch_config_list`
- `session_launch_config_get`
- `session_launch_config_set`
- `session_launch_config_delete`
- `session_cookie_jar_list`
- `session_set_policy`
- `session_get_policy`
- `session_set_download_dir`
- `session_trace_start`
- `session_trace_stop`
- `session_trace_get`
- `session_trace_export`
- `session_trace_replay`
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

## Project docs

- Architecture: `docs/architecture.md`

## SKILL FILE

- Skill: `skills/browser-bridge-mcp-usage/SKILL.md`

## Troubleshooting

- **"command not found: browser-bridge-mcp"**
  - Run `pipx ensurepath`, restart terminal and AI client, then retry.
  - Use absolute command path from `which browser-bridge-mcp`.
- **Python version mismatch**
  - Use a supported Python (`>=3.10`) and reinstall/upgrade the package in your MCP environment.
- **Browser fails to launch in restricted environments**
  - Try `session_start` with `sandbox=false`.
- **MCP client does not show tools**
  - Confirm JSON syntax is valid.
  - Confirm transport is `stdio`.
  - Fully restart the AI client after editing MCP config.

## Safety notes

- Use this only on sites and accounts where you are authorized.
- Respect website Terms of Service and local regulations.
- Be cautious with high-frequency automation.

