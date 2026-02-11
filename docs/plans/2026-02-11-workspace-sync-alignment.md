# Workspace Sync Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the workspace sync pipeline so that `bifrost sync` works end-to-end — serialization matches import, the CLI /sync endpoint exists, and bifrost-workspace passes preflight + syncs successfully.

**Architecture:** The git sync has two code paths that diverged: (1) `FormIndexer`/`AgentIndexer` used by the code editor's file watcher, and (2) `_import_form`/`_import_agent`/`_import_app` in `github_sync.py` used by `desktop_pull`. Path (2) is incomplete — it bypasses the indexers and loses data. We'll fix (2) to delegate to the indexers, add the missing `/sync` API endpoint, fix the serialization format mismatches, and update bifrost-workspace to match.

**Tech Stack:** Python 3.11 (FastAPI, SQLAlchemy, Pydantic, PyYAML, GitPython), PostgreSQL, S3/MinIO

---

## Task 1: Fix Agent Import — Use AgentIndexer in github_sync.py

The `_import_agent` method in `github_sync.py` only imports name/system_prompt/description. It ignores tool_ids, channels, knowledge_sources, delegated_agent_ids, LLM config. The `AgentIndexer` already handles all of this correctly.

**Files:**
- Modify: `api/src/services/github_sync.py` (lines 798-828, `_import_agent`)
- Test: `api/tests/integration/platform/test_git_sync_local.py`

**Step 1: Write a failing test — agent tool associations survive pull**

Add to `test_git_sync_local.py` in the `TestPull` class:

```python
async def test_pull_new_agent_with_tools(self, sync_service, db, work_dir):
    """Agent pulled from repo should have tool associations."""
    from src.models.orm.agents import Agent
    from src.models.orm.workflows import Workflow

    # Create a workflow to be referenced as a tool
    wf_id = uuid4()
    db.add(Workflow(
        id=wf_id,
        name="agent_tool_workflow",
        path="workflows/agent_tool.py",
        function_name="agent_tool_workflow",
        is_active=True,
    ))
    await db.flush()

    agent_id = uuid4()
    agent_yaml = f"""name: Test Agent With Tools
description: Agent with tool associations
system_prompt: You are a test agent.
channels:
- chat
tool_ids:
- {wf_id}
"""
    # Write agent file + manifest
    agent_dir = work_dir / "agents"
    agent_dir.mkdir(exist_ok=True)
    (agent_dir / f"{agent_id}.agent.yaml").write_text(agent_yaml)

    manifest_dir = work_dir / ".bifrost"
    manifest_dir.mkdir(exist_ok=True)
    (manifest_dir / "metadata.yaml").write_text(f"""agents:
  Test Agent With Tools:
    id: "{agent_id}"
    path: agents/{agent_id}.agent.yaml
    organization_id: null
    roles: []
workflows: {{}}
forms: {{}}
apps: {{}}
organizations: []
roles: []
""")

    # Commit to repo
    repo = sync_service._open_or_init(work_dir)
    repo.index.add(["agents/", ".bifrost/"])
    repo.index.commit("Add agent with tools")

    # Import
    async with db.begin_nested():
        await sync_service._import_all_entities(work_dir)
    await db.commit()

    # Verify agent was created with tool association
    agent = await db.get(Agent, agent_id)
    assert agent is not None
    assert agent.name == "Test Agent With Tools"
    assert agent.channels == ["chat"]

    # Verify tool association
    from sqlalchemy import select
    from src.models.orm.agents import AgentTool
    tools = (await db.execute(
        select(AgentTool).where(AgentTool.agent_id == agent_id)
    )).scalars().all()
    assert len(tools) == 1
    assert tools[0].workflow_id == wf_id
```

**Step 2: Run test to verify it fails**

```bash
./test.sh tests/integration/platform/test_git_sync_local.py::TestPull::test_pull_new_agent_with_tools -v
```

Expected: FAIL — current `_import_agent` doesn't create tool associations.

**Step 3: Replace _import_agent to use AgentIndexer**

In `api/src/services/github_sync.py`, replace the `_import_agent` method:

