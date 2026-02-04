# Bifrost SDK Skills Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create user-level Claude Code skills (`bifrost:setup`, `bifrost:build`) and a SessionStart hook for automatic environment detection.

**Architecture:** A SessionStart hook detects environment state (source access, SDK installed, logged in, MCP configured) and exports variables. Two skills use these variables: `setup` guides installation/auth, `build` provides workflow/form/app creation guidance with context-aware debugging.

**Tech Stack:** Bash (hook script), Markdown with YAML frontmatter (skills), JSON (settings)

---

## Task 1: Create Hook Script

**Files:**
- Create: `~/.claude/hooks/bifrost-detect.sh`

**Step 1: Create the hooks directory**

```bash
mkdir -p ~/.claude/hooks
```

**Step 2: Write the detection hook script**

Create `~/.claude/hooks/bifrost-detect.sh`:

```bash
#!/bin/bash

# Bifrost environment detection hook for Claude Code
# Runs on SessionStart to detect SDK, auth, MCP, and source access

# Only run if CLAUDE_ENV_FILE is available (SessionStart only)
if [ -z "$CLAUDE_ENV_FILE" ]; then
  exit 0
fi

# Initialize all variables to false
BIFROST_HAS_SOURCE=false
BIFROST_SDK_INSTALLED=false
BIFROST_LOGGED_IN=false
BIFROST_MCP_CONFIGURED=false
BIFROST_DEV_URL=""
BIFROST_SOURCE_PATH=""

# 1. Detect Bifrost source code via file markers
# Check current directory and up to 5 parent directories
check_bifrost_source() {
  local dir="$1"
  local markers=0

  [ -f "$dir/api/shared/models.py" ] && markers=$((markers + 1))
  [ -f "$dir/docker-compose.dev.yml" ] && markers=$((markers + 1))
  [ -f "$dir/api/src/main.py" ] && markers=$((markers + 1))

  if [ $markers -ge 2 ]; then
    echo "$dir"
    return 0
  fi
  return 1
}

# Start from current directory
search_dir="$(pwd)"
for i in 1 2 3 4 5; do
  if result=$(check_bifrost_source "$search_dir"); then
    BIFROST_HAS_SOURCE=true
    BIFROST_SOURCE_PATH="$result"
    break
  fi
  parent="$(dirname "$search_dir")"
  [ "$parent" = "$search_dir" ] && break
  search_dir="$parent"
done

# 2. Check if bifrost CLI is installed
if command -v bifrost >/dev/null 2>&1; then
  BIFROST_SDK_INSTALLED=true
fi

# 3. Check for credentials file and extract URL
CREDS_FILE=""
if [ -f "$HOME/.bifrost/credentials.json" ]; then
  CREDS_FILE="$HOME/.bifrost/credentials.json"
elif [ -n "$APPDATA" ] && [ -f "$APPDATA/Bifrost/credentials.json" ]; then
  CREDS_FILE="$APPDATA/Bifrost/credentials.json"
fi

if [ -n "$CREDS_FILE" ]; then
  BIFROST_LOGGED_IN=true
  # Extract URL from credentials if jq is available
  if command -v jq >/dev/null 2>&1; then
    BIFROST_DEV_URL=$(jq -r '.url // .base_url // empty' "$CREDS_FILE" 2>/dev/null)
  fi
fi

# 4. Check if bifrost MCP server is configured
if command -v claude >/dev/null 2>&1; then
  if claude mcp list 2>/dev/null | grep -q "bifrost"; then
    BIFROST_MCP_CONFIGURED=true
  fi
fi

# Write all variables to CLAUDE_ENV_FILE
{
  echo "export BIFROST_HAS_SOURCE=$BIFROST_HAS_SOURCE"
  echo "export BIFROST_SDK_INSTALLED=$BIFROST_SDK_INSTALLED"
  echo "export BIFROST_LOGGED_IN=$BIFROST_LOGGED_IN"
  echo "export BIFROST_MCP_CONFIGURED=$BIFROST_MCP_CONFIGURED"
  [ -n "$BIFROST_DEV_URL" ] && echo "export BIFROST_DEV_URL=\"$BIFROST_DEV_URL\""
  [ -n "$BIFROST_SOURCE_PATH" ] && echo "export BIFROST_SOURCE_PATH=\"$BIFROST_SOURCE_PATH\""
} >> "$CLAUDE_ENV_FILE"

exit 0
```

