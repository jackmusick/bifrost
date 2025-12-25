"""
SDK Generator Service for Bifrost.

Generates Python SDK modules from OpenAPI specifications with integration-aware
authentication. Generated SDKs automatically fetch credentials from Bifrost
integrations at runtime.

Supported auth types:
- bearer: Authorization: Bearer {token}
- api_key: Custom header with API key (e.g., x-api-key)
- basic: Authorization: Basic {base64(username:password)}
- oauth: Uses Bifrost OAuth provider tokens
"""

import json
import logging
import re
from typing import Any, Literal

import requests
import yaml

logger = logging.getLogger(__name__)

AuthType = Literal["bearer", "api_key", "basic", "oauth"]


# =============================================================================
# Spec Loading
# =============================================================================


def load_spec_from_url(url: str) -> dict:
    """Load OpenAPI spec from a URL."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")

    if "json" in content_type or url.endswith(".json"):
        return response.json()
    else:
        return yaml.safe_load(response.text)


def load_spec_from_content(content: str, content_type: str = "json") -> dict:
    """Load OpenAPI spec from raw content."""
    if content_type == "json":
        return json.loads(content)
    else:
        return yaml.safe_load(content)


# =============================================================================
# Name Utilities
# =============================================================================


def to_snake_case(name: str) -> str:
    """Convert PascalCase or camelCase to snake_case."""
    s1 = re.sub("([a-z0-9])([A-Z])", r"\1_\2", name)
    s2 = re.sub("([A-Z]+)([A-Z][a-z])", r"\1_\2", s1)
    return s2.lower().replace("-", "_").replace(" ", "_")


def to_pascal_case(name: str) -> str:
    """Convert snake_case, kebab-case, or camelCase to PascalCase."""
    name = re.sub(r"\d+\.\d+", "", name)
    words = re.split(r"[_\-\s.]+", name)

    result_parts = []
    for word in words:
        if not word:
            continue
        if word.isupper() and len(word) > 1:
            result_parts.append(word)
        elif any(c.isupper() for c in word[1:]):
            camel_words = re.sub(
                "([A-Z][a-z]+)", r" \1", re.sub("([A-Z]+)", r" \1", word)
            ).split()
            for cw in camel_words:
                if cw:
                    result_parts.append(cw.capitalize())
        else:
            result_parts.append(word.capitalize())

    result = "".join(result_parts)
    result = re.sub(r"[^a-zA-Z0-9]", "", result)
    if result and result[0].isdigit():
        result = f"Api{result}"
    return result or "ApiClient"


def sanitize_class_name(name: str) -> str:
    """Sanitize a string to be a valid Python class name."""
    name = re.sub(r"\d+\.\d+", "", name)
    name = re.sub(r"[^a-zA-Z0-9]+", "", name)
    if name and name[0].isdigit():
        name = f"Api{name}"
    return name or "ApiClient"


def pluralize(word: str) -> str:
    """Convert a singular English word to its plural form."""
    if not word:
        return word

    if word.endswith("s") and not word.endswith(("ss", "us", "is", "os")):
        return word

    if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        return word[:-1] + "ies"

    if word.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"

    if word.endswith("f") and word not in ("roof", "proof", "chief", "belief"):
        return word[:-1] + "ves"

    if word.endswith("fe"):
        return word[:-2] + "ves"

    if word.endswith("o") and len(word) > 1 and word[-2] not in "aeiou":
        if word not in ("photo", "piano", "memo", "zoo"):
            return word + "es"

    return word + "s"


# =============================================================================
# Spec Sanitization
# =============================================================================


def _sanitize_value_recursive(value: Any) -> Any:
    """Recursively normalize OpenAPI type names."""
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            result[k] = _sanitize_value_recursive(v)

        if "type" in result and isinstance(result["type"], str):
            type_val = result["type"]

            if type_val.startswith("List<") and type_val.endswith(">"):
                inner_type = type_val[5:-1]
                inner_type_mapping = {
                    "int": "integer",
                    "bool": "boolean",
                    "float": "number",
                    "str": "string",
                    "string": "string",
                    "integer": "integer",
                    "boolean": "boolean",
                    "number": "number",
                }
                mapped_inner = inner_type_mapping.get(inner_type, inner_type)
                result["type"] = "array"
                result["items"] = {"type": mapped_inner}
            else:
                type_mapping = {
                    "int": "integer",
                    "bool": "boolean",
                    "float": "number",
                    "double": "number",
                    "str": "string",
                    "dict": "object",
                    "list": "array",
                    "DateTime": "string",
                    "datetime": "string",
                    "date": "string",
                    "Date": "string",
                }
                if type_val in type_mapping:
                    result["type"] = type_mapping[type_val]
                    if type_val in ["DateTime", "datetime"]:
                        result["format"] = "date-time"
                    elif type_val in ["date", "Date"]:
                        result["format"] = "date"

        return result
    elif isinstance(value, list):
        return [_sanitize_value_recursive(item) for item in value]
    else:
        return value


def sanitize_spec(spec: dict) -> dict:
    """Fix common OpenAPI spec issues by normalizing type names."""
    return _sanitize_value_recursive(spec)


# =============================================================================
# Type Generation
# =============================================================================


def python_type_from_schema(
    schema: dict[str, Any],
    components: dict,
    inline_schemas: dict[str, dict] | None = None,
    context_name: str | None = None,
) -> str:
    """Convert OpenAPI schema to Python type hint."""
    if not schema:
        return "Any"

    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        return to_pascal_case(ref_name)

    schema_type = schema.get("type", "object")

    if schema_type == "array":
        items = schema.get("items", {})
        item_context = f"{context_name}Item" if context_name else None
        item_type = python_type_from_schema(items, components, inline_schemas, item_context)
        return f"List[{item_type}]"
    elif schema_type == "object":
        properties = schema.get("properties", {})
        if properties and inline_schemas is not None and context_name:
            class_name = to_pascal_case(context_name)
            if class_name not in inline_schemas:
                inline_schemas[class_name] = schema
            return class_name
        else:
            return "Dict[str, Any]"
    elif schema_type == "integer":
        return "int"
    elif schema_type == "number":
        return "float"
    elif schema_type == "boolean":
        return "bool"
    elif schema_type == "string":
        return "str"
    else:
        return "Any"


# =============================================================================
# Dataclass Generation
# =============================================================================

PYTHON_KEYWORDS = {
    "and", "as", "assert", "break", "class", "continue", "def", "del", "elif",
    "else", "except", "False", "finally", "for", "from", "global", "if",
    "import", "in", "is", "lambda", "None", "nonlocal", "not", "or", "pass",
    "raise", "return", "True", "try", "while", "with", "yield", "async", "await",
}


def generate_dataclass(
    name: str,
    schema: dict[str, Any],
    components: dict,
    inline_schemas: dict[str, dict] | None = None,
) -> str:
    """Generate a dataclass from an OpenAPI schema."""
    class_name = to_pascal_case(name)
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    lines = ["@dataclass", f"class {class_name}:"]

    if not properties:
        lines.append("    pass")
        return "\n".join(lines)

    if "description" in schema:
        lines.append(f'    """{schema["description"]}"""')

    fields_required = []
    fields_optional = []

    for prop_name, prop_schema in properties.items():
        py_name = to_snake_case(prop_name)

        if py_name and py_name[0].isdigit():
            py_name = f"field_{py_name}"

        py_name = re.sub(r"^[^a-zA-Z_]", "_", py_name)
        py_name = re.sub(r"[^a-zA-Z0-9_]", "_", py_name)

        if py_name in PYTHON_KEYWORDS:
            py_name = f"{py_name}_"

        nested_context = (
            f"{class_name}{to_pascal_case(prop_name)}" if inline_schemas is not None else None
        )
        py_type = python_type_from_schema(prop_schema, components, inline_schemas, nested_context)

        desc = prop_schema.get("description", "")
        comment = f"  # {desc}" if desc else ""

        if prop_name not in required:
            py_type = f"Optional[{py_type}]"
            fields_optional.append(f"    {py_name}: {py_type} = None{comment}")
        else:
            fields_required.append(f"    {py_name}: {py_type}{comment}")

    for field in fields_required:
        lines.append(field)
    for field in fields_optional:
        lines.append(field)

    lines.append("")
    lines.append("    @classmethod")
    lines.append(f"    def from_dict(cls, data: Dict[str, Any]) -> '{class_name}':")
    lines.append("        if data is None:")
    lines.append("            return None")
    lines.append("        return cls(**{")

    for prop_name in properties.keys():
        py_name = to_snake_case(prop_name)
        lines.append(f"            '{py_name}': data.get('{prop_name}'),")

    lines.append("        })")

    return "\n".join(lines)


def generate_method_name(path: str, method: str) -> str:
    """Generate a clean method name from path and HTTP method."""
    clean_path = re.sub(r"\{[^}]+\}", "", path)
    parts = [p for p in clean_path.split("/") if p]

    resource = to_snake_case(parts[-1] if parts else "resource")
    resource = re.sub(r"[^a-zA-Z0-9_]", "_", resource)
    resource = resource.strip("_")

    if method == "get":
        if "{" in path:
            action = "get"
        else:
            action = "list"
            resource = pluralize(resource)
    elif method == "post":
        action = "create"
    elif method == "put":
        action = "update"
    elif method == "patch":
        action = "patch"
    elif method == "delete":
        action = "delete"
    else:
        action = method

    return f"{action}_{resource}"


# =============================================================================
# Client Generation
# =============================================================================


def generate_internal_client(spec: dict[str, Any], class_name: str) -> tuple[list[str], list[str]]:
    """Generate the internal client class with all API methods.

    Returns:
        Tuple of (lines of generated code, list of method names)
    """
    components = spec.get("components", {})
    paths = spec.get("paths", {})
    inline_schemas: dict[str, dict] = {}

    lines: list[str] = []

    # First pass: collect inline schemas from responses
    for path, path_item in paths.items():
        for http_method in ["get", "post", "put", "patch", "delete"]:
            if http_method not in path_item:
                continue

            operation = path_item[http_method]
            responses = operation.get("responses", {})

            for status_code in ["200", "201", "204", "default"]:
                response = responses.get(status_code)
                if not response:
                    continue

                content = response.get("content", {})
                json_content = content.get("application/json", {})
                schema = json_content.get("schema", {})

                if schema:
                    operation_id = operation.get("operationId")
                    if operation_id:
                        context_name = f"{to_pascal_case(operation_id)}Response"
                    else:
                        method_name = generate_method_name(path, http_method)
                        context_name = f"{to_pascal_case(method_name)}Response"

                    python_type_from_schema(schema, components, inline_schemas, context_name)

    # Generate dataclasses for component schemas
    schemas = components.get("schemas", {})
    if schemas:
        lines.append("# Data Models")
        lines.append("")

        for schema_name, schema_def in sorted(schemas.items()):
            if schema_def.get("type") == "object":
                lines.append(generate_dataclass(schema_name, schema_def, components, inline_schemas))
                lines.append("")
                lines.append("")

    # Generate inline response schemas
    if inline_schemas:
        lines.append("# Inline Response Models")
        lines.append("")

        generated_schemas: set[str] = set()
        while len(generated_schemas) < len(inline_schemas):
            for schema_name, schema_def in sorted(inline_schemas.items()):
                if schema_name not in generated_schemas:
                    lines.append(
                        generate_dataclass(schema_name, schema_def, components, inline_schemas)
                    )
                    lines.append("")
                    lines.append("")
                    generated_schemas.add(schema_name)

    # Generate internal client class
    lines.append("")
    lines.append(f"class _{class_name}Client:")
    lines.append(f'    """Internal client implementation for {class_name}."""')
    lines.append("")
    lines.append("    def __init__(self, base_url: str, session: requests.Session):")
    lines.append('        self.base_url = base_url.rstrip("/")')
    lines.append("        self.session = session")
    lines.append("")
    lines.append("    def _auto_convert(self, data):")
    lines.append('        """Automatically convert dicts to DotDict for dot notation access."""')
    lines.append("        if data is None:")
    lines.append("            return None")
    lines.append("        if isinstance(data, list):")
    lines.append("            return [self._auto_convert(item) for item in data]")
    lines.append("        if isinstance(data, dict):")
    lines.append("            return DotDict(data)")
    lines.append("        return data")
    lines.append("")

    # Generate methods
    method_names: set[str] = set()

    for path, path_item in sorted(paths.items()):
        for http_method in ["get", "post", "put", "patch", "delete"]:
            if http_method not in path_item:
                continue

            operation = path_item[http_method]

            base_method_name = generate_method_name(path, http_method)
            method_name = base_method_name
            counter = 1
            while method_name in method_names:
                method_name = f"{base_method_name}_{counter}"
                counter += 1
            method_names.add(method_name)

            path_params = re.findall(r"\{([^}]+)\}", path)

            params = []
            for path_param in path_params:
                params.append(f"{to_snake_case(path_param)}: str")

            if http_method in ["post", "put", "patch"]:
                params.append("data: Dict[str, Any] = None")

            params.append("**kwargs")
            params_str = ", ".join(params) if params else "**kwargs"

            responses = operation.get("responses", {})
            success_response = (
                responses.get("200")
                or responses.get("201")
                or responses.get("204")
                or responses.get("default")
            )
            return_type = "Any"

            if success_response:
                content = success_response.get("content", {})
                json_content = content.get("application/json", {})
                schema = json_content.get("schema", {})

                operation_id = operation.get("operationId")
                if operation_id:
                    context_name = f"{to_pascal_case(operation_id)}Response"
                else:
                    context_name = f"{to_pascal_case(method_name)}Response"

                return_type = python_type_from_schema(
                    schema, components, inline_schemas, context_name
                )

            lines.append(f"    def {method_name}(self, {params_str}) -> {return_type}:")

            summary = operation.get("summary", f"{http_method.upper()} {path}")
            lines.append(f'        """{summary}"""')

            url_template = path
            for path_param in path_params:
                snake_param = to_snake_case(path_param)
                url_template = url_template.replace(f"{{{path_param}}}", f"{{{snake_param}}}")

            lines.append(f'        url = f"{{self.base_url}}{url_template}"')

            if http_method in ["post", "put", "patch"]:
                lines.append(
                    f"        response = self.session.{http_method}(url, json=data, params=kwargs)"
                )
            else:
                lines.append(f"        response = self.session.{http_method}(url, params=kwargs)")

            lines.append("        response.raise_for_status()")
            lines.append("        result = response.json() if response.content else None")
            lines.append("        return self._auto_convert(result)")
            lines.append("")
            lines.append("")

    return lines, list(method_names)


def generate_lazy_client(
    class_name: str,
    integration_name: str,
    auth_type: AuthType,
    method_names: list[str],
) -> list[str]:
    """Generate the lazy client wrapper that auto-initializes from Bifrost."""
    lines = []

    lines.append("")
    lines.append("class _LazyClient:")
    lines.append('    """')
    lines.append("    Module-level proxy that auto-initializes from Bifrost integration.")
    lines.append("    Provides zero-config authentication experience.")
    lines.append('    """')
    lines.append("")
    lines.append(f"    _client: Optional[_{class_name}Client] = None")
    lines.append(f'    _integration_name: str = "{integration_name}"')
    lines.append(f'    _auth_type: str = "{auth_type}"')
    lines.append("")
    lines.append("    async def _ensure_client(self):")
    lines.append("        if self._client is not None:")
    lines.append("            return self._client")
    lines.append("")
    lines.append("        from bifrost import integrations")
    lines.append("")
    lines.append("        integration = await integrations.get(self._integration_name)")
    lines.append("        if not integration:")
    lines.append(
        "            raise RuntimeError(f\"Integration '{self._integration_name}' not found\")"
    )
    lines.append("")
    lines.append("        config = integration.config or {}")
    lines.append("        session = requests.Session()")
    lines.append("")

    # Auth type-specific initialization
    if auth_type == "api_key":
        lines.append("        # API Key authentication")
        lines.append('        header_name = config.get("header_name", "Authorization")')
        lines.append('        api_key = config.get("api_key")')
        lines.append("        if api_key:")
        lines.append("            session.headers[header_name] = api_key")
    elif auth_type == "bearer":
        lines.append("        # Bearer token authentication")
        lines.append('        token = config.get("token")')
        lines.append("        if token:")
        lines.append('            session.headers["Authorization"] = f"Bearer {token}"')
    elif auth_type == "basic":
        lines.append("        # Basic authentication")
        lines.append("        import base64")
        lines.append('        username = config.get("username", "")')
        lines.append('        password = config.get("password", "")')
        lines.append("        if username or password:")
        lines.append(
            '            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()'
        )
        lines.append('            session.headers["Authorization"] = f"Basic {credentials}"')
    elif auth_type == "oauth":
        lines.append("        # OAuth authentication")
        lines.append("        if integration.oauth and integration.oauth.access_token:")
        lines.append(
            '            session.headers["Authorization"] = f"Bearer {integration.oauth.access_token}"'
        )
        lines.append("        else:")
        lines.append(
            "            raise RuntimeError(\"OAuth not configured or access token missing\")"
        )

    lines.append("")
    lines.append('        base_url = config.get("base_url", "")')
    lines.append("        if not base_url:")
    lines.append(
        "            raise RuntimeError(f\"base_url not configured for integration '{self._integration_name}'\")"
    )
    lines.append("")
    lines.append(f"        self._client = _{class_name}Client(base_url, session)")
    lines.append("        return self._client")
    lines.append("")

    # Generate async wrapper methods for each API method
    lines.append("    def __getattr__(self, name: str):")
    lines.append('        """Proxy attribute access to the real client."""')
    lines.append("        async def method_wrapper(*args, **kwargs):")
    lines.append("            client = await self._ensure_client()")
    lines.append("            method = getattr(client, name)")
    lines.append("            return method(*args, **kwargs)")
    lines.append("        return method_wrapper")
    lines.append("")

    return lines


