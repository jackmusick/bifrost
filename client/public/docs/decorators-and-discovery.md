# Decorators and Discovery System

## Overview

Bifrost uses a decorator-based system to automatically discover and register workflows and data providers from workspace directories. Parameters are automatically derived from function signatures - no additional decorators needed.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  1. App Startup                                             │
│     - Initializes API server                                │
│     - Calls discover_workspace_modules()                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  2. Workspace Discovery                                     │
│     - Scans workspace directories                           │
│     - Finds all *.py files (except __init__.py)             │
│     - Imports each file as a module                         │
│     - No __init__.py files required!                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  3. Decorator Execution (sdk/decorators.py)                 │
│     - @workflow and @data_provider decorators run           │
│     - Parameters extracted from function signatures         │
│     - Metadata is registered in WorkflowRegistry            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  4. Registry Storage (shared/registry.py)                   │
│     - WorkflowRegistry (singleton, thread-safe)             │
│     - Stores WorkflowMetadata (dataclass)                   │
│     - Stores DataProviderMetadata (dataclass)               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  5. API Endpoints                                           │
│     - GET /api/discovery → get_discovery_metadata()         │
│     - GET /api/data-providers → list_data_providers()       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  6. Model Conversion (shared/handlers/discovery_handlers.py)│
│     - convert_registry_workflow_to_model()                  │
│     - convert_registry_provider_to_model()                  │
│     - Converts dataclass → Pydantic model for API           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  7. Client Consumption                                       │
│     - Form builder fetches data providers                   │
│     - Workflow UI shows available workflows                 │
│     - Type-safe API responses (Pydantic validated)          │
└─────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Workspace Discovery

**What it does**:

- Scans workspace directories recursively
- Finds all `.py` files (except those starting with `_`)
- Imports each file using `importlib`
- Module names follow pattern: `workspace.{path}.{filename}`

**Example**:

```
File: workspace/workflows/my_workflow.py
Module name: workspace.workflows.my_workflow
```

**Key characteristics**:

- No `__init__.py` files required
- Hot-reload friendly (paths determined dynamically)

### 2. The `@workflow` Decorator

**Location**: `sdk/decorators.py`

**What it does**:

1. Wraps your async function
2. Extracts parameters from function signature (type hints)
3. Collects metadata (name from function, description from docstring)
4. Registers function in `WorkflowRegistry`
5. Returns the original function (unmodified)

**Example**:

```python
from bifrost import workflow

@workflow
async def process_order(order_id: str, priority: str = "normal") -> dict:
    """Process customer order."""
    # Your logic here
    return {"status": "processed"}
```

**Behind the scenes**:

```python
# Decorator extracts parameters from signature
# name = "process_order" (from function name)
# description = "Process customer order." (from docstring)
# parameters extracted from: order_id: str, priority: str = "normal"

metadata = WorkflowMetadata(
    name="process_order",
    description="Process customer order.",
    parameters=[
        WorkflowParameter(name="order_id", type="string", required=True),
        WorkflowParameter(name="priority", type="string", required=False, default_value="normal")
    ],
    function=process_order  # Your actual function
)

# Registers in singleton registry
get_registry().register_workflow(metadata)
```

### 3. The `@data_provider` Decorator

**Location**: `sdk/decorators.py`

**What it does**:

1. Wraps your async function
2. Extracts parameters from function signature
3. Collects metadata (name, description from docstring, cache TTL)
4. Registers function in `WorkflowRegistry`
5. Returns the original function (unmodified)

**Example**:

```python
from bifrost import data_provider

@data_provider(cache_ttl_seconds=300)
async def get_github_repos(token: str, org: str = "") -> list[dict]:
    """Get GitHub repositories."""
    # Your logic here
    return [
        {"label": "repo-1", "value": "org/repo-1"},
        {"label": "repo-2", "value": "org/repo-2"}
    ]
```

### 4. Parameter Extraction from Signatures

Parameters are automatically extracted from your function signature:

```python
@workflow
async def create_user(
    email: str,                # Required string
    name: str,                 # Required string
    department: str = "IT",    # Optional with default
    active: bool = True,       # Optional boolean
    tags: list | None = None   # Optional list
) -> dict:
    """Create a new user."""
    pass
```

**Type mapping**:
- `str` → string input
- `int` → integer input
- `float` → decimal input
- `bool` → checkbox
- `dict` → JSON editor
- `list` → array input

**Labels** are auto-generated from parameter names:
- `first_name` → "First Name"
- `userEmail` → "User Email"

### 5. WorkflowRegistry (Singleton)

**Location**: `shared/registry.py`

**What it stores**:

```python
# Two dataclasses for metadata
@dataclass
class WorkflowMetadata:
    name: str
    description: str
    parameters: list[WorkflowParameter]
    function: Any  # The actual Python function
    # ... more fields

@dataclass
class DataProviderMetadata:
    name: str
    description: str
    parameters: list[WorkflowParameter]
    function: Any  # The actual Python function
    cache_ttl_seconds: int
```

**Thread safety**: Uses `threading.Lock()` for concurrent registration

**Singleton pattern**: Only one instance exists across the entire app

### 6. Model Conversion for API

**Location**: `shared/handlers/discovery_handlers.py`

**Why needed**:

