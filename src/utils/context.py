"""
Request context management using contextvars for correlation IDs and user information.
"""

import contextvars
from typing import Optional

# Context variables for request tracking
request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'request_id', default=None
)

user_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'user_id', default=None
)

user_email_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'user_email', default=None
)


def set_request_context(request_id: str, user_id: Optional[str] = None, user_email: Optional[str] = None):
    """Set request context variables."""
    request_id_var.set(request_id)
    if user_id:
        user_id_var.set(user_id)
    if user_email:
        user_email_var.set(user_email)


def get_request_id() -> Optional[str]:
    """Get current request ID from context."""
    return request_id_var.get()


def get_user_id() -> Optional[str]:
    """Get current user ID from context."""
    return user_id_var.get()


def get_user_email() -> Optional[str]:
    """Get current user email from context."""
    return user_email_var.get()


def clear_context():
    """Clear all context variables."""
    request_id_var.set(None)
    user_id_var.set(None)
    user_email_var.set(None)
