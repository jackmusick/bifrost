# Bifrost Setup Checklist

## Environment Checks

### Detect local source

Look for at least two of these markers near the current directory:

- `api/src/main.py`
- `docker-compose.dev.yml`
- `api/shared/models.py` in older guidance or `shared/` in the current fork

In this repo, practical markers are:

- `api/src/main.py`
- `shared/`
- `docker-compose*.yml`

### Detect CLI

```bash
command -v bifrost
```

### Detect credentials

```bash
test -f "$HOME/.bifrost/credentials.json" && echo present || echo missing
```

If present, inspect `api_url`:

```bash
jq -r '.api_url // empty' "$HOME/.bifrost/credentials.json"
```

### Detect Python and installer

Check for Python 3.11+:

```bash
python3.12 --version
python3.11 --version
python3 --version
python --version
```

Prefer installers in this order:

- `pipx`
- `python3 -m pip`
- `python -m pip`

## Install Flow

### Install CLI

Preferred:

```bash
pipx install --force <bifrost-url>/api/cli/download
```

Fallback:

```bash
python3 -m pip install --force-reinstall <bifrost-url>/api/cli/download
```

Verify:

```bash
bifrost help
```

### Log in

```bash
bifrost login --url <bifrost-url>
```

Credentials are stored in `~/.bifrost/credentials.json`.

## Repo-Specific Boundaries

- Codex work on this repo does not require Claude MCP setup.
- For repo work, local source + CLI + credentials are enough for most tasks.
- The repo's normal development environment is Docker.
- Prefer `./debug.sh` for the local stack and `./test.sh` for validation.

## Quick Interpretation

- Source + CLI + credentials present: SDK-first development is available.
- Source present but no CLI: install CLI, then log in.
- CLI present but no credentials: log in.
- No source but CLI + credentials present: remote/platform-oriented tasks are still possible.

## Optional Claude-Specific MCP Note

Only discuss this when the user is explicitly working in Claude Code and wants MCP-backed platform tools.

Typical Claude MCP command:

```bash
claude mcp add --transport http bifrost <bifrost-url>/mcp
```
