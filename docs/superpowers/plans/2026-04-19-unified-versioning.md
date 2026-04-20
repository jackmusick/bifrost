# Unified Versioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace four independent hardcoded `2.0.0` strings with a single `BIFROST_VERSION` env var derived from `git describe`, propagated to API, CLI, frontend, Docker images, and CI — with dev builds on every main push and real releases on `v*` tags.

**Architecture:** A new `api/shared/version.py` provides `get_version()` (reads `BIFROST_VERSION` env var, falls back to `git describe`). All consumers (API, health router, CLI `__init__`, CLI download tarball) import from this one place. `BIFROST_VERSION` is injected by `debug.sh` at startup and baked into Docker images as a build arg. CI splits unit and E2E tests so unit tests gate dev image builds; E2E gates tag releases only.

**Tech Stack:** Python `os.environ`, `subprocess`, `functools.lru_cache`; Vite `import.meta.env`; GitHub Actions `docker/metadata-action`; `git describe --tags --always --dirty`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `api/shared/version.py` | **CREATE** | Single `get_version()` + `MIN_CLI_VERSION` constant |
| `api/tests/unit/test_version.py` | **CREATE** | Unit tests for `get_version()` |
| `api/src/routers/version.py` | **CREATE** | `GET /api/version` endpoint |
| `api/src/routers/__init__.py` | **MODIFY** | Export `version_router` |
| `api/src/main.py:266` | **MODIFY** | `version="2.0.0"` → `version=get_version()` + register `version_router` |
| `api/src/routers/health.py:24,32` | **MODIFY** | Replace hardcoded defaults with `get_version()` |
| `api/bifrost/__init__.py:274` | **MODIFY** | `__version__ = '2.0.0'` → `__version__ = get_version()` |
| `api/bifrost/pyproject.toml:7` | **MODIFY** | `version = "2.0.0"` → `version = "0.0.0+source"` |
| `api/bifrost/cli.py` (main dispatch) | **MODIFY** | Add `--version` / `-V` flag handling |
| `api/src/routers/cli.py:2368-2395` | **MODIFY** | Stamp live version into tarball's `pyproject.toml` and `__init__.py` |
| `api/Dockerfile` | **MODIFY** | Add `ARG BIFROST_VERSION=unknown` + `ENV BIFROST_VERSION` |
| `client/Dockerfile` | **MODIFY** | Add `ARG VITE_BIFROST_VERSION=unknown`, pass to `npm run build` |
| `client/src/lib/version.ts` | **CREATE** | `export const APP_VERSION` |
| `client/src/components/AppShell.tsx` (or layout) | **MODIFY** | Display version in footer/sidebar |
| `debug.sh` | **MODIFY** | Compute + export `BIFROST_VERSION` before `docker compose up` |
| `build.sh` | **MODIFY** | Default `TAG` to `git describe`; pass `--build-arg BIFROST_VERSION` |
| `.github/workflows/ci.yml` | **MODIFY** | Split test job; add `build-dev` job; pass version build arg |
| `scripts/release-check.sh` | **CREATE** | Pre-tag safety checks |

---

## Task 1: Create `api/shared/version.py` and unit tests

**Files:**
- Create: `api/shared/version.py`
- Create: `api/tests/unit/test_version.py`

- [ ] **Step 1: Write the failing tests**

Create `api/tests/unit/test_version.py`:

```python
import importlib
import os
import sys
from unittest.mock import patch


def _reload_version():
    """Re-import version module to reset lru_cache between tests."""
    import api.shared.version as m  # noqa: F401
    if "shared.version" in sys.modules:
        del sys.modules["shared.version"]
    import shared.version as v
    importlib.reload(v)
    return v


def test_get_version_from_env(monkeypatch):
    monkeypatch.setenv("BIFROST_VERSION", "2.1.0-dev.5+abc1234")
    v = _reload_version()
    assert v.get_version() == "2.1.0-dev.5+abc1234"


def test_get_version_unknown_when_no_env_and_no_git(monkeypatch):
    monkeypatch.delenv("BIFROST_VERSION", raising=False)
    with patch("subprocess.check_output", side_effect=FileNotFoundError):
        v = _reload_version()
        assert v.get_version() == "unknown"


def test_get_version_git_fallback(monkeypatch):
    monkeypatch.delenv("BIFROST_VERSION", raising=False)
    with patch("subprocess.check_output", return_value="v2.0.0-12-gabc1234\n"):
        v = _reload_version()
        assert v.get_version() == "v2.0.0-12-gabc1234"


def test_min_cli_version_is_string(monkeypatch):
    monkeypatch.setenv("BIFROST_VERSION", "2.0.0")
    v = _reload_version()
    assert isinstance(v.MIN_CLI_VERSION, str)
    assert v.MIN_CLI_VERSION  # non-empty
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
./test.sh tests/unit/test_version.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `shared.version` does not exist yet.

- [ ] **Step 3: Create `api/shared/version.py`**

```python
import os
import subprocess
from functools import lru_cache

MIN_CLI_VERSION = "2.0.0"