def generate_sdk(
    spec: dict[str, Any],
    integration_name: str,
    auth_type: AuthType,
    module_name: str | None = None,
) -> tuple[str, str]:
    """
    Generate a complete SDK module from an OpenAPI spec.

    Args:
        spec: Parsed OpenAPI specification
        integration_name: Name of the Bifrost integration
        auth_type: Authentication type (bearer, api_key, basic, oauth)
        module_name: Optional module name (defaults to sanitized spec title)

    Returns:
        Tuple of (generated_code, suggested_module_name)
    """
    spec = sanitize_spec(spec)

    title = spec.get("info", {}).get("title", "API")
    class_name = to_pascal_case(title) or "APIClient"

    if not module_name:
        pythonic_name = re.sub(r"[^a-zA-Z0-9]+", "_", title).lower().strip("_")
        module_name = pythonic_name

    lines = [
        '"""',
        f"{title} - Python SDK",
        "",
        "Auto-generated from OpenAPI spec with Bifrost integration support.",
        f"Integration: {integration_name}",
        f"Auth Type: {auth_type}",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "from typing import Any, Dict, List, Optional",
        "",
        "import requests",
        "",
        "",
        "# Helper class for dot notation access on dicts",
        "class DotDict(dict):",
        '    """Dict subclass that allows dot notation access to keys."""',
        "",
        "    def __getattr__(self, key):",
        "        try:",
        "            value = self[key]",
        "            if isinstance(value, dict) and not isinstance(value, DotDict):",
        "                return DotDict(value)",
        "            elif isinstance(value, list):",
        "                return [DotDict(item) if isinstance(item, dict) else item for item in value]",
        "            return value",
        "        except KeyError:",
        '            raise AttributeError(f"No attribute {key}")',
        "",
        "    def __setattr__(self, key, value):",
        "        self[key] = value",
        "",
        "    def __delattr__(self, key):",
        "        try:",
        "            del self[key]",
        "        except KeyError:",
        '            raise AttributeError(f"No attribute {key}")',
        "",
        "",
    ]

    # Generate internal client with all methods
    client_lines, method_names = generate_internal_client(spec, class_name)
    lines.extend(client_lines)

    # Generate lazy client wrapper
    lazy_lines = generate_lazy_client(class_name, integration_name, auth_type, method_names)
    lines.extend(lazy_lines)

    # Module-level instance and __getattr__ for magic imports
    lines.append("")
    lines.append("# Module-level lazy client instance")
    lines.append("_lazy = _LazyClient()")
    lines.append("")
    lines.append("")
    lines.append("def __getattr__(name: str):")
    lines.append('    """Enable module-level attribute access to lazy client methods."""')
    lines.append("    return getattr(_lazy, name)")
    lines.append("")

    return "\n".join(lines), module_name


