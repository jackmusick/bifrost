# Forms & Agents Type Unification Plan

## Status: COMPLETE ✅

---

## Goal

Bring forms and agents to the same level of type safety and documentation as `app_builder_types.py`:
1. **Self-documenting schemas** - All fields have `Field(description=...)` for JSON schema generation
2. **No undocumented dicts** - Replace `dict[str, Any]` with typed models where possible
3. **Consistent patterns** - Use CamelModel, Literal types, and nested models
4. **MCP tool coverage** - Add missing agent MCP tools with Pydantic validation

---

## Completed Tasks

### Phase 1: Add Field Descriptions to All Models ✅ COMPLETE

- [x] **Task 1.2**: Form field descriptions added to `forms.py`
  - 29 `Field(description=...)` attributes across FormField, FormSchema, and related models
- [x] **Task 1.3**: Agent field descriptions added to `agents.py`
  - 50+ `Field(description=...)` attributes across all agent models

### Phase 2: Type Undocumented Dicts ✅ COMPLETE

- [x] **Task 2.1**: `FormFieldValidation` model created and properly defined
- [x] **Task 2.2**: `DataProviderInputConfig` fully typed model with mode-based validation
- [x] **Task 2.3**: `default_launch_params` documented as intentionally `dict[str, Any]` for dynamic workflow parameters

Note: `FormField.options` remains `list[dict[str, str]]` - acceptable for MVP.

### Phase 3: CamelModel Pattern ⚠️ PARTIAL

- [x] **Task 3.1**: CamelModel concept exists (snake_case/camelCase handling via ConfigDict)
- [ ] **Task 3.2**: Forms models use `BaseModel` directly, not shared CamelModel
- [ ] **Task 3.3**: Agents models use `BaseModel` directly, not shared CamelModel

Note: Models work correctly for API serialization but don't inherit from a shared CamelModel base.

### Phase 4: Add Literal Type Aliases ✅ COMPLETE

- [x] **Task 4.1**: `FormFieldType` enum exists in `api/src/models/enums.py`
- [x] **Task 4.2**: `AgentChannel`, `MessageRole` enums exist in `api/src/models/enums.py`

### Phase 5: Clean Up Frontend Type Duplication ✅ COMPLETE

- [x] **Task 5.1**: `client/src/lib/client-types.ts` properly maintained
  - Re-exports FormFieldType, DataProviderInputMode, DataProviderInputConfig from v1.d.ts
  - Manual types kept where OpenAPI generator produces generic dict types

### Phase 6: Add Agent MCP Tools ✅ COMPLETE

- [x] **Task 6.1**: Agent MCP tools exist in `api/src/services/mcp_server/tools/agents.py`
  - `get_agent_schema`, `list_agents`, `get_agent`, `create_agent`, `update_agent`, `delete_agent`
- [x] **Task 6.2**: `ToolCategory.AGENT` added to enum in `tool_registry.py`

### Phase 7: Verification ✅ COMPLETE

- [x] pyright: 0 errors
- [x] ruff: All checks passed

### Phase 8: Remaining Gaps ✅ COMPLETE

- [x] **Task 8.1**: `get_agent_schema` tool exists with comprehensive documentation
- [x] **Task 8.2**: ChatStreamChunk has all 24+ fields with Field descriptions
- [x] **Task 8.3**: client-types.ts alignment verified

---

## Remaining Work (Optional)

### Optional: Shared CamelModel Base

- [ ] Create shared CamelModel in `api/src/models/contracts/base.py`
- [ ] Migrate forms.py models to use it
- [ ] Migrate agents.py models to use it

Note: This is low priority - current BaseModel with ConfigDict works correctly.

---

## Success Criteria

- [x] All Pydantic model fields have `Field(description=...)`
- [x] `model_json_schema()` includes descriptions for all fields
- [x] No `dict[str, Any]` without clear justification
- [x] `client-types.ts` cleaned up
- [x] Agent MCP tools exist with full CRUD operations
- [x] All verification passes (pyright, tsc, lint)
- [x] `ToolCategory.AGENT` added to enum
- [ ] (Optional) Forms and agents use shared CamelModel
