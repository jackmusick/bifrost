"""
Authorization helpers for shared HaloPSA tools.

Provides caller scoping (provider vs org user) and ticket access checks.
"""

from bifrost import context, UserError


def get_caller_scope() -> dict:
    """Return caller identity for authorization decisions.

    When no organization context is available (e.g. CLI testing),
    defaults to provider-level access.
    """
    org = getattr(context, "organization", None)
    return {
        "is_provider": getattr(org, "is_provider", True) if org else True,
        "email": getattr(context, "email", None),
        "org_id": getattr(context, "org_id", None),
    }


async def check_ticket_access(ticket: dict) -> None:
    """Raise UserError if an org user tries to access a ticket they don't own.

    Provider users have unrestricted access.
    Org users can only access tickets where they are the requestor (matched by email).
    """
    scope = get_caller_scope()
    if scope["is_provider"]:
        return

    ticket_email = (
        ticket.get("user_emailaddress") or ticket.get("useremail") or ""
    ).lower()
    caller_email = (scope["email"] or "").lower()

    if not caller_email or ticket_email != caller_email:
        raise UserError("You don't have access to this ticket.")
