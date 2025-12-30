"""
Built-in webhook adapters for the Bifrost event system.
"""

from src.services.webhooks.adapters.generic import GenericWebhookAdapter
from src.services.webhooks.adapters.microsoft_graph import MicrosoftGraphAdapter

__all__ = [
    "GenericWebhookAdapter",
    "MicrosoftGraphAdapter",
]

# Registry of built-in adapters
BUILTIN_ADAPTERS: dict[str, type] = {
    "generic": GenericWebhookAdapter,
    "microsoft_graph": MicrosoftGraphAdapter,
}
