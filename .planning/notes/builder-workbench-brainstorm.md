# Builder Workbench Brainstorm

**Started:** 2026-02-01
**Status:** Active discussion

## The Core Tension

Bifrost tries to serve two development paradigms simultaneously:

1. **Local Development** (git-based, VS Code, filesystem)
   - Requires paths for Python imports
   - Needs serialization/deserialization (DB <-> filesystem)
   - Complex sync logic to detect changes, avoid orphaning, handle conflicts
   - Entity detection via AST parsing to identify workflows vs modules

2. **MCP/AI-First Development** (database-native, Builder UI)
   - Paths don't matter - modules could be by name
   - No serialization step - entities live in DB directly
   - Apps, forms, workflows are just records
   - Much simpler mental model

**The Problem:** Supporting local development adds significant complexity that degrades both experiences:
- `virtual_import.py` - 500+ lines to load Python from Redis instead of filesystem
- `entity_detector.py` - AST parsing to detect if a file is a workflow
- GitHub sync with orphaning protection, conflict detection
- Path columns on entities that only exist to support filesystem imports

## The Builder Workbench Vision

Inspired by Visual Studio WinForms designer:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Workbench: "Client Onboarding App"                    [Publish] [○]     │
├─────────────┬───────────────────────────────────┬───────────────────────┤
│ EXPLORER    │      MAIN CANVAS                  │     CHAT / AI         │
│             │   (context-dependent)             │                       │
│ ▼ App       │                                   │ > Add a field to      │
│   index.tsx │   [App Preview]                   │   capture phone       │
│   styles    │        or                         │   number              │
│ ▼ Workflows │   [Form Designer]                 │                       │
│   onboard   │        or                         │ ✓ Added phone field   │
│   validate  │   [Agent Chat Test]               │   to intake form      │
│ ▼ Forms     │        or                         │                       │
│   intake    │   [Code Editor]                   │                       │
│ ▼ Configs   │                                   │                       │
│   settings  │                                   │                       │
├─────────────┴───────────────────────────────────┴───────────────────────┤
│ OUTPUT / LOGS                                              [popout ↗]   │
│─────────────────────────────────────────────────────────────────────────│
│ 12:04:01  workflow:onboard  started  user_id=abc123                     │
│ 12:04:02  workflow:onboard  step: validate_email ✓                      │
│ 12:04:03  workflow:onboard  completed duration=1.2s                     │
│           Variables: { client_name: "Acme", tier: "premium" }           │
└─────────────────────────────────────────────────────────────────────────┘
```

**Key behaviors:**
- Click "Build" on an App → Workbench opens with that app as root
- Click "Build" on a Form → Form workbench, form as root
- All related entities visible in explorer
- Single place to save, test, run, see logs
- Unified permissions for the session (not per-action dialogs)

---

## Key Decisions Made

### 1. Prescriptive Folders + Name-Based Imports

**Decision:** Folders are prescriptive, names derived from filenames, imports are flat by name.

**Structure:**
```
my-project/
  workflows/
    onboard_client.py       # name: onboard_client
    ticketing/
      sync.py               # name: sync
      escalate.py           # name: escalate
  modules/
    halopsa.py              # name: halopsa
    integrations/
      psa/
        utils.py            # name: utils
  forms/
    intake.form.json        # name: intake
  agents/
    support.agent.json      # name: support
  apps/
    client-portal/
      app.json
      ...
```

**Rules:**
1. Top-level folder = entity type (enforced)
2. Filename = name (no manifest needed)
3. Subfolders are for human organization only
4. Names unique within scope
5. Imports always by name: `from bifrost.modules import halopsa`

### 2. Absolute Imports Only

**Decision:** No relative imports. All module imports use `from bifrost.modules import X`.

This is simpler and more portable. Code works the same locally and in the cloud.

### 3. Multiple Workflows Per File Allowed

**Decision:** A single `.py` file can have multiple `@workflow` decorated functions.

This allows related workflows to share logic in the same file.

**Portable ref format:** `workflow::{filename}::{function_name}`
- Example: `workflow::sync::sync_tickets`

### 4. Repo Per Scope

**Decision:** Separate git repos for global vs org-scoped entities.

**The problem we hit:**
- Multiple orgs need their own `user_onboarding` workflow
- Global `user_onboarding` might also exist
- Can't have same filename twice in one repo
- Scope isn't something you can encode in filename without it being ugly

**The solution:**
- **Global repo**: Shared workflows, modules, agents that everyone can use (community/platform-managed)
- **Org repo**: That org's private stuff, can override/extend global

**Why this works:**
1. Most orgs only have an org repo - they consume global, don't contribute
2. Contributing to global is deliberate (fork, PR) - normal open source flow
3. Platform resolves org-first, global-second at runtime (cascade)
4. Moving org→global = copy file to global repo, delete from org repo (intentional friction)

**Local dev story:**
```
~/projects/
  bifrost-global/        # Clone of global repo (read-only for most)
    workflows/
    modules/
  my-org/                # Your org's repo
    workflows/
    modules/