```python
async def _import_agent(self, magent, content: bytes) -> None:
    """Import an agent from repo YAML into the DB using AgentIndexer."""
    from uuid import UUID

    from src.services.file_storage.indexers.agent import AgentIndexer

    # Inject ID into YAML if not present (manifest is source of truth for ID)
    data = yaml.safe_load(content.decode("utf-8"))
    if not data:
        return

    data["id"] = magent.id
    # Set organization_id before indexing so it's available for new agents
    if magent.organization_id:
        # AgentIndexer preserves existing org_id on update, but we need it for insert
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from src.models.orm.agents import Agent
        # Pre-create with org_id if doesn't exist yet
        stmt = pg_insert(Agent).values(
            id=UUID(magent.id),
            name=data.get("name", ""),
            system_prompt=data.get("system_prompt", ""),
            is_active=True,
            created_by="git-sync",
            organization_id=UUID(magent.organization_id),
        ).on_conflict_do_nothing(index_elements=["id"])
        await self.db.execute(stmt)

    updated_content = yaml.dump(data, default_flow_style=False, sort_keys=False).encode("utf-8")
    indexer = AgentIndexer(self.db)
    await indexer.index_agent(f"agents/{magent.id}.agent.yaml", updated_content)
```

**Step 4: Run test to verify it passes**

```bash
./test.sh tests/integration/platform/test_git_sync_local.py::TestPull::test_pull_new_agent_with_tools -v
```

Expected: PASS

**Step 5: Run all git sync tests to check for regressions**

```bash
./test.sh tests/integration/platform/test_git_sync_local.py -v
```

Expected: All existing tests still pass.

**Step 6: Commit**

```bash
git add api/src/services/github_sync.py api/tests/integration/platform/test_git_sync_local.py
git commit -m "fix: use AgentIndexer in git sync import for complete agent data"
```

---

## Task 2: Fix Form Import — Use FormIndexer in github_sync.py

Same problem as agents. `_import_form` loses all form fields.

**Files:**
- Modify: `api/src/services/github_sync.py` (lines 766-796, `_import_form`)
- Test: `api/tests/integration/platform/test_git_sync_local.py`

**Step 1: Write a failing test — form fields survive pull**

Add to `test_git_sync_local.py` in the `TestPull` class:

```python
async def test_pull_new_form_with_fields(self, sync_service, db, work_dir):
    """Form pulled from repo should have field definitions."""
    from src.models.orm.forms import Form, FormField
    from src.models.orm.workflows import Workflow

    # Create a workflow to be referenced
    wf_id = uuid4()
    db.add(Workflow(
        id=wf_id,
        name="form_test_workflow",
        path="workflows/form_test.py",
        function_name="form_test_workflow",
        is_active=True,
    ))
    await db.flush()

    form_id = uuid4()
    form_yaml = f"""name: Test Form With Fields
description: Form with field definitions
workflow_id: {wf_id}
form_schema:
  fields:
  - name: email
    type: text
    label: Email Address
    required: true
  - name: count
    type: number
    label: Count
    required: false
    default_value: 5
"""
    form_dir = work_dir / "forms"
    form_dir.mkdir(exist_ok=True)
    (form_dir / f"{form_id}.form.yaml").write_text(form_yaml)

    manifest_dir = work_dir / ".bifrost"
    manifest_dir.mkdir(exist_ok=True)
    (manifest_dir / "metadata.yaml").write_text(f"""forms:
  Test Form With Fields:
    id: "{form_id}"
    path: forms/{form_id}.form.yaml
    organization_id: null
    roles: []
workflows: {{}}
agents: {{}}
apps: {{}}
organizations: []
roles: []
""")

    repo = sync_service._open_or_init(work_dir)
    repo.index.add(["forms/", ".bifrost/"])
    repo.index.commit("Add form with fields")

    async with db.begin_nested():
        await sync_service._import_all_entities(work_dir)
    await db.commit()

    # Verify form was created
    form = await db.get(Form, form_id)
    assert form is not None
    assert form.name == "Test Form With Fields"
    assert str(form.workflow_id) == str(wf_id)

    # Verify fields were imported
    from sqlalchemy import select
    fields = (await db.execute(
        select(FormField).where(FormField.form_id == form_id).order_by(FormField.position)
    )).scalars().all()
    assert len(fields) == 2
    assert fields[0].name == "email"
    assert fields[0].type == "text"
    assert fields[0].required is True
    assert fields[1].name == "count"
    assert fields[1].default_value == 5
```

**Step 2: Run test to verify it fails**

```bash
./test.sh tests/integration/platform/test_git_sync_local.py::TestPull::test_pull_new_form_with_fields -v
```

Expected: FAIL — current `_import_form` doesn't import fields.

**Step 3: Replace _import_form to use FormIndexer**

