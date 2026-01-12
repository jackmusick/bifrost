# Forms & Agents Type Unification Plan

## Current Status (2026-01-11)

### Completed Tasks
- [x] **Phase 1.2**: Form field descriptions added to `forms.py`
- [x] **Phase 2.1**: `FormField.options` typed as `list[FormFieldOption]`
- [x] **Phase 2.2**: `FormField.validation` typed as `FormFieldValidation | None`
- [x] **Phase 3.1**: `CamelModel` already exists in `base.py`
- [x] **Phase 3.2**: Forms models migrated to `CamelModel` (FormField, FormSchema, FormPublic, etc.)
- [x] **Phase 6.1**: AGENT tool category added (agents.py MCP tools exist)

### Blocking Issue: FormFieldOption Serialization Bug

**Test Failures**: 28 tests broken (14 failures + 14 errors)

**Root Cause**: `TypeError: Object of type FormFieldOption is not JSON serializable`

**Location**: `api/src/routers/forms.py` line 108

When converting `FormSchema` to ORM fields, Pydantic model instances are assigned directly to JSONB columns instead of being serialized:

```python
# CURRENT (broken)
field_orm = FormFieldORM(
    ...
    options=field.options,           # list[FormFieldOption] - Pydantic models!
    validation=field.validation,     # FormFieldValidation | None - Pydantic model!
    ...
)

# FIXED
field_orm = FormFieldORM(
    ...
    options=[opt.model_dump(mode="json") for opt in field.options] if field.options else None,
    validation=field.validation.model_dump(mode="json") if field.validation else None,
    ...
)
```

**Affected Files**:
- `api/src/routers/forms.py`: `_form_schema_to_fields()` function
- Possibly `api/src/models/contracts/forms.py`: `FormExport.from_form_orm()` if reading back

### Pending Work

1. **Fix serialization bug** (URGENT)
   - Update `_form_schema_to_fields()` to serialize Pydantic models before ORM assignment
   - Run tests to verify fix

2. **GitHub Sync not including forms/agents in comparison**
   - Forms/agents are DB entities, not workspace_files traditionally
   - `_get_local_file_shas()` only queries `WorkspaceFile` table
   - Need to either:
     a. Ensure forms/agents are tracked in workspace_files when created/updated, OR
     b. Add separate query for entity files in `get_sync_preview()`

3. **Frontend conflict handling incomplete**
   - UI components for conflict resolution may need additional work
   - Need to verify frontend can display and resolve conflicts properly

---

## Goal

Bring forms and agents to the same level of type safety and documentation as `app_builder_types.py`:
1. **Self-documenting schemas** - All fields have `Field(description=...)` for JSON schema generation
2. **No undocumented dicts** - Replace `dict[str, Any]` with typed models where possible
3. **Consistent patterns** - Use `CamelModel`, Literal types, and nested models
4. **MCP tool coverage** - Add missing agent MCP tools with Pydantic validation

## Current State Analysis

| Aspect | App Builder | Forms | Agents |
|--------|-------------|-------|--------|
| Field descriptions | Docstrings (not in schema) | ✅ ~95% coverage | ~90% coverage |
| `dict[str, Any]` usage | Minimal, intentional | ✅ Typed models | Clean |
| CamelModel base | Yes | ✅ Yes | No |
| Literal type aliases | Extensive | ✅ FormFieldType enum | Minimal |
| MCP tools | Extensive | ✅ 5 tools | ✅ Tools exist |
| MCP validation | `validation.py` | Inline | N/A |

### Key Finding: Docstrings Don't Generate Schema Descriptions

The current pattern in `app_builder_types.py`:
```python
items: str
"""Expression that evaluates to an array"""
```

Does NOT include the description in JSON schema. Only `Field(description=...)` does:
```python
items: str = Field(description="Expression that evaluates to an array")
```

---

## Phase 1: Add Field Descriptions to All Models

**Priority: HIGH** - This is the foundation for self-documenting APIs

### Task 1.1: Update `app_builder_types.py` with Field Descriptions

Convert all field docstrings to `Field(description=...)`:

```python
# Before
class RepeatFor(CamelModel):
    items: str
    """Expression that evaluates to an array"""

# After
class RepeatFor(CamelModel):
    items: str = Field(description="Expression that evaluates to an array")
```

**Scope**: ~150 fields across 50+ models

**Files**:
- `api/src/models/contracts/app_builder_types.py`

### Task 1.2: Update `forms.py` with Field Descriptions ✅ DONE

