# Forms & Agents Type Unification Plan

## Goal

Bring forms and agents to the same level of type safety and documentation as `app_builder_types.py`:
1. **Self-documenting schemas** - All fields have `Field(description=...)` for JSON schema generation
2. **No undocumented dicts** - Replace `dict[str, Any]` with typed models where possible
3. **Consistent patterns** - Use `CamelModel`, Literal types, and nested models
4. **MCP tool coverage** - Add missing agent MCP tools with Pydantic validation

## Current State Analysis

| Aspect | App Builder | Forms | Agents |
|--------|-------------|-------|--------|
| Field descriptions | ✅ Field(description=...) | ✅ Complete | ✅ Complete |
| `dict[str, Any]` usage | Minimal, intentional | ✅ Typed | Clean |
| CamelModel base | ✅ Yes | ✅ Yes | ✅ Yes |
| Literal type aliases | Extensive | ✅ FormFieldType | ✅ AgentChannel, MessageRole |
| MCP tools | Extensive | 5 tools | ✅ 6 tools |
| get_*_schema tool | ✅ get_app_schema | ✅ get_form_schema | ✅ get_agent_schema |

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

## Tasks

### Phase 1: Add Field Descriptions to All Models ✅ COMPLETE

**Priority: HIGH** - This is the foundation for self-documenting APIs

- [x] **Task 1.1**: Update `app_builder_types.py` with Field descriptions (~150 fields)
  - Convert all field docstrings to `Field(description=...)`
  - File: `api/src/models/contracts/app_builder_types.py`

- [x] **Task 1.2**: Update `forms.py` with Field descriptions
  - `FormField.type` - "Field type (text, number, select, etc.)"
  - `FormField.validation` - "Validation rules for this field"
  - `FormField.options` - "Options for select/radio fields"
  - `FormSchema.fields` - "List of form fields"
  - All `default_launch_params` fields
  - File: `api/src/models/contracts/forms.py`

- [x] **Task 1.3**: Update `agents.py` with Field descriptions
  - `ToolCall.arguments` - "Arguments to pass to the tool as key-value pairs"
  - `ToolResult.result` - "Result from tool execution (structure varies by tool)"
  - `AgentCreate` fields
  - `ChatStreamChunk` fields
  - File: `api/src/models/contracts/agents.py`

---

### Phase 2: Type Undocumented Dicts ✅ COMPLETE

**Priority: HIGH** - Eliminate loose typing that can't be validated

- [x] **Task 2.1**: Type `FormField.options`
  - Current: `list[dict[str, str]]`
  - Change to: `list[FormFieldOption]`
  - Create `FormFieldOption` model with `value` and `label` fields

- [x] **Task 2.2**: Type `FormField.validation`
  - Current: `dict[str, Any] | None`
  - Change to: `FormFieldValidation | None` (model already exists, verify and use)

- [x] **Task 2.3**: Audit `default_launch_params`
  - Current: `dict[str, Any]` or untyped `dict`
  - Decision: Keep as `dict[str, Any]` - truly dynamic workflow parameters
  - Add description documenting this is intentionally dynamic

---

### Phase 3: Adopt CamelModel Pattern ✅ COMPLETE

**Priority: MEDIUM** - Consistency and frontend compatibility

- [x] **Task 3.1**: Create shared CamelModel base
  - Create `api/src/models/contracts/base.py`
  - Move `CamelModel` from `app_builder_types.py`

- [x] **Task 3.2**: Migrate Forms models to CamelModel
  - `FormField`
  - `FormSchema`
  - `FormPublic`
  - Export/Import models stay as-is (snake_case for portability)

- [x] **Task 3.3**: Migrate Agents models to CamelModel
  - `AgentPublic`
  - `ChatStreamChunk`
  - `ToolCall`
  - `MessagePublic`

---

### Phase 4: Add Literal Type Aliases ✅ COMPLETE

**Priority: MEDIUM** - Improves type safety and IDE support

- [x] **Task 4.1**: Review Forms Literals
  - Verified `FormFieldType` enum exists in `enums.py`

- [x] **Task 4.2**: Review Agents Literals
  - Verified `AgentChannel`, `MessageRole` exist in `enums.py`

---

### Phase 5: Clean Up Frontend Type Duplication ✅ COMPLETE

**Priority: MEDIUM** - Remove manual types that duplicate generated ones

- [x] **Task 5.1**: Audit `client/src/lib/client-types.ts`
  - Re-exported `FormFieldType`, `DataProviderInputMode`, `DataProviderInputConfig` from v1.d.ts
  - Note: `FormFieldOption`, `FormFieldValidation`, `FormField`, `FormSchema` kept manual due to OpenAPI generator producing generic dict types instead of specific models