In `api/src/services/github_sync.py`, replace the `_import_form` method:

```python
async def _import_form(self, mform, content: bytes) -> None:
    """Import a form from repo YAML into the DB using FormIndexer."""
    from uuid import UUID

    from src.services.file_storage.indexers.form import FormIndexer

    # Inject ID into YAML if not present (manifest is source of truth for ID)
    data = yaml.safe_load(content.decode("utf-8"))
    if not data:
        return

    data["id"] = mform.id
    # Set organization_id before indexing so it's available for new forms
    if mform.organization_id:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from src.models.orm.forms import Form
        stmt = pg_insert(Form).values(
            id=UUID(mform.id),
            name=data.get("name", ""),
            is_active=True,
            created_by="git-sync",
            organization_id=UUID(mform.organization_id),
        ).on_conflict_do_nothing(index_elements=["id"])
        await self.db.execute(stmt)

    updated_content = yaml.dump(data, default_flow_style=False, sort_keys=False).encode("utf-8")
    indexer = FormIndexer(self.db)
    await indexer.index_form(f"forms/{mform.id}.form.yaml", updated_content)
```

**Step 4: Run test to verify it passes**

```bash
./test.sh tests/integration/platform/test_git_sync_local.py::TestPull::test_pull_new_form_with_fields -v
```

Expected: PASS

**Step 5: Run all git sync tests**

```bash
./test.sh tests/integration/platform/test_git_sync_local.py -v
```

Expected: All pass.

**Step 6: Commit**

```bash
git add api/src/services/github_sync.py api/tests/integration/platform/test_git_sync_local.py
git commit -m "fix: use FormIndexer in git sync import for complete form data"
```

---

## Task 3: Support `tools` as Alias for `tool_ids` in AgentIndexer

The bifrost-workspace and human-authored YAML uses `tools` (shorter, friendlier). The serializer outputs `tool_ids`. The indexer should accept both.

**Files:**
- Modify: `api/src/services/file_storage/indexers/agent.py` (line 180)
- Test: `api/tests/unit/services/test_agent_indexer.py` (or add to existing agent tests)

**Step 1: Write a failing test**

```python
async def test_index_agent_with_tools_alias(self, db):
    """AgentIndexer should accept 'tools' as alias for 'tool_ids'."""
    from src.services.file_storage.indexers.agent import AgentIndexer
    from src.models.orm.workflows import Workflow

    wf_id = uuid4()
    db.add(Workflow(
        id=wf_id, name="test_wf", path="workflows/test.py",
        function_name="test_wf", is_active=True,
    ))
    await db.flush()

    agent_yaml = f"""name: Agent With Tools Alias
system_prompt: Test
tools:
- {wf_id}
"""
    indexer = AgentIndexer(db)
    await indexer.index_agent("agents/test.agent.yaml", agent_yaml.encode())
    await db.flush()

    from sqlalchemy import select
    from src.models.orm.agents import Agent, AgentTool
    agent = (await db.execute(select(Agent).where(Agent.name == "Agent With Tools Alias"))).scalar_one()
    tools = (await db.execute(select(AgentTool).where(AgentTool.agent_id == agent.id))).scalars().all()
    assert len(tools) == 1
    assert tools[0].workflow_id == wf_id
```

**Step 2: Run test to verify it fails**

Expected: FAIL — `tools` key is ignored, only `tool_ids` is read.

**Step 3: Add alias support in AgentIndexer**

In `api/src/services/file_storage/indexers/agent.py`, around line 180:

```python
# Sync tool associations (tool_ids are workflow UUIDs)
# Accept 'tools' as friendlier alias for 'tool_ids'
tool_ids = agent_data.get("tool_ids") or agent_data.get("tools", [])
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add api/src/services/file_storage/indexers/agent.py api/tests/...
git commit -m "feat: accept 'tools' as alias for 'tool_ids' in agent YAML"
```

---

## Task 4: Support `workflow`/`launch_workflow` Aliases and Flat `fields` in FormIndexer

The workspace uses `workflow` (not `workflow_id`), `launch_workflow` (not `launch_workflow_id`), and flat `fields:` with `default:` (not `form_schema.fields` with `default_value:`).

**Files:**
- Modify: `api/src/services/file_storage/indexers/form.py` (lines 149-203)
- Test: `api/tests/unit/services/test_form_indexer.py` (or add to existing form tests)

**Step 1: Write failing tests**

