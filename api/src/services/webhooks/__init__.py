"""
Webhook services for the Bifrost event system.

This package provides:
- WebhookAdapter protocol for implementing webhook handlers
- Built-in adapters (generic, Microsoft Graph)
- Adapter registry for discovery and lookup
"""

from src.services.webhooks.protocol import (
    Deliver,
    HandleResult,
    Rejected,
    RenewResult,
    SubscribeResult,
    ValidationResponse,
    WebhookAdapter,
    WebhookRequest,
)

__all__ = [
    "WebhookAdapter",
    "WebhookRequest",
    "SubscribeResult",
    "RenewResult",
    "HandleResult",
    "ValidationResponse",
    "Deliver",
    "Rejected",
]