- [x] **Task 5.2**: Regenerate types after backend changes
  - Regenerated types and fixed 135 snake_case → camelCase frontend errors

---

### Phase 6: Add Agent MCP Tools ✅ COMPLETE

**Priority: LOW** (but important for completeness)

- [x] **Task 6.1**: Add `AGENT` tool category
  - File: `api/src/services/mcp_server/tool_registry.py`

- [x] **Task 6.2**: Create Agent MCP tools
  - File: `api/src/services/mcp_server/tools/agents.py` (NEW)
  - Tools: `list_agents`, `get_agent`, `create_agent`, `update_agent`, `delete_agent`
  - Note: Tool assignment managed via create/update with tool_ids parameter

- [x] **Task 6.3**: Add agent validation helpers
  - Validation is done inline in create/update tools using model validation
  - Follows same pattern as other MCP tools

---

### Phase 7: Verification ✅ COMPLETE

- [x] **Task 7.1**: Backend verification
  - pyright: 0 errors (1 warning for psutil - expected)
  - ruff: All checks passed

- [x] **Task 7.2**: Frontend verification
  - npm run generate:types: Success
  - npm run tsc: 0 errors
  - npm run lint: 0 errors (2 pre-existing warnings)

- [x] **Task 7.3**: Schema verification
  - Verified `model_json_schema()` includes descriptions for all fields

---

### Phase 8: Remaining Gaps (From Review)

**Priority: MEDIUM** - For consistency and completeness

- [x] **Task 8.1**: Add `get_agent_schema` MCP tool ✅ COMPLETE
  - Added for consistency with `get_app_schema`, `get_form_schema`, `get_workflow_schema`
  - Returns Pydantic-generated JSON schema for AgentCreate/AgentPublic
  - File: `api/src/services/mcp_server/tools/agents.py`
  - Includes comprehensive documentation for channels, tool assignment, delegation

- [x] **Task 8.2**: Review ChatStreamChunk completeness ✅ COMPLETE
  - All 24 fields have Field(description=...)
  - Discriminated union with 16 chunk types (Literal type field)
  - Proper CamelModel inheritance
  - No changes needed - model is complete

- [x] **Task 8.3**: Verify client-types.ts alignment ✅ COMPLETE
  - All manual types (FormFieldOption, FormFieldValidation, FormField, FormSchema) align correctly
  - Field names match with proper camelCase conversion
  - Manual types remain valuable for cleaner imports and protecting against generic dict unions
  - No updates needed

---

## Files Summary

| File | Tasks | Changes |
|------|-------|---------|
| `api/src/models/contracts/app_builder_types.py` | 1.1 | Add Field descriptions (~150 fields) |
| `api/src/models/contracts/forms.py` | 1.2, 2.1-2.3, 3.2 | Add descriptions, type dicts, CamelModel |
| `api/src/models/contracts/agents.py` | 1.3, 3.3 | Add descriptions, CamelModel |
| `api/src/models/contracts/base.py` | 3.1 | **NEW** - Shared CamelModel |
| `api/src/services/mcp_server/tool_registry.py` | 6.1 | Add AGENT category |
| `api/src/services/mcp_server/tools/agents.py` | 6.2 | **NEW** - Agent MCP tools |
| `api/src/services/mcp_server/tools/validation.py` | 6.3 | Add agent validation helpers |
| `client/src/lib/client-types.ts` | 5.1 | Remove duplicates, re-export from v1.d.ts |

---

## Success Criteria

- [x] All Pydantic model fields have `Field(description=...)`
- [x] `model_json_schema()` includes descriptions for all fields
- [x] No `dict[str, Any]` without clear justification
- [x] Forms and agents use `CamelModel` for frontend-facing models
- [x] `client-types.ts` cleaned up (some manual types needed due to OpenAPI generator limitations)
- [x] Agent MCP tools exist with full CRUD operations
- [x] All verification passes (pyright, tsc, lint)

---

## Execution Order

1. **Phase 1** (Field Descriptions) - Foundation, do first
2. **Phase 2** (Type Dicts) - Can be done with Phase 1
3. **Phase 3** (CamelModel) - After 1 & 2, may cause serialization changes
4. **Phase 4** (Literals) - Low risk, verify coverage
5. **Phase 5** (Frontend Cleanup) - After backend changes complete
6. **Phase 6** (MCP Tools) - Independent, lowest priority
7. **Phase 7** (Verification) - Final step

**Estimated scope**: ~500 lines of changes across 8 files