Test 1 — `workflow` alias:
```python
async def test_index_form_with_workflow_alias(self, db):
    """FormIndexer should accept 'workflow' as alias for 'workflow_id'."""
    from src.services.file_storage.indexers.form import FormIndexer

    wf_id = uuid4()
    form_yaml = f"""name: Test Form Alias
workflow: {wf_id}
"""
    indexer = FormIndexer(db)
    await indexer.index_form("forms/test.form.yaml", form_yaml.encode())
    await db.flush()

    from sqlalchemy import select
    from src.models.orm.forms import Form
    form = (await db.execute(select(Form).where(Form.name == "Test Form Alias"))).scalar_one()
    assert str(form.workflow_id) == str(wf_id)
```

Test 2 — flat `fields` with `default`:
```python
async def test_index_form_with_flat_fields(self, db):
    """FormIndexer should accept flat 'fields' array (not nested in form_schema)."""
    from src.services.file_storage.indexers.form import FormIndexer

    form_yaml = """name: Flat Fields Form
fields:
- name: email
  type: text
  label: Email
  required: true
- name: count
  type: number
  label: Count
  default: 5
"""
    indexer = FormIndexer(db)
    await indexer.index_form("forms/test.form.yaml", form_yaml.encode())
    await db.flush()

    from sqlalchemy import select
    from src.models.orm.forms import Form, FormField
    form = (await db.execute(select(Form).where(Form.name == "Flat Fields Form"))).scalar_one()
    fields = (await db.execute(
        select(FormField).where(FormField.form_id == form.id).order_by(FormField.position)
    )).scalars().all()
    assert len(fields) == 2
    assert fields[0].name == "email"
    assert fields[1].default_value == 5
```

**Step 2: Run tests to verify they fail**

**Step 3: Add alias support in FormIndexer**

In `api/src/services/file_storage/indexers/form.py`:

Around line 149 (workflow_id resolution):
```python
# Get workflow_id - prefer explicit workflow_id, fall back to 'workflow' (UUID alias),
# then linked_workflow (name lookup)
workflow_id = form_data.get("workflow_id") or form_data.get("workflow")
if not workflow_id:
    linked_workflow = form_data.get("linked_workflow")
    if linked_workflow:
        workflow_id = await self.resolve_workflow_name_to_id(linked_workflow)
        ...
```

Around line 161 (launch_workflow_id):
```python
launch_workflow_id = form_data.get("launch_workflow_id") or form_data.get("launch_workflow")
if not launch_workflow_id:
    launch_workflow_name = form_data.get("launch_workflow")
    # Only do name lookup if it's not a UUID
    ...
```

Around line 200 (form_schema fields):
```python
# Sync form_schema (fields) if present
# Support both form_schema.fields (canonical) and flat fields (workspace shorthand)
form_schema = form_data.get("form_schema")
if form_schema and isinstance(form_schema, dict):
    fields_data = form_schema.get("fields", [])
elif "fields" in form_data and isinstance(form_data["fields"], list):
    # Flat fields format — normalize 'default' to 'default_value'
    fields_data = []
    for f in form_data["fields"]:
        if isinstance(f, dict):
            fd = dict(f)
            if "default" in fd and "default_value" not in fd:
                fd["default_value"] = fd.pop("default")
            fields_data.append(fd)
else:
    fields_data = None

if fields_data is not None and isinstance(fields_data, list):
    # ... existing field sync logic (delete + recreate) ...
```

**Step 4: Run tests to verify they pass**

**Step 5: Commit**

```bash
git add api/src/services/file_storage/indexers/form.py api/tests/...
git commit -m "feat: accept workflow/fields aliases in form YAML for workspace compat"
```

---

## Task 5: Add `GET /api/github/sync` and `POST /api/github/sync` Endpoints

The CLI `bifrost sync` calls these endpoints but they don't exist.

**Files:**
- Modify: `api/src/routers/github.py` — add two endpoints
- Modify: `api/src/models/contracts/github.py` — add request/response models if needed
- Test: `api/tests/integration/platform/test_git_sync_local.py` or new file

**Step 1: Add models**

In `api/src/models/contracts/github.py`, add:

```python
class SyncPreview(BaseModel):
    """Sync preview showing what would change."""
    is_empty: bool = True
    to_pull: list[dict] = Field(default_factory=list)
    to_push: list[dict] = Field(default_factory=list)
    conflicts: list[dict] = Field(default_factory=list)
    preflight: dict = Field(default_factory=dict)


class SyncExecuteRequest(BaseModel):
    """Request to execute a sync with conflict resolutions."""
    conflict_resolutions: dict[str, str] = Field(default_factory=dict)
    confirm_orphans: bool = False
```

