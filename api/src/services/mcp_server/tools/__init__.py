"""
MCP System Tools

All system tool implementations live in this package.
Each tool has the @system_tool decorator which registers it automatically.

To add a new tool:
1. Add your function to the appropriate file (or create a new one)
2. Add the @system_tool decorator with metadata
3. Import the module in this __init__.py
4. Done - it's automatically available everywhere

Structure:
- workflow.py     - execute, list, validate, create workflows
- forms.py        - form CRUD and schema
- files.py        - workspace file operations
- knowledge.py    - knowledge base search
- integrations.py - list integrations
- execution.py    - execution history
- data_providers.py - data provider tools
- sdk.py          - SDK documentation (generated from source)
- apps.py         - application CRUD
- tables.py       - table CRUD and schema
- organizations.py - organization CRUD (restricted)
- agents.py       - agent CRUD and schema
- app_files.py    - app file CRUD for code engine apps
"""

# Import all tool modules to trigger registration
# The @system_tool decorator registers each function in the global registry
from src.services.mcp_server.tools import workflow  # noqa: F401
from src.services.mcp_server.tools import forms  # noqa: F401
from src.services.mcp_server.tools import files  # noqa: F401
from src.services.mcp_server.tools import knowledge  # noqa: F401
from src.services.mcp_server.tools import integrations  # noqa: F401
from src.services.mcp_server.tools import execution  # noqa: F401
from src.services.mcp_server.tools import data_providers  # noqa: F401
from src.services.mcp_server.tools import apps  # noqa: F401
from src.services.mcp_server.tools import tables  # noqa: F401
from src.services.mcp_server.tools import organizations  # noqa: F401
from src.services.mcp_server.tools import sdk  # noqa: F401
from src.services.mcp_server.tools import agents  # noqa: F401
from src.services.mcp_server.tools import app_files  # noqa: F401