**Step 3: Make the script executable**

```bash
chmod +x ~/.claude/hooks/bifrost-detect.sh
```

**Step 4: Test the hook script manually**

```bash
cd /home/jack/GitHub/bifrost
export CLAUDE_ENV_FILE=/tmp/test-env
~/.claude/hooks/bifrost-detect.sh
cat /tmp/test-env
rm /tmp/test-env
```

Expected output should show `BIFROST_HAS_SOURCE=true` and `BIFROST_SOURCE_PATH=/home/jack/GitHub/bifrost`.

**Step 5: Commit**

```bash
git add ~/.claude/hooks/bifrost-detect.sh
git commit -m "feat: add Bifrost environment detection hook"
```

---

## Task 2: Create Setup Skill

**Files:**
- Create: `~/.claude/skills/bifrost/setup.md`

**Step 1: Create the skills directory**

```bash
mkdir -p ~/.claude/skills/bifrost
```

**Step 2: Write the setup skill**

Create `~/.claude/skills/bifrost/setup.md`:

```markdown
---
name: setup
description: Set up Bifrost SDK - install CLI, authenticate, configure MCP server. Use when user needs to get started with Bifrost or has incomplete setup.
---

# Bifrost Setup

Guide the user through Bifrost SDK setup. Check environment variables to determine where to start.

## Current State

Check these environment variables (set by SessionStart hook):
- `BIFROST_SDK_INSTALLED`: !`echo $BIFROST_SDK_INSTALLED`
- `BIFROST_LOGGED_IN`: !`echo $BIFROST_LOGGED_IN`
- `BIFROST_MCP_CONFIGURED`: !`echo $BIFROST_MCP_CONFIGURED`

## Resume Logic

Based on the environment state:

1. **All true** → Setup complete! Inform user they're ready to use `/bifrost:build`
2. **SDK not installed** → Start at Step 1 (Python check)
3. **SDK installed but not logged in** → Start at Step 4 (Login)
4. **Logged in but MCP not configured** → Start at Step 5 (MCP config)

## Setup Steps

### Step 1: Check Python 3.11+

```bash
python3 --version
```

If Python < 3.11 or not installed, provide OS-specific guidance:

- **macOS**: `brew install python@3.11`
- **Ubuntu/Debian**: `sudo apt install python3.11 python3-pip`
- **Windows**: `winget install Python.Python.3.11` or download from python.org

### Step 2: Get Bifrost URL

Ask the user for their Bifrost instance URL. Examples:
- `https://app.gobifrost.com` (production)
- `https://dev.gobifrost.com` (development)
- `http://localhost:8000` (local development)

### Step 3: Validate and Install SDK

Test the URL is accessible, then install:

```bash
# Test URL (should return a wheel file)
curl -I {url}/api/cli/download

# Install SDK
pip install --force-reinstall {url}/api/cli/download
```

Verify installation:
```bash
bifrost --version
```

### Step 4: Login

```bash
bifrost login --url {url}
```

This opens a browser for authentication and saves credentials to `~/.bifrost/credentials.json`.

### Step 5: Configure MCP Server

First, check if a bifrost MCP server already exists:

```bash
claude mcp list
```

**If `bifrost` exists with a different URL:**
Ask user: "You have an existing Bifrost MCP server configured. Do you want to update it to point to {url}?"

- If yes: `claude mcp remove bifrost && claude mcp add bifrost --transport http --url "{url}/mcp"`
- If no: Skip this step

**If `bifrost` doesn't exist:**
```bash
claude mcp add bifrost --transport http --url "{url}/mcp"
```

### Step 6: Restart Required

Tell the user:

> Setup complete! Please restart Claude Code for the MCP server to take effect.
>
> After restarting, you can use `/bifrost:build` to create workflows, forms, and apps.

## Troubleshooting

### pip install fails
- Try `pip3` instead of `pip`
- Try `python3 -m pip install ...`
- Check if pip is installed: `pip --version`

### bifrost login hangs
- Check if URL is accessible in browser
- Try with `--no-browser` flag and copy the URL manually