**Step 2: Add GET /api/github/sync endpoint**

This endpoint should:
1. Run `desktop_fetch` to get remote state
2. Compute diff between local and remote (what to pull/push)
3. Run preflight validation on incoming files
4. Return the preview

Since these operations can be slow, they should be queued as a background job. The CLI polls `/api/jobs/{job_id}`.

```python
@router.get(
    "/sync",
    response_model=GitJobResponse,
    summary="Preview sync",
)
async def sync_preview_endpoint(
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> GitJobResponse:
    """Queue a sync preview job. Poll /api/jobs/{job_id} for results."""
    # Create background job
    job_id = str(uuid.uuid4())
    # ... queue job that runs desktop_fetch + desktop_status + preflight ...
    return GitJobResponse(job_id=job_id, status="queued")
```

**Step 3: Add POST /api/github/sync endpoint**

```python
@router.post(
    "/sync",
    response_model=GitJobResponse,
    summary="Execute sync",
)
async def sync_execute_endpoint(
    request: SyncExecuteRequest,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> GitJobResponse:
    """Queue a sync execution job. Commits local changes, pulls remote, pushes."""
    job_id = str(uuid.uuid4())
    # ... queue job that runs commit + pull (with resolutions) + push ...
    return GitJobResponse(job_id=job_id, status="queued")
```

**Note:** The exact job queuing mechanism depends on the existing job infrastructure. Look at how `/fetch`, `/pull`, `/push` endpoints queue jobs. The pattern is likely:
1. Create a job record
2. Submit to background worker
3. Return job_id
4. Worker updates job record on completion

**Step 4: Write integration test that exercises the endpoint**

**Step 5: Commit**

```bash
git add api/src/routers/github.py api/src/models/contracts/github.py api/tests/...
git commit -m "feat: add GET/POST /api/github/sync endpoints for CLI sync"
```

---

## Task 6: Update bifrost-workspace Agent YAMLs

Rename `tools` to `tool_ids` in all agent YAML files, add `id` field where missing.

**Files:**
- Modify: `/home/jack/GitHub/bifrost-workspace/agents/*.agent.yaml` (4 files)

**Step 1: Update each agent file**

