# Appendix: Package Installation

## Overview

This document clarifies how Python package installation works in Bifrost.

## Current Behavior: System Site-Packages

Packages are installed to the **system Python site-packages**, NOT to a `.packages` directory in the workspace.

**File:** `api/src/services/package_manager.py`

```python
async def install_packages(requirements: list[str]) -> InstallResult:
    """
    Install packages to system Python environment.

    Packages are installed to the system Python site-packages and are
    immediately available to all code running in the container.
    """
    cmd = [sys.executable, "-m", "pip", "install", *requirements]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # ...
```

## Why System Site-Packages?

1. **Container isolation:** Each worker runs in its own container. Installing to system site-packages affects only that container.

2. **Standard Python behavior:** `import package_name` works without any path manipulation.

3. **No path hacks:** Don't need to modify `sys.path` or use custom import hooks for packages.

4. **Caching:** Docker layer caching can cache common packages across builds.

## Package Installation Flow

1. **User defines requirements** in workflow metadata or `requirements.txt`
2. **Init container or startup** installs packages via `pip install`
3. **Packages go to** `/usr/local/lib/python3.11/site-packages/` (or similar)
4. **Available immediately** to all Python code in the container

## Relationship to Virtual Modules

Virtual module loading (from Redis) is for **user-written workspace code**:
- `from shared import halopsa` → loaded from Redis
- `import requests` → loaded from system site-packages (standard import)

The virtual import hook checks if a path exists in our module index. If not, it returns `None` and Python falls through to the standard filesystem finder, which finds packages in site-packages.

## No `.packages` Directory

There is no `.packages` directory. If you see references to it in old code or docs, that's outdated. The current design uses:

- **System site-packages** for third-party packages (requests, pandas, etc.)
- **Database/Redis** for user-written modules (via virtual import hook)

## Docker Build vs Runtime

**Build time (Dockerfile):**
```dockerfile
# Base packages installed during image build
RUN pip install requests pandas sqlalchemy
```

**Runtime (during execution):**
```python
# Dynamic packages can be installed at runtime
await package_manager.install_packages(["custom-package==1.0"])
```

Both end up in system site-packages.

## Summary

| What | Where | How |
|------|-------|-----|
| Third-party packages | System site-packages | `pip install` |
| User modules | Database + Redis cache | Virtual import hook |
| Workflows | Database (workflows.code) | `exec_from_db()` |

The virtual module loading plan does NOT change package installation - it only affects user-written `.py` files in the workspace.