# =============================================================================
# Public API
# =============================================================================


class SDKGeneratorResult:
    """Result of SDK generation."""

    def __init__(
        self,
        code: str,
        module_name: str,
        class_name: str,
        endpoint_count: int,
        schema_count: int,
    ):
        self.code = code
        self.module_name = module_name
        self.class_name = class_name
        self.endpoint_count = endpoint_count
        self.schema_count = schema_count


def generate_sdk_from_url(
    spec_url: str,
    integration_name: str,
    auth_type: AuthType,
    module_name: str | None = None,
) -> SDKGeneratorResult:
    """
    Generate SDK from an OpenAPI spec URL.

    Args:
        spec_url: URL to OpenAPI spec (JSON or YAML)
        integration_name: Name of the Bifrost integration
        auth_type: Authentication type
        module_name: Optional module name

    Returns:
        SDKGeneratorResult with generated code and metadata
    """
    logger.info(f"Loading OpenAPI spec from {spec_url}")
    spec = load_spec_from_url(spec_url)

    return _generate_sdk_result(spec, integration_name, auth_type, module_name)


def generate_sdk_from_content(
    content: str,
    content_type: str,
    integration_name: str,
    auth_type: AuthType,
    module_name: str | None = None,
) -> SDKGeneratorResult:
    """
    Generate SDK from OpenAPI spec content.

    Args:
        content: Raw OpenAPI spec content
        content_type: "json" or "yaml"
        integration_name: Name of the Bifrost integration
        auth_type: Authentication type
        module_name: Optional module name

    Returns:
        SDKGeneratorResult with generated code and metadata
    """
    logger.info("Parsing OpenAPI spec from provided content")
    spec = load_spec_from_content(content, content_type)

    return _generate_sdk_result(spec, integration_name, auth_type, module_name)


def _generate_sdk_result(
    spec: dict,
    integration_name: str,
    auth_type: AuthType,
    module_name: str | None,
) -> SDKGeneratorResult:
    """Internal helper to generate SDK and build result."""
    code, final_module_name = generate_sdk(spec, integration_name, auth_type, module_name)

    title = spec.get("info", {}).get("title", "API")
    class_name = sanitize_class_name(to_pascal_case(title))

    paths = spec.get("paths", {})
    endpoint_count = sum(
        len([m for m in ["get", "post", "put", "patch", "delete"] if m in item])
        for item in paths.values()
    )
    schema_count = len(spec.get("components", {}).get("schemas", {}))

    logger.info(
        f"Generated SDK: {final_module_name}.py with {endpoint_count} endpoints, {schema_count} schemas"
    )

    return SDKGeneratorResult(
        code=code,
        module_name=final_module_name,
        class_name=class_name,
        endpoint_count=endpoint_count,
        schema_count=schema_count,
    )