For each agent YAML:
- Add `id: <uuid-from-filename>` at the top
- Rename `tools:` to `tool_ids:` (if the alias from Task 3 is in place, this is optional but keeps consistency with what the serializer outputs)
- Remove `llm_model: null` lines (exclude_none in serializer means null fields shouldn't appear)

Example for `b70cfb81-411a-4110-ad20-a9c92c5934bf.agent.yaml`:
```yaml
id: b70cfb81-411a-4110-ad20-a9c92c5934bf
name: HaloPSA Report Agent
description: ...
system_prompt: ...
tool_ids:
- c943c063-7ef0-4316-b8ff-3fd02c1b7869
- 9dd8f037-400b-47c2-be1c-55d42a259541
- 0e86a4b8-046e-4b0b-a76d-37f62c13f22c
```

**Step 2: Commit in bifrost-workspace**

```bash
cd /home/jack/GitHub/bifrost-workspace
git add agents/
git commit -m "fix: align agent YAML format with serializer (add id, rename tools to tool_ids)"
```

---

## Task 7: Update bifrost-workspace Form YAMLs

Convert forms to canonical format: `workflow_id`, `launch_workflow_id`, `form_schema.fields`, `default_value`.

**Files:**
- Modify: `/home/jack/GitHub/bifrost-workspace/forms/*.form.yaml` (4 files)

**Step 1: Update each form file**

For each form:
- Add `id: <uuid-from-filename>` at the top
- Rename `workflow:` to `workflow_id:`
- Rename `launch_workflow:` to `launch_workflow_id:` (or remove if null)
- Wrap `fields:` under `form_schema:`
- Rename `default:` to `default_value:` in each field

Example for `196309ab-56bd-49f6-95e2-5878c9d43378.form.yaml`:
```yaml
id: 196309ab-56bd-49f6-95e2-5878c9d43378
name: Test Greeting
description: Form for testing the greeting workflow
workflow_id: 35c332d1-78f4-48cc-88a8-73a8e70339e0
form_schema:
  fields:
  - name: name
    type: text
    label: Your Name
    required: true
  - name: greeting_type
    type: text
    label: Greeting Type
    default_value: Hello
  - name: repeat_count
    type: number
    label: Repeat Count
    default_value: 1
  - name: uppercase
    type: checkbox
    label: Uppercase
    default_value: false
```

**Step 2: Commit in bifrost-workspace**

```bash
cd /home/jack/GitHub/bifrost-workspace
git add forms/
git commit -m "fix: align form YAML format with serializer (add id, use workflow_id, form_schema)"
```

---

## Task 8: Validate E2E Tests Still Cover the Key Scenarios

Review and potentially extend integration tests to cover the full round-trip:
- Serialize agent from DB → YAML → import back → verify tools/channels/knowledge preserved
- Serialize form from DB → YAML → import back → verify fields preserved
- Preflight catches broken references, syntax errors

**Files:**
- Review: `api/tests/integration/platform/test_git_sync_local.py`
- Review: `api/tests/unit/services/test_github_sync_virtual_files.py`

**Step 1: Add round-trip test for agent with tools**

In `TestRoundTrip`:
```python
async def test_agent_with_tools_survives_round_trip(self, ...):
    """Create agent with tools → commit+push → modify in repo → pull → tools preserved."""
    # Create agent + tool associations in DB
    # Commit + push (should serialize to YAML with tool_ids)
    # Verify serialized YAML has tool_ids
    # Pull back
    # Verify tool associations still exist
```

**Step 2: Add round-trip test for form with fields**

```python
async def test_form_with_fields_survives_round_trip(self, ...):
    """Create form with fields → commit+push → pull → fields preserved."""
```

**Step 3: Run all tests**

```bash
./test.sh tests/integration/platform/test_git_sync_local.py -v
./test.sh tests/unit/services/ -v
```

**Step 4: Commit**

---

## Task 9: Run Preflight + Sync Against bifrost-workspace

This is the manual validation step using the actual bifrost-workspace.

**Step 1: Ensure dev stack is running**

```bash
./debug.sh
```

**Step 2: Login to CLI**

```bash
cd /home/jack/GitHub/bifrost-workspace
bifrost login --url http://localhost:3000
```

**Step 3: Run sync preview**

```bash
bifrost sync --preview
```

Verify:
- No preflight errors
- Expected pull/push counts make sense
- No broken references

**Step 4: Run actual sync**

```bash
bifrost sync
```

Verify:
- Sync completes without error
- Check the DB (via docker exec into postgres) that:
  - Agents have tool associations
  - Forms have field definitions
  - Apps have correct metadata

**Step 5: Verify via SQL**

```bash
docker exec -it bifrost-dev-postgres-1 psql -U bifrost -d bifrost -c "
  SELECT a.name, COUNT(at.workflow_id) as tools
  FROM agents a
  LEFT JOIN agent_tools at ON a.id = at.agent_id
  WHERE a.is_active = true
  GROUP BY a.name;
"
```

```bash
docker exec -it bifrost-dev-postgres-1 psql -U bifrost -d bifrost -c "
  SELECT f.name, COUNT(ff.id) as fields
  FROM forms f
  LEFT JOIN form_fields ff ON f.id = ff.form_id
  WHERE f.is_active = true
  GROUP BY f.name;
"
```

---

## Task 10: Pre-Completion Verification

**Step 1: Backend checks**

```bash
cd /home/jack/GitHub/bifrost/api
pyright
ruff check .
```

**Step 2: Frontend type generation (if API models changed)**

```bash
cd /home/jack/GitHub/bifrost/client
npm run generate:types
npm run tsc
npm run lint
```

**Step 3: Full test suite**

```bash
cd /home/jack/GitHub/bifrost
./test.sh
```

**Step 4: Commit any remaining changes**

---

## Dependency Graph

```
Task 1 (Fix agent import) ──┐
Task 2 (Fix form import)  ──┤
Task 3 (Agent tools alias) ─┤──→ Task 8 (E2E round-trip tests)
Task 4 (Form field aliases) ─┤
Task 5 (Sync endpoints)   ──┘──→ Task 9 (Manual sync validation)
                                      │
Task 6 (Update workspace agents) ─────┤
Task 7 (Update workspace forms)  ─────┘──→ Task 10 (Verification)
```

Tasks 1-5 can be worked in parallel (no dependencies). Tasks 6-7 can be done in parallel. Task 8 depends on 1-4. Task 9 depends on 5-7. Task 10 is the final gate.