```

`bifrost run` in `my-org/` loads from `my-org/` first, can fall back to configured global path.

Or simpler: just test your org code locally, global is "just there" in the platform.

---

## What This Simplifies

| Before | After |
|--------|-------|
| Path-based entity detection | Folder determines type |
| `workspace_files.path` as primary key | `name` + `entity_type` + `scope` as key |
| `portable_ref = path::function` | `portable_ref = name::function` |
| Virtual import path→module conversion | Simple name lookup |
| Arbitrary folder structures | Prescriptive top-level folders |
| Single repo with scope detection | Repo = scope |
| Complex orphaning/conflict detection | Simpler sync (name uniqueness enforced) |

---

## Portable References (Updated)

**Format:** `workflow::{name}::{function_name}`

Where:
- `name` = filename (without `.py`)
- `function_name` = the `@workflow` decorated function

**Resolution:**
1. Look in current org for workflow with that name
2. Fall back to global
3. Match function_name within the workflow file

**Examples:**
```
workflow::sync::sync_tickets      # sync.py, function sync_tickets
workflow::onboard::validate       # onboard.py, function validate
```

Forms/agents reference by portable ref:
```json
{
  "name": "intake",
  "on_submit": {
    "workflow": "workflow::onboard::process_intake"
  }
}
```

---

## Local SDK Changes

**Current:** Adds cwd to sys.path, allows arbitrary imports like `from features.x import y`

**New:** Custom importer for `bifrost.modules.*` namespace

```python
# bifrost/local_modules.py

class BifrostModuleFinder(MetaPathFinder):
    """
    Enables `from bifrost.modules import X` locally.
    Scans modules/ folder and registers by filename.
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.module_registry: dict[str, Path] = {}
        self._scan_modules()

    def _scan_modules(self):
        modules_dir = self.project_root / "modules"
        for py_file in modules_dir.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            name = py_file.stem
            if name in self.module_registry:
                raise ValueError(f"Duplicate module name '{name}'")
            self.module_registry[name] = py_file

    def find_spec(self, fullname, path, target=None):
        if not fullname.startswith("bifrost.modules."):
            return None
        module_name = fullname.split(".")[2]
        if module_name not in self.module_registry:
            return None
        return ModuleSpec(fullname, BifrostModuleLoader(...))
```

---

## Cloud/Builder Side Changes

Virtual import simplifies to name-based lookup:

```python
class VirtualModuleFinder(MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if not fullname.startswith("bifrost.modules."):
            return None

        module_name = fullname.split(".")[2]

        # Cascade: org first, then global
        content = redis.get(f"module:{org_id}:{module_name}")
        if not content:
            content = redis.get(f"module:global:{module_name}")
        if not content:
            return None

        return ModuleSpec(fullname, VirtualModuleLoader(content))
```

---

## Open Questions

1. **How does the platform know which repo is global vs org?**
   - Repo setting? First connected org owns it?
   - Or: special "global" org that platform manages?

2. **Can an org contribute to global?**
   - Fork global repo, make changes, PR back?
   - Platform syncs from global repo periodically?

3. **What about dependencies between global and org?**
   - Org workflow imports global module - works (cascade)
   - Global workflow imports org module - should fail (can't depend on org-specific)

4. **Versioning global entities?**
   - If global `halopsa` module changes, do orgs get updated automatically?
   - Or pin to versions?

---

## Migration Path

1. Add `name` column to workflows table (derived from filename)
2. Add `scope` indicator (org_id or null for global)
3. Keep `path` column but make it informational
4. Update portable_ref generation to use `name::function`
5. Update virtual import to name-based lookup with cascade
6. Update local SDK with `bifrost.modules` importer
7. Migrate existing repos to prescriptive structure (tooling needed)

---

## Next Steps

- [ ] Define how global repo is designated/managed
- [ ] Prototype `bifrost.modules` local importer
- [ ] Add `name` column to workflows table
- [ ] Update portable_ref format
- [ ] Design migration tooling for existing repos

---

*Notes from conversation 2026-02-01*