- Registry uses **dataclasses** (lightweight, internal)
- API needs **Pydantic models** (validation, serialization, OpenAPI)

**Conversion flow**:

```python
# Registry dataclass (internal)
@dataclass
class DataProviderMetadata:
    parameters: list[WorkflowParameter]  # Python list

# Pydantic model (API)
class DataProviderMetadata(BaseModel):
    parameters: list[WorkflowParameter] = Field(...)  # Validated list

# Conversion function
def convert_registry_provider_to_model(registry_provider):
    # Maps dataclass fields → Pydantic model fields
    # Handles snake_case → camelCase (e.g., cache_ttl_seconds → cacheTtlSeconds)
    # Converts parameter objects to dicts
    return DataProviderMetadata(
        name=registry_provider.name,
        parameters=[param_to_dict(p) for p in registry_provider.parameters]
    )
```

## Data Flow Example: Form with Data Provider

### Step 1: User creates form in UI

```json
{
    "name": "Create Ticket",
    "formSchema": {
        "fields": [
            {
                "name": "priority",
                "type": "select",
                "data_provider_id": "uuid-of-get-priority-levels",
                "data_provider_inputs": {
                    "filter": "{{status}}"
                }
            }
        ]
    }
}
```

### Step 2: Form validation (create/update)

**Location**: `shared/handlers/forms_handlers.py`

```python
# Validates that data provider exists
provider = registry.get_data_provider(data_provider_id)
if not provider:
    raise ValidationError("Unknown provider")

# Validates required parameters are configured
for param in provider.parameters:
    if param.required and param.name not in field.data_provider_inputs:
        raise ValidationError(f"Missing required parameter: {param.name}")
```

### Step 3: Form startup (when user opens form)

```python
# For each field with data_provider_id
for field in form.fields:
    if field.data_provider_id:
        # Resolve inputs (static values, field references like {{field_name}})
        inputs = resolve_data_provider_inputs(field.data_provider_inputs, context)

        # Call data provider
        options = await call_data_provider(field.data_provider_id, inputs, context)

        # Return options to client
        response["fields"][field.name]["options"] = options
```

### Step 4: Data provider execution

**Location**: `shared/handlers/data_providers_handlers.py`

```python
async def get_data_provider_options_handler(
    provider_id: str,
    inputs: dict,
    context: RequestContext
):
    # Get provider from registry
    provider = registry.get_data_provider(provider_id)

    # Validate inputs against parameters
    errors = validate_data_provider_inputs(provider, inputs)
    if errors:
        return {"error": "ValidationError", "details": errors}, 400

    # Check cache
    cache_key = compute_cache_key(provider_id, inputs, context.org_id)
    cached = get_from_cache(cache_key)
    if cached:
        return cached, 200

    # Call provider function with inputs as kwargs
    options = await provider.function(**inputs)

    # Cache result
    set_cache(cache_key, options, ttl=provider.cache_ttl_seconds)

    return {"provider_id": provider_id, "options": options}, 200
```

## Key Design Decisions

### 1. Why dataclass for registry + Pydantic for API?

**Registry (dataclass)**:

- Lightweight (no validation overhead during registration)
- Fast (no serialization needed)
- Mutable (can attach `function` reference)

**API (Pydantic)**:

- Validation (ensures API contracts)
- Serialization (automatic JSON conversion)
- OpenAPI (generates API documentation)

### 2. Why singleton registry?

- **Global state**: All modules register to same registry
- **Thread safety**: Multiple imports during startup
- **Performance**: No repeated initialization

### 3. Why no __init__.py required?

- **User experience**: Drop files, they just work
- **Hot reload**: No module structure to maintain
- **Flexibility**: Mix Python packages and standalone files

### 4. Why extract parameters from signatures?

- **DRY**: Define parameters once in the function signature
- **Type safety**: Python type hints provide validation
- **IDE support**: Full autocomplete and type checking
- **Less boilerplate**: No separate parameter decorators needed

## Troubleshooting

### Provider not showing up in /api/data-providers

1. **Check file is being imported**:
    - Look for startup logs: `✓ Discovered: workspace.providers.my_provider`
    - If missing: File starts with `_` or import failed

2. **Check decorator is correct**:

    ```python
    from bifrost import data_provider  # Correct
    ```

3. **Check registry**:
    ```python
    from shared.registry import get_registry
    registry = get_registry()
    providers = registry.get_all_data_providers()
    print([p.name for p in providers])
    ```

### Parameters not showing up

1. **Check function has type hints**:

    ```python
    @data_provider
    async def test(field: str) -> list[dict]:  # Type hint required
        pass
    ```

2. **Check parameters have correct types**:
    - Use `str`, `int`, `float`, `bool`, `list`, `dict`
    - Optional parameters need defaults: `field: str = "default"`

## Related Files

- **Decorators**: `sdk/decorators.py`
- **Registry**: `shared/registry.py`
- **Discovery**: `shared/discovery.py`
- **API Endpoints**:
    - `src/routers/discovery.py`
    - `src/routers/data_providers.py`
- **Handlers**:
    - `shared/handlers/discovery_handlers.py`
    - `shared/handlers/data_providers_handlers.py`
    - `shared/handlers/forms_handlers.py`
- **Models**: `shared/models.py`