Add descriptions to all fields, focusing on:
- `FormField.type` - "Field type (text, number, select, etc.)"
- `FormField.validation` - "Validation rules for this field"
- `FormField.options` - "Options for select/radio fields"
- `FormSchema.fields` - "List of form fields"
- All `default_launch_params` fields

**Files**:
- `api/src/models/contracts/forms.py`

### Task 1.3: Update `agents.py` with Field Descriptions

Add descriptions to fields missing them:
- `ToolCall.arguments` - "Arguments to pass to the tool as key-value pairs"
- `ToolResult.result` - "Result from tool execution (structure varies by tool)"
- `AgentCreate` fields
- `ChatStreamChunk` fields

**Files**:
- `api/src/models/contracts/agents.py`

---

## Phase 2: Type Undocumented Dicts

**Priority: HIGH** - Eliminate loose typing that can't be validated

### Task 2.1: Type `FormField.options` ✅ DONE

**Current**: `list[dict[str, str]]`
**Change to**: `list[FormFieldOption]`

```python
class FormFieldOption(CamelModel):
    """Option for select, radio, or checkbox fields."""
    value: str = Field(description="Value submitted when this option is selected")
    label: str = Field(description="Display label shown to user")
```

**⚠️ REQUIRES FIX**: ORM assignment must serialize to dict before storing in JSONB column.

### Task 2.2: Type `FormField.validation` ✅ DONE

**Current**: `dict[str, Any] | None`
**Change to**: `FormFieldValidation | None`

```python
class FormFieldValidation(CamelModel):
    """Form field validation rules"""
    pattern: str | None = Field(default=None, description="Regex pattern for validation")
    min: float | None = Field(default=None, description="Minimum value for numeric fields")
    max: float | None = Field(default=None, description="Maximum value for numeric fields")
    message: str | None = Field(default=None, description="Custom error message when validation fails")
```

**⚠️ REQUIRES FIX**: ORM assignment must serialize to dict before storing in JSONB column.

### Task 2.3: Audit `default_launch_params`

**Current**: `dict[str, Any]` or untyped `dict`
**Options**:
1. Keep as `dict[str, Any]` but document structure
2. Create `LaunchParams` model if structure is predictable

**Decision**: Review usage to determine if typing is feasible or if it's truly dynamic.

---

## Phase 3: Adopt CamelModel Pattern

**Priority: MEDIUM** - Consistency and frontend compatibility

### Task 3.1: Create Shared CamelModel Base ✅ DONE

`CamelModel` already exists in `api/src/models/contracts/base.py`:

```python
class CamelModel(BaseModel):
    """Base model with camelCase serialization."""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )
```

### Task 3.2: Migrate Forms Models to CamelModel ✅ DONE

Updated models that serialize to frontend:
- `FormField` - using CamelModel
- `FormFieldOption` - using CamelModel
- `FormFieldValidation` - using CamelModel
- `FormSchema` - using CamelModel
- `FormPublic` - using CamelModel
- `DataProviderInputConfig` - using CamelModel

Export/Import models stay as BaseModel (use snake_case for portability)

### Task 3.3: Migrate Agents Models to CamelModel

Update models that serialize to frontend:
- `AgentPublic`
- `ChatStreamChunk`
- `ToolCall`
- `MessagePublic`

---

## Phase 4: Add Literal Type Aliases

**Priority: MEDIUM** - Improves type safety and IDE support

### Task 4.1: Extract Forms Literals ✅ DONE

Forms use `FormFieldType` enum from `src.models.enums` and `DataProviderInputMode` from base.py.

### Task 4.2: Review Agents Literals

Agents already have good enum usage (`AgentChannel`, `MessageRole`). Verify coverage is complete.

---

## Phase 5: Clean Up Frontend Type Duplication

**Priority: MEDIUM** - Remove manual types that duplicate generated ones

### Task 5.1: Audit `client/src/lib/client-types.ts`

**Current issues** (lines 33-117):
- Manual `FormFieldType`, `FormField`, `FormSchema` definitions
- These duplicate auto-generated types in `v1.d.ts`

**Change to**:
```typescript
// Re-export from generated types instead of duplicating
import type { components } from "./v1";

export type FormFieldType = components["schemas"]["FormFieldType"];
export type FormField = components["schemas"]["FormField-Output"];
export type FormSchema = components["schemas"]["FormSchema-Output"];
```

### Task 5.2: Regenerate Types After Backend Changes

After all backend model updates:
```bash
cd client && npm run generate:types
```

Verify frontend still compiles with `npm run tsc`.