### MCP not working after restart
- Verify with `claude mcp list`
- Check Claude Code logs for MCP connection errors
```

**Step 3: Commit**

```bash
git add ~/.claude/skills/bifrost/setup.md
git commit -m "feat: add bifrost:setup skill for SDK installation"
```

---

## Task 3: Create Build Skill

**Files:**
- Create: `~/.claude/skills/bifrost/build.md`

**Step 1: Write the build skill**

Create `~/.claude/skills/bifrost/build.md`:

```markdown
---
name: build
description: Build Bifrost workflows, forms, and apps using MCP tools. Use when user wants to create, debug, or modify Bifrost artifacts.
---

# Bifrost Build

Create and debug Bifrost artifacts using MCP tools.

## Prerequisites

Check setup status:
- SDK installed: !`echo $BIFROST_SDK_INSTALLED`
- Logged in: !`echo $BIFROST_LOGGED_IN`

**If either is false:** Direct user to run `/bifrost:setup` first.

## Environment Context

- Source access: !`echo $BIFROST_HAS_SOURCE`
- Source path: !`echo $BIFROST_SOURCE_PATH`
- Bifrost URL: !`echo $BIFROST_DEV_URL`

## Before Building

Clarify with the user:
1. **Which organization?** Use `list_organizations` to show options, or "global" for platform-wide
2. **What triggers this?** (webhook, form, schedule, manual)
3. **If webhook:** Get sample payload
4. **What integrations?** Use `list_integrations` to verify availability
5. **Error handling requirements?**

## MCP Tools Reference

### Discovery
- `list_workflows` - List workflows (filter by query, category, type)
- `get_workflow` - Get workflow metadata by ID or name
- `get_workflow_schema` - Workflow decorator documentation
- `get_sdk_schema` - Full SDK documentation
- `list_integrations` - Available integrations and auth status
- `list_forms` - List forms with URLs
- `get_form_schema` - Form structure documentation
- `list_apps` - List App Builder applications
- `get_app_schema` - App structure documentation

### Creation (Auto-Validating)
- `create_workflow` - Create workflow, tool, or data provider
- `create_form` - Create a form linked to a workflow
- `create_app` - Create an App Builder application

### Editing
- `list_content` - List files by entity type
- `search_content` - Search code patterns
- `read_content_lines` - Read specific lines
- `patch_content` - Surgical string replacement
- `replace_content` - Replace entire file

### Execution
- `execute_workflow` - Execute by workflow ID
- `list_executions` - List recent executions
- `get_execution` - Get execution details and logs

### Organization
- `list_organizations` - List all organizations
- `get_organization` - Get org details
- `list_tables` - List data tables

## Creation Workflow

1. **Understand the goal** - What does the user want to build?
2. **Read SDK docs** - Use `get_workflow_schema`, `get_sdk_schema` as needed
3. **Check integrations** - Verify required integrations exist with `list_integrations`
4. **Create artifact** - Use `create_workflow`, `create_form`, or `create_app`
5. **Test execution** - Use `execute_workflow` or access preview URL
6. **Check logs** - Use `get_execution` if issues arise
7. **Iterate** - Use `patch_content` or `replace_content` to fix issues

## Testing Requirements

### Workflows/Tools
1. Create via `create_workflow` (auto-validates)
2. Verify in `list_workflows`
3. Execute with sample data via `execute_workflow`
4. Verify result matches expectations

### Data Providers
1. Create via `create_workflow` with `type='data_provider'`
2. Execute via `execute_workflow`
3. Verify output is `[{"label": "...", "value": "..."}]` format

### Forms
1. Create via `create_form` (auto-validates)
2. Verify referenced workflow exists and works
3. Access at `{BIFROST_DEV_URL}/forms/{form_id}`

### Apps
1. Create via `create_app`
2. Preview at `{BIFROST_DEV_URL}/apps/{slug}/preview`
3. Only `publish_app` when user explicitly requests
4. Live at `{BIFROST_DEV_URL}/apps/{slug}` after publishing

## Debugging

### MCP-First Debugging
1. Check execution logs via `get_execution`
2. Verify integrations with `list_integrations`
3. Test workflows with `execute_workflow`
4. Inspect workflow metadata with `get_workflow`

### When Errors Suggest System Bugs

If an error appears to be a backend bug (not user error or doc issue):

**If `BIFROST_HAS_SOURCE=true`:**
> "This appears to be a backend bug ({error description}). I have access to the Bifrost source code at `{BIFROST_SOURCE_PATH}`. Would you like me to debug and fix this on the backend?"

