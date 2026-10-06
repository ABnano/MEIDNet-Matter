"""Request-scoped helpers for the routes."""
from __future__ import annotations

import re

from fastapi import Header, Request

from matter.api.errors import ApiError

SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
RESERVED_SESSIONS = ("local", "localtab")


def get_services(request: Request):
    services = getattr(request.app.state, "services", None)
    if services is None:
        raise ApiError("server_error", "the application has not finished starting", status=503)
    return services


def session_id(request: Request, x_matter_session: str | None = Header(default=None), mutating: bool = False) -> str:
    """The visitor's session id: the X-Matter-Session header. Locally it may be absent ("local"); on a shared host a
    mutating request needs one, and the shared defaults are refused."""
    settings = request.app.state.settings
    sid = (x_matter_session or "").strip()
    if not sid:
        if settings.public and mutating:
            raise ApiError("validation_error", "the X-Matter-Session header is needed on this shared server", status=400)
        return "local"
    if not SESSION_RE.match(sid):
        raise ApiError("validation_error", "X-Matter-Session must be 4–64 letters, digits, '-' or '_'", status=400)
    if settings.public and sid in RESERVED_SESSIONS:
        raise ApiError("validation_error", f"'{sid}' is a reserved session id", status=400)
    return sid
