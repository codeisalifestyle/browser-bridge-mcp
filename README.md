# browser-bridge-mcp — moved

> **This repository has been merged into [`nodriver-reforged`](https://github.com/codeisalifestyle/nodriver-reforged).**
>
> Active development continues under [`packages/browser-bridge-mcp/`](https://github.com/codeisalifestyle/nodriver-reforged/tree/main/packages/browser-bridge-mcp) of the monorepo. This standalone repo is archived and will receive no further updates.

## Why the move

`browser-bridge-mcp` is a wrapper around `nodriver-reforged`. Maintaining the two as separate repos meant every cross-cutting fix needed:

1. a PR on `nodriver-reforged`,
2. a release/tag,
3. a pin bump on `browser-bridge-mcp`.

In the new monorepo the engine and the MCP live as sibling packages in a `uv` workspace, so a single commit covers both.

## Update your install

If you previously installed from this repo:

```bash
pip install "git+https://github.com/codeisalifestyle/browser-bridge-mcp.git"
```

…switch to the new subdirectory install:

```bash
pip install "git+https://github.com/codeisalifestyle/nodriver-reforged.git#subdirectory=packages/browser-bridge-mcp"
```

The package name (`browser-bridge-mcp`), import path (`browser_bridge_mcp`), and CLI entry point (`browser-bridge-mcp`) are all unchanged.

## Recovering the pre-merge state

The exact pre-migration tip is preserved here as the `pre-monorepo` tag and is available as a starting point for forks:

```bash
git checkout pre-monorepo
```