**If `BIFROST_HAS_SOURCE=false`:**
> "This appears to be a backend bug ({error description}). Please report this to the platform team with these details: {error details}"

### Issue Categories
- **Documentation/Schema issue** → Note for recommendation, work around, continue
- **System bug** → Detect source access, offer to fix or escalate

## Code Standards

When writing workflow code:
- Production-quality with proper error handling
- Pythonic with type hints
- Docstrings explaining purpose and assumptions
- Follow SDK patterns from `get_sdk_schema`

## Session Summary

At end of session, provide:

```markdown
## Session Summary

### Completed
- [What was built/accomplished]

### System Bugs Fixed (if source available)
- [Bug] → [Fix] → [File]

### Documentation Recommendations
- [Tool/Schema]: [Issue] → [Recommendation]

### Notes for Future Sessions
- [Relevant context]
```
```

**Step 2: Commit**

```bash
git add ~/.claude/skills/bifrost/build.md
git commit -m "feat: add bifrost:build skill for artifact creation"
```

---

## Task 4: Register Hook in Settings

**Files:**
- Modify: `~/.claude/settings.json`

**Step 1: Read current settings**

```bash
cat ~/.claude/settings.json
```

**Step 2: Update settings to add hook registration**

The settings file needs the `hooks` section added. Merge with existing content:

```json
{
  "enabledPlugins": {
    "superpowers@claude-plugins-official": true
  },
  "statusLine": {
    "type": "command",
    "command": "npx -y ccstatusline@latest",
    "padding": 0
  },
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/bifrost-detect.sh"
          }
        ]
      }
    ]
  }
}
```

**Step 3: Validate JSON syntax**

```bash
cat ~/.claude/settings.json | jq .
```

Expected: Valid JSON output with no errors.

**Step 4: Commit**

```bash
git add ~/.claude/settings.json
git commit -m "feat: register Bifrost detection hook in settings"
```

---

## Task 5: Test Full Flow

**Step 1: Restart Claude Code**

Close and reopen Claude Code to trigger the SessionStart hook.

**Step 2: Verify environment variables are set**

In the new session:

```bash
echo "SOURCE: $BIFROST_HAS_SOURCE"
echo "SDK: $BIFROST_SDK_INSTALLED"
echo "LOGGED_IN: $BIFROST_LOGGED_IN"
echo "MCP: $BIFROST_MCP_CONFIGURED"
echo "URL: $BIFROST_DEV_URL"
echo "PATH: $BIFROST_SOURCE_PATH"
```

Expected (when in Bifrost repo):
- `BIFROST_HAS_SOURCE=true`
- `BIFROST_SOURCE_PATH=/home/jack/GitHub/bifrost`
- Other values depend on current setup state

**Step 3: Test setup skill invocation**

Run `/bifrost:setup` and verify:
- It detects current state from environment variables
- It provides appropriate guidance based on what's missing

**Step 4: Test build skill invocation**

Run `/bifrost:build` and verify:
- It checks prerequisites
- It shows environment context
- MCP tools are available and working

**Step 5: Test from non-Bifrost directory**

```bash
cd /tmp
```

Then restart Claude Code and verify `BIFROST_HAS_SOURCE=false`.

---

## Task 6: Remove Old Skill

**Files:**
- Delete: `/home/jack/GitHub/bifrost/.claude/skills/bifrost_vibecode_debugger/`

**Step 1: Verify new skills work**

Confirm Tasks 1-5 all passed before removing the old skill.

**Step 2: Remove the old skill directory**

```bash
rm -rf /home/jack/GitHub/bifrost/.claude/skills/bifrost_vibecode_debugger
```

**Step 3: Commit**

```bash
cd /home/jack/GitHub/bifrost
git add -A
git commit -m "chore: remove old bifrost_vibecode_debugger skill

Replaced by user-level skills at ~/.claude/skills/bifrost/"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Create hook script | `~/.claude/hooks/bifrost-detect.sh` |
| 2 | Create setup skill | `~/.claude/skills/bifrost/setup.md` |
| 3 | Create build skill | `~/.claude/skills/bifrost/build.md` |
| 4 | Register hook | `~/.claude/settings.json` |
| 5 | Test full flow | Manual verification |
| 6 | Remove old skill | `/home/jack/GitHub/bifrost/.claude/skills/bifrost_vibecode_debugger/` |