---

## Phase 6: Add Agent MCP Tools

**Priority: LOW** (but important for completeness)

### Task 6.1: Add `AGENT` Tool Category ✅ DONE

Agent MCP tools exist in `api/src/services/mcp_server/tools/agents.py`

### Task 6.2: Create `agents.py` MCP Tools ✅ DONE

Tools implemented in `agents.py`:
| Tool | Description |
|------|-------------|
| `list_agents` | List all agents accessible to the user |
| `get_agent` | Get agent details by ID |
| `create_agent` | Create agent with validation |
| `update_agent` | Update agent with validation |
| `delete_agent` | Delete an agent |

### Task 6.3: Add Validation Helpers

**File**: `api/src/services/mcp_server/tools/validation.py`

Add functions similar to app_builder:
```python
def validate_agent_config(config: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate agent configuration using AgentCreate model."""
    try:
        AgentCreate.model_validate(config)
        return True, None
    except ValidationError as e:
        return False, f"Invalid agent config: {_format_validation_errors(e.errors())}"
```

---

## Phase 7: Verification

### Task 7.1: Backend Verification

```bash
cd api
pyright                    # Type checking
ruff check .               # Linting
./test.sh                  # All tests pass
```

### Task 7.2: Frontend Verification

```bash
cd client
npm run generate:types     # Regenerate from updated models
npm run tsc                # Type checking
npm run lint               # Linting
```

### Task 7.3: Schema Verification

Verify JSON schemas include descriptions:
```python
from src.models.contracts.forms import FormField
import json
schema = FormField.model_json_schema()
# Verify all properties have "description" key
```

---

## File Summary

| File | Phase | Changes | Status |
|------|-------|---------|--------|
| `api/src/models/contracts/app_builder_types.py` | 1.1 | Add Field descriptions (~150 fields) | Pending |
| `api/src/models/contracts/forms.py` | 1.2, 2.1-2.3, 3.2, 4.1 | Add descriptions, type dicts, adopt CamelModel | ✅ Done |
| `api/src/models/contracts/agents.py` | 1.3, 3.3 | Add descriptions, adopt CamelModel | Pending |
| `api/src/models/contracts/base.py` | 3.1 | Create shared CamelModel | ✅ Done |
| `api/src/routers/forms.py` | 2.1, 2.2 | **FIX**: Serialize Pydantic models before ORM | **URGENT** |
| `api/src/services/mcp_server/tool_registry.py` | 6.1 | Add AGENT category | ✅ Done |
| `api/src/services/mcp_server/tools/agents.py` | 6.2 | Agent MCP tools | ✅ Done |
| `api/src/services/mcp_server/tools/validation.py` | 6.3 | Add agent validation helpers | Pending |
| `client/src/lib/client-types.ts` | 5.1 | Remove duplicates, re-export from v1.d.ts | Pending |

---

## Success Criteria

- [x] All Pydantic model fields have `Field(description=...)` for forms
- [ ] All Pydantic model fields have `Field(description=...)` for agents
- [ ] All Pydantic model fields have `Field(description=...)` for app_builder_types
- [x] `model_json_schema()` includes descriptions for form fields
- [x] No `dict[str, Any]` without clear justification in forms
- [x] Forms use `CamelModel` for frontend-facing models
- [ ] Agents use `CamelModel` for frontend-facing models
- [ ] `client-types.ts` has no manual type definitions that duplicate `v1.d.ts`
- [x] Agent MCP tools exist with CRUD operations
- [ ] **All verification passes (pyright, tsc, lint, tests)** - BLOCKED by serialization bug

---

## Next Steps

1. **URGENT**: Fix the FormFieldOption/FormFieldValidation serialization bug in `forms.py` router
2. Run tests to verify fix
3. Address GitHub sync entity tracking (forms/agents in workspace_files)
4. Complete frontend conflict handling UI
5. Continue with remaining tasks (app_builder_types descriptions, agents CamelModel, etc.)

---

## Execution Order

1. **Phase 1** (Field Descriptions) - Foundation, do first
2. **Phase 2** (Type Dicts) - ✅ Done but needs serialization fix
3. **Phase 3** (CamelModel) - ✅ Done for forms
4. **Phase 4** (Literals) - ✅ Done for forms
5. **Phase 5** (Frontend Cleanup) - After backend changes complete
6. **Phase 6** (MCP Tools) - ✅ Done
7. **Phase 7** (Verification) - BLOCKED by serialization bug

**Estimated remaining scope**: ~300 lines of changes across 5 files