@lru_cache(maxsize=1)
def get_version() -> str:
    if v := os.environ.get("BIFROST_VERSION"):
        return v
    try:
        return subprocess.check_output(
            ["git", "describe", "--tags", "--always", "--dirty"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
./test.sh tests/unit/test_version.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add api/shared/version.py api/tests/unit/test_version.py
git commit -m "feat(version): add shared get_version() helper with env-var + git describe fallback"
```

---

## Task 2: Wire `get_version()` into API, health router, and FastAPI app

**Files:**
- Modify: `api/src/main.py:266`
- Modify: `api/src/routers/health.py:24,32`

- [ ] **Step 1: Update `api/src/main.py` line 266**

Change:
```python
    app = FastAPI(
        title="Bifrost API",
        description="MSP automation platform API",
        version="2.0.0",
```

To:
```python
    from shared.version import get_version
    app = FastAPI(
        title="Bifrost API",
        description="MSP automation platform API",
        version=get_version(),
```

- [ ] **Step 2: Update `api/src/routers/health.py`**

Add import at top (after existing imports):
```python
from shared.version import get_version
```

Change line 24:
```python
    version: str = "2.0.0"
```
To:
```python
    version: str = Field(default_factory=get_version)
```

Change line 32:
```python
    version: str = "2.0.0"
```
To:
```python
    version: str = Field(default_factory=get_version)
```

Also add `Field` to the pydantic import at the top of health.py. The existing import is:
```python
from pydantic import BaseModel
```
Change to:
```python
from pydantic import BaseModel, Field
```

- [ ] **Step 3: Verify API starts cleanly**

```bash
docker compose -f docker-compose.dev.yml logs -f api 2>&1 | head -20
```

Expected: API restarts (hot reload), no import errors. Then:

```bash
curl -s http://localhost:3000/health | python3 -m json.tool
```

Expected: `"version"` field is now `"unknown"` (no `BIFROST_VERSION` env var set yet) or the git describe output if git binary is available in container. Either is correct — real value comes in Task 7 when `debug.sh` injects it.

- [ ] **Step 4: Commit**

```bash
git add api/src/main.py api/src/routers/health.py
git commit -m "feat(version): wire get_version() into FastAPI app and health router"
```

---

## Task 3: Create `GET /api/version` endpoint

**Files:**
- Create: `api/src/routers/version.py`
- Modify: `api/src/routers/__init__.py`
- Modify: `api/src/main.py`

- [ ] **Step 1: Create `api/src/routers/version.py`**

```python
from fastapi import APIRouter
from pydantic import BaseModel

from shared.version import MIN_CLI_VERSION, get_version

router = APIRouter(prefix="/api/version", tags=["version"])


class VersionResponse(BaseModel):
    version: str
    min_cli_version: str


@router.get("", response_model=VersionResponse)
async def get_version_info() -> VersionResponse:
    return VersionResponse(
        version=get_version(),
        min_cli_version=MIN_CLI_VERSION,
    )
```

- [ ] **Step 2: Export from `api/src/routers/__init__.py`**

Add at end of imports block (find the last `from src.routers.X import router as X_router` line and add after it):
```python
from src.routers.version import router as version_router
```

Add `"version_router"` to the `__all__` list at the bottom of `__init__.py`.

- [ ] **Step 3: Register in `api/src/main.py`**

In the `from src.routers import (...)` block, add `version_router` to the import list.

Then in the `app.include_router(...)` section (around line 510), add:
```python
    app.include_router(version_router)
```

- [ ] **Step 4: Test the endpoint**

```bash
curl -s http://localhost:3000/api/version | python3 -m json.tool
```

Expected:
```json
{
    "version": "unknown",
    "min_cli_version": "2.0.0"
}
```

(`"unknown"` is correct — `BIFROST_VERSION` env var not yet set. Becomes meaningful after Task 7.)

- [ ] **Step 5: Commit**

```bash
git add api/src/routers/version.py api/src/routers/__init__.py api/src/main.py
git commit -m "feat(version): add GET /api/version endpoint"
```

---

## Task 4: Wire `get_version()` into CLI `__init__` and add `--version` flag

**Files:**
- Modify: `api/bifrost/__init__.py:274`
- Modify: `api/bifrost/pyproject.toml:7`
- Modify: `api/bifrost/cli.py` (main dispatch)

- [ ] **Step 1: Update `api/bifrost/__init__.py` line 274**

The CLI module is standalone and does not import from `shared.*` (those only exist in Docker). Instead, use the same inline fallback pattern directly:

Find line 274:
```python
__version__ = '2.0.0'
```

Replace with:
```python
import os as _os
import subprocess as _subprocess

def _compute_version() -> str:
    if v := _os.environ.get("BIFROST_VERSION"):
        return v
    try:
        return _subprocess.check_output(
            ["git", "describe", "--tags", "--always", "--dirty"],
            text=True,
            stderr=_subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"

__version__ = _compute_version()
```

Note: we do NOT import from `shared.version` here because the CLI is standalone. The logic is intentionally duplicated — the CLI runs outside Docker where `shared/` is not on the path.

- [ ] **Step 2: Update `api/bifrost/pyproject.toml` line 7**

Change:
```toml
version = "2.0.0"
```
To:
```toml
version = "0.0.0+source"
```

This is the placeholder for in-repo/local installs. The download endpoint stamps the real version at serve time (Task 5).

- [ ] **Step 3: Add `--version` / `-V` flag to CLI dispatch**

In `api/bifrost/cli.py`, find the `main()` function's dispatch block (starts around line 342). Add a version check before the `command = args[0].lower()` line:

```python
    if not args:
        print_help()
        return 0

    # Handle --version / -V before lowercasing (they're flags, not commands)
    if args[0] in ("--version", "-V"):
        from bifrost import __version__
        print(f"bifrost {__version__}")
        return 0

    try:
        command = args[0].lower()
```

Also add `--version` and `-V` to `print_help()` — find the `help` line in the Commands list and add after it:
```
  -V, --version   Print the installed CLI version
```

- [ ] **Step 4: Verify locally**

```bash
cd api && pip install -e bifrost/ -q
bifrost --version
```

Expected: `bifrost unknown` (no `BIFROST_VERSION` set in shell; that's correct — it will be set when installed from the API endpoint).

- [ ] **Step 5: Commit**

```bash
git add api/bifrost/__init__.py api/bifrost/pyproject.toml api/bifrost/cli.py
git commit -m "feat(version): CLI reads BIFROST_VERSION env, adds --version flag, placeholder pyproject"
```

---

## Task 5: Stamp version into CLI download tarball

**Files:**
- Modify: `api/src/routers/cli.py:2368-2395`

The `_generate_tarball()` function currently adds `pyproject.toml` directly from disk. We need to rewrite its `version = ...` line on the fly with the live server version, and do the same for `__init__.py`'s `__version__` assignment.

- [ ] **Step 1: Update `_generate_tarball()` in `api/src/routers/cli.py`**

Find the `_generate_tarball()` function (lines ~2368–2395). Replace the body with:

```python
    def _generate_tarball():
        """Generate tarball synchronously in thread."""
        import re
        live_version = get_version()

        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            # Add pyproject.toml at root level with version stamped
            pyproject_path = package_dir / "pyproject.toml"
            if pyproject_path.exists():
                content = pyproject_path.read_text()
                content = re.sub(
                    r'^version\s*=\s*"[^"]*"',
                    f'version = "{live_version}"',
                    content,
                    flags=re.MULTILINE,
                )
                data = content.encode()
                info = tarfile.TarInfo(name="pyproject.toml")
                info.size = len(data)
                tar.addfile(info, fileobj=__import__("io").BytesIO(data))

            # Add all Python files from bifrost/
            for file_path in package_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                if "__pycache__" in str(file_path):
                    continue
                if file_path.name in exclude_files:
                    continue
                if file_path.suffix not in (".py", ".toml"):
                    continue
                if file_path.name == "pyproject.toml":
                    continue  # Already added above

                arcname = f"bifrost/{file_path.relative_to(package_dir)}"

                # Stamp __version__ in __init__.py
                if file_path.name == "__init__.py" and file_path.parent == package_dir:
                    content = file_path.read_text()
                    content = re.sub(
                        r"^__version__\s*=\s*_compute_version\(\)",
                        f'__version__ = "{live_version}"',
                        content,
                        flags=re.MULTILINE,
                    )
                    data = content.encode()
                    info = tarfile.TarInfo(name=arcname)
                    info.size = len(data)
                    tar.addfile(info, fileobj=__import__("io").BytesIO(data))
                else:
                    tar.add(file_path, arcname=arcname)
```

Also add `from shared.version import get_version` at the top of the `download_cli` function (or at the top of `cli.py` router's imports if not already there).

Also update the `Content-Disposition` header to use the live version:

```python
        headers={
            "Content-Disposition": f"attachment; filename=bifrost-cli-{get_version()}.tar.gz",
        },
```

- [ ] **Step 2: Verify via curl**

```bash
curl -s http://localhost:3000/api/cli/download -o /tmp/bifrost-cli-test.tar.gz
tar -tzf /tmp/bifrost-cli-test.tar.gz | head -5
tar -xOzf /tmp/bifrost-cli-test.tar.gz pyproject.toml | grep version
```

Expected: `version = "unknown"` (no `BIFROST_VERSION` set yet — correct).

- [ ] **Step 3: Commit**

```bash
git add api/src/routers/cli.py
git commit -m "feat(version): stamp live server version into CLI download tarball"
```

---

## Task 6: Frontend version display

**Files:**
- Create: `client/src/lib/version.ts`
- Modify: one layout/shell component (identify the correct one below)

- [ ] **Step 1: Find the sidebar/footer component**

```bash
grep -rn "sidebar\|footer\|AppShell\|Layout\|Shell" /home/jack/GitHub/bifrost/client/src/components/ --include="*.tsx" -l | head -10
grep -rn "sidebar\|Sidebar" /home/jack/GitHub/bifrost/client/src/App.tsx | head -5
```

Use the output to identify which component renders the persistent sidebar or footer. Typical candidates: `Sidebar.tsx`, `AppLayout.tsx`, `Shell.tsx`.

- [ ] **Step 2: Create `client/src/lib/version.ts`**

```typescript
export const APP_VERSION: string =
  (import.meta.env.VITE_BIFROST_VERSION as string | undefined) ?? "unknown";
```

- [ ] **Step 3: Add version display to the sidebar/footer component**

In the identified component, import and display:

```tsx
import { APP_VERSION } from "@/lib/version";

// Inside the component JSX, at the bottom of the sidebar or footer:
<p className="text-xs text-muted-foreground px-2 pb-2">{APP_VERSION}</p>
```

Place it in a subtle, non-intrusive location (e.g., bottom of sidebar below nav items, or small footer text).

- [ ] **Step 4: Verify in browser**

Open `http://localhost:3000` and confirm `unknown` appears in the expected location (correct — real value after Task 7).

- [ ] **Step 5: Commit**

```bash
git add client/src/lib/version.ts client/src/components/<modified-file>.tsx
git commit -m "feat(version): display app version in UI sidebar/footer"
```

---

## Task 7: Inject `BIFROST_VERSION` in `debug.sh` and `build.sh`

**Files:**
- Modify: `debug.sh`
- Modify: `build.sh`

- [ ] **Step 1: Update `debug.sh`**

The current content of `debug.sh` starts with:
```bash
mkdir -p api/src/services/app_compiler/node_modules
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Change to:
```bash
#!/bin/bash
set -e

BIFROST_VERSION=$(git describe --tags --always --dirty 2>/dev/null || echo "unknown")
export BIFROST_VERSION
export VITE_BIFROST_VERSION="$BIFROST_VERSION"

mkdir -p api/src/services/app_compiler/node_modules
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

- [ ] **Step 2: Update `build.sh` — default `TAG` to `git describe`**

Find the `TAG="latest"` line near the top of `build.sh` (line ~12). Change:
```bash
TAG="latest"
```
To:
```bash
TAG=$(git describe --tags --always --dirty 2>/dev/null || echo "latest")
```

- [ ] **Step 3: Update `build.sh` — pass `BIFROST_VERSION` build arg**

Find the API build block (lines ~153–158):
```bash
    docker buildx build $NO_CACHE \
        --platform "$PLATFORMS" \
        -t "$API_IMAGE" \
        -f api/Dockerfile \
        $BUILD_OUTPUT \
        .
```

Change to:
```bash
    BIFROST_VERSION=$(git describe --tags --always --dirty 2>/dev/null || echo "unknown")
    docker buildx build $NO_CACHE \
        --platform "$PLATFORMS" \
        -t "$API_IMAGE" \
        -f api/Dockerfile \
        --build-arg "BIFROST_VERSION=${BIFROST_VERSION}" \
        $BUILD_OUTPUT \
        .
```

Find the client build block (lines ~170–176):
```bash
    docker buildx build $NO_CACHE \
        --platform "$PLATFORMS" \
        -t "$CLIENT_IMAGE" \
        -f client/Dockerfile \
        --target production \
        $BUILD_OUTPUT \
        ./client
```

Change to:
```bash
    docker buildx build $NO_CACHE \
        --platform "$PLATFORMS" \
        -t "$CLIENT_IMAGE" \
        -f client/Dockerfile \
        --target production \
        --build-arg "VITE_BIFROST_VERSION=${BIFROST_VERSION}" \
        $BUILD_OUTPUT \
        ./client
```

- [ ] **Step 4: Restart debug stack and verify end-to-end**

Stop and restart the dev stack so `debug.sh` injects the version:

```bash
# Ctrl-C any running debug.sh, then:
./debug.sh
```

Then in another terminal:
```bash
curl -s http://localhost:3000/health | python3 -m json.tool | grep version
curl -s http://localhost:3000/api/version | python3 -m json.tool
bifrost --version  # if installed
```

Expected: all three return the same `git describe` string (e.g., `v0.6-127-gabc1234-dirty`).

Also open `http://localhost:3000` and confirm the version appears in the sidebar/footer.

- [ ] **Step 5: Commit**

```bash
git add debug.sh build.sh
git commit -m "feat(version): inject BIFROST_VERSION from git describe in debug.sh and build.sh"
```

---

## Task 8: Add `ARG`/`ENV` to Dockerfiles

**Files:**
- Modify: `api/Dockerfile`
- Modify: `client/Dockerfile`

- [ ] **Step 1: Update `api/Dockerfile`**

After the `ENV PYTHONUNBUFFERED=1` line (line 77), add:
```dockerfile
ARG BIFROST_VERSION=unknown
ENV BIFROST_VERSION=${BIFROST_VERSION}
```

- [ ] **Step 2: Update `client/Dockerfile`**

In the `builder` stage, before `RUN npm run build` (line 29), add:
```dockerfile
ARG VITE_BIFROST_VERSION=unknown
ENV VITE_BIFROST_VERSION=${VITE_BIFROST_VERSION}
```

The `ENV` makes it available to the `vite build` process (Vite reads `VITE_*` env vars at build time via `import.meta.env`).

- [ ] **Step 3: Test with `build.sh`**

```bash
./build.sh --amd64-only --api-only
docker inspect $(docker images jackmusick/bifrost-api --format "{{.ID}}" | head -1) | grep -A2 BIFROST_VERSION
```

Expected: `BIFROST_VERSION=v0.6-127-gabc1234` (or whatever `git describe` returns) in the image env.

- [ ] **Step 4: Commit**

```bash
git add api/Dockerfile client/Dockerfile
git commit -m "feat(version): bake BIFROST_VERSION build arg into Docker images"
```

---

## Task 9: Update CI — split test jobs, add dev build

**Files:**
- Modify: `.github/workflows/ci.yml`

The current `ci.yml` has one `test` job that runs `./test.sh --coverage --ci`. We split this into `test-unit` and `test-e2e`, add a `build-dev` job, and update existing `build-api`/`build-client` jobs to pass the version build arg.

- [ ] **Step 1: Replace the `test` job with `test-unit` and `test-e2e`**

Replace the entire `test:` job block with:

```yaml
  # =============================================================================
  # Unit Tests - Fast, gates all builds
  # =============================================================================
  test-unit:
    runs-on: ubuntu-latest
    name: Unit Tests
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Run unit tests
        run: |
          chmod +x test.sh
          ./test.sh tests/unit/ --ci

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml
          flags: api
          name: api-coverage
          token: ${{ secrets.CODECOV_TOKEN }}

  # =============================================================================
  # E2E Tests - Slow, only gates tag releases
  # =============================================================================
  test-e2e:
    runs-on: ubuntu-latest
    name: E2E Tests
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Run E2E tests
        run: |
          chmod +x test.sh
          ./test.sh tests/e2e/ --ci
```

- [ ] **Step 2: Add `build-dev` job (push to main only)**

After the `test-e2e` job, add:

```yaml
  # =============================================================================
  # Dev Build - Every push to main, gated by unit tests only
  # =============================================================================
  build-dev:
    if: github.ref == 'refs/heads/main' && !startsWith(github.ref, 'refs/tags/')
    needs: test-unit
    runs-on: ubuntu-latest
    name: Build Dev Images
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Required for git describe to find tags

      - name: Compute version
        id: version
        run: |
          VERSION=$(git describe --tags --always --dirty 2>/dev/null || echo "unknown")
          echo "version=${VERSION}" >> $GITHUB_OUTPUT

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push API dev image
        uses: docker/build-push-action@v5
        with:
          context: .
          file: ./api/Dockerfile
          platforms: linux/amd64,linux/arm64
          push: true
          tags: |
            ghcr.io/${{ env.API_IMAGE }}:${{ steps.version.outputs.version }}
            ghcr.io/${{ env.API_IMAGE }}:dev
            ghcr.io/${{ env.API_IMAGE }}:sha-${{ github.sha }}
          build-args: |
            BIFROST_VERSION=${{ steps.version.outputs.version }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Build and push client dev image
        uses: docker/build-push-action@v5
        with:
          context: ./client
          file: ./client/Dockerfile
          target: production
          platforms: linux/amd64,linux/arm64
          push: true
          tags: |
            ghcr.io/${{ env.CLIENT_IMAGE }}:${{ steps.version.outputs.version }}
            ghcr.io/${{ env.CLIENT_IMAGE }}:dev
            ghcr.io/${{ env.CLIENT_IMAGE }}:sha-${{ github.sha }}
          build-args: |
            VITE_BIFROST_VERSION=${{ steps.version.outputs.version }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 3: Update `build-api` and `build-client` jobs to use `test-unit` + `test-e2e` and pass version**

In the `build-api` job:
- Change `needs: test` → `needs: [test-unit, test-e2e]`
- Add `fetch-depth: 0` to the checkout step
- Add a `Compute version` step (same as in `build-dev` above, but for tag builds, derive from tag name):

```yaml
      - name: Compute version from tag
        id: version
        run: |
          VERSION="${GITHUB_REF#refs/tags/v}"
          echo "version=${VERSION}" >> $GITHUB_OUTPUT
```

- Add `build-args: BIFROST_VERSION=${{ steps.version.outputs.version }}` to the `docker/build-push-action` step.

In the `build-client` job:
- Same changes: `needs: [test-unit, test-e2e]`, add version compute step, add `build-args: VITE_BIFROST_VERSION=${{ steps.version.outputs.version }}`.

In the `create-release` job:
- Change `needs: [build-api, build-client]` — no change needed, already correct.

- [ ] **Step 4: Verify CI yaml is valid**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "YAML valid"
```

Expected: `YAML valid`

- [ ] **Step 5: Commit and push to trigger CI**

```bash
git add .github/workflows/ci.yml
git commit -m "feat(version): split unit/e2e test jobs; add build-dev job for main pushes"
git push origin main
```

Open GitHub Actions and confirm:
- `Unit Tests` job runs and passes
- `E2E Tests` job runs (may pass or fail — does not block `Build Dev Images`)
- `Build Dev Images` job runs after `Unit Tests` and pushes `:dev` images

---

## Task 10: Add `scripts/release-check.sh`

**Files:**
- Create: `scripts/release-check.sh`

- [ ] **Step 1: Create the script**

```bash
mkdir -p scripts
```

Create `scripts/release-check.sh`:

```bash
#!/bin/bash
# Pre-tag safety checks before creating a release tag.
# Usage: ./scripts/release-check.sh v2.1.0
# Run this BEFORE: git tag v2.1.0 && git push --tags

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

TAG="$1"

if [ -z "$TAG" ]; then
    echo -e "${RED}Usage: $0 <tag> (e.g., $0 v2.1.0)${NC}"
    exit 1
fi

if [[ "$TAG" != v* ]]; then
    echo -e "${RED}Tag must start with 'v' (got: $TAG)${NC}"
    exit 1
fi

FAIL=0

echo "Running release checks for $TAG..."
echo ""

# 1. Clean working tree
if [ -n "$(git status --porcelain)" ]; then
    echo -e "${RED}✗ Working tree is dirty. Commit or stash changes first.${NC}"
    git status --short
    FAIL=1
else
    echo -e "${GREEN}✓ Working tree is clean${NC}"
fi

# 2. Tag does not already exist locally
if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo -e "${RED}✗ Tag $TAG already exists locally. Use a different version.${NC}"
    FAIL=1
else
    echo -e "${GREEN}✓ Tag $TAG does not exist locally${NC}"
fi

# 3. Tag does not already exist on remote
if git ls-remote --tags origin "$TAG" | grep -q "$TAG"; then
    echo -e "${RED}✗ Tag $TAG already exists on remote. Use a different version.${NC}"
    FAIL=1
else
    echo -e "${GREEN}✓ Tag $TAG does not exist on remote${NC}"
fi

# 4. Current HEAD is on main
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo -e "${YELLOW}⚠ Not on main branch (on: $CURRENT_BRANCH). Proceed with caution.${NC}"
else
    echo -e "${GREEN}✓ On main branch${NC}"
fi

# 5. Unit tests pass
echo ""
echo -e "${YELLOW}Running unit tests...${NC}"
if ./test.sh tests/unit/ -v; then
    echo -e "${GREEN}✓ Unit tests passed${NC}"
else
    echo -e "${RED}✗ Unit tests failed. Fix before tagging.${NC}"
    FAIL=1
fi

echo ""
if [ $FAIL -ne 0 ]; then
    echo -e "${RED}Release checks FAILED. Fix the issues above before tagging.${NC}"
    exit 1
fi

echo -e "${GREEN}All release checks passed!${NC}"
echo ""
echo "To create the release:"
echo "  git tag $TAG && git push origin $TAG"
```

- [ ] **Step 2: Make executable and test**

```bash
chmod +x scripts/release-check.sh
./scripts/release-check.sh
```

Expected: `Usage: ./scripts/release-check.sh <tag>` error (no arg supplied).

```bash
./scripts/release-check.sh v999.0.0
```

Expected: prints checks, passes or fails based on current state. Should show `✓` for clean tree (if your tree is clean at this point) and `✓` for tag not existing.

- [ ] **Step 3: Commit**

```bash
git add scripts/release-check.sh
git commit -m "feat(version): add release-check.sh pre-tag safety script"
```

---

## Task 11: Add optional CLI version check against `/api/version`

**Files:**
- Modify: `api/bifrost/cli.py`

The CLI should warn (not fail) if the installed version is older than `min_cli_version` returned by the API. This runs at login or at first command, uses the stored API URL, and is silently skipped if the API is unreachable.

- [ ] **Step 1: Add a `_check_cli_version()` helper in `api/bifrost/cli.py`**

Find where constants and helpers are defined near the top of cli.py (after imports). Add:

```python
def _check_cli_version() -> None:
    """Warn if the installed CLI is older than the API's minimum required version."""
    try:
        import urllib.request
        import json as _json
        from bifrost import __version__

        # Load API URL from stored config (same pattern used by login)
        config_path = pathlib.Path.home() / ".bifrost" / "config.json"
        if not config_path.exists():
            return
        config = _json.loads(config_path.read_text())
        api_url = config.get("api_url", "").rstrip("/")
        if not api_url:
            return

        with urllib.request.urlopen(f"{api_url}/api/version", timeout=3) as resp:
            data = _json.loads(resp.read())

        min_ver = data.get("min_cli_version", "")
        installed = __version__.lstrip("v")
        # Simple string comparison works for semver when both are well-formed
        if min_ver and installed != "unknown" and installed < min_ver:
            print(
                f"\033[33mWarning: CLI version {installed} is older than the "
                f"minimum required {min_ver}. Run:\n"
                f"  pipx install {api_url}/api/cli/download\n\033[0m",
                file=sys.stderr,
            )
    except Exception:
        pass  # Never block the user for a version check failure
```

- [ ] **Step 2: Call it at startup in `main()`**

In the `main()` function, after the `--version` check and before the `try:` block that dispatches commands, add:

```python
    _check_cli_version()

    try:
        command = args[0].lower()
```

- [ ] **Step 3: Verify it doesn't break anything**

```bash
bifrost --help
bifrost --version
bifrost login --help
```

Expected: all work normally. Version check either silently passes (API reachable) or silently skips (not reachable).

- [ ] **Step 4: Commit**

```bash
git add api/bifrost/cli.py
git commit -m "feat(version): CLI warns if installed version is below API min_cli_version"
```

---

## Verification Checklist

Run through these after all tasks are complete:

- [ ] `./debug.sh` up → `curl http://localhost:3000/health | python3 -m json.tool` → `version` field matches `git describe` output
- [ ] `curl http://localhost:3000/api/version | python3 -m json.tool` → same version, plus `min_cli_version`
- [ ] Browser opens `http://localhost:3000` → version string visible in sidebar/footer
- [ ] `pip install --force-reinstall http://localhost:3000/api/cli/download && bifrost --version` → prints same version as above
- [ ] `pipx install http://localhost:3000/api/cli/download` (no `--force`) → pipx detects version change and upgrades (requires two different debug.sh sessions at different git commits)
- [ ] `./build.sh --amd64-only --api-only` → `docker inspect` shows `BIFROST_VERSION` env in image
- [ ] `./scripts/release-check.sh v2.1.0` → passes on clean main, fails with "dirty" if uncommitted changes
- [ ] CI push to main → Unit Tests passes → Build Dev Images runs → `:dev` and `:<version>` tags pushed to GHCR
- [ ] CI push to main with failing E2E → Build Dev Images still runs (E2E doesn't block it)
- [ ] `./test.sh tests/unit/test_version.py -v` → all 4 tests pass
