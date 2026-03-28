---
name: bifrost-setup
description: Set up or verify a Bifrost development environment. Use when checking whether local source, CLI access, credentials, and optional MCP access are available; when installing the `bifrost` CLI; when logging in to a Bifrost instance; or when deciding whether SDK-first development is possible on the current machine.
---

# Bifrost Setup

Establish whether the machine can do Bifrost work through local source and the CLI before assuming any SDK-first workflow.

Treat the upstream-supported setup flow as the default contract. If this fork uses extra conveniences or shortcuts, keep them clearly marked as fork-local.

## Workflow

1. Detect current state first.
   - Check whether the current directory is inside a Bifrost source tree.
   - Check whether the `bifrost` CLI is installed.
   - Check whether credentials already exist in `~/.bifrost/credentials.json`.
   - Check whether a usable Python 3.11+ and install path are available.

2. If source, CLI, and credentials already exist, stop early.
   - Tell the user SDK-first development is available.
   - Only discuss MCP setup if the user explicitly needs MCP-only tools or Claude-specific configuration.

3. If CLI is missing, install it from the user's Bifrost instance.
   - Ask for the instance URL only if it cannot be discovered from existing credentials.
   - Prefer `pipx` when available; otherwise fall back to `python -m pip`.

4. If credentials are missing, run `bifrost login --url <instance>`.
   - Treat login as the critical step for local CLI and API access.

5. Distinguish Codex setup from Claude-only setup.
   - Codex does not need Claude MCP configuration to work on the repo.
   - Claude MCP configuration is optional and should be described as such.

## Rules

- Do not assume MCP is required for Bifrost development.
- Do not suggest placeholder Bifrost URLs if the user needs a real instance URL.
- Prefer quick environment checks over long setup instructions.
- Prefer repo-local source + CLI workflows over remote-only guidance when both are available.

## Reference

Read [references/bifrost-setup-checklist.md](./references/bifrost-setup-checklist.md) for the exact checks, install commands, and repo-specific setup boundaries.
