# PRD: Dialog, Upload, and Download Support

## Status

- Proposed
- Target phase: Phase 2

## Problem

Many test and automation scenarios require handling native dialogs, uploading files, and validating downloads. These flows are not first-class today, forcing brittle workarounds.

## Goals

- Provide predictable dialog control for confirm/prompt/alert flows.
- Enable file input uploads through explicit tools.
- Expose download event visibility and metadata.

## Non-goals

- No anti-captcha or file chooser UI automation outside standard file inputs.
- No antivirus/content scanning of downloaded files.

## Proposed MCP tools

1. `browser_handle_dialog`
   - Inputs: `session_id`, `accept=true`, `prompt_text: str | null`, `once=true`
   - Output: configured handler state

2. `browser_set_file_input`
   - Inputs: `session_id`, `selector`, `file_paths: list[str]`, `wait_seconds=1.2`
   - Output: `selector`, `files_set_count`, `url`, `title`

3. `browser_downloads`
   - Inputs: `session_id`, `limit=100`, `clear=false`
   - Output: download rows with path/url/status/timestamps

4. `session_set_download_dir` (optional if not part of `session_start`)
   - Inputs: `session_id`, `download_dir`
   - Output: configured path

## Functional requirements

- Dialog handling should support both one-shot and persistent modes.
- If no handler is configured, default behavior should be explicit and documented.
- File input tool must validate that all provided paths exist before action.
- Download tracking should be memory-bounded and clearable.

## Implementation notes

- Extend `BridgeBrowser` with dialog event hook and upload helper.
- Introduce download observer buffer (similar to console/network event buffers).
- Normalize file paths to absolute expanded paths in output.
- Surface clear errors for unsupported upload elements.

## Acceptance criteria

- Prompt flow can submit custom text and continue execution.
- File input receives selected files and form submission succeeds.
- Download metadata is retrievable after a known download trigger.

## Test plan

- Integration page with `alert`, `confirm`, and `prompt` controls.
- Upload test using temporary files and multipart form endpoint.
- Download test verifying recorded metadata and on-disk file existence.

## Risks

- Browser-specific download behavior may vary by OS and sandbox mode.
- Dialog interception timing may race if handler is configured too late.
