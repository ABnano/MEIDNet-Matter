"""One error shape for every non-2xx answer:

    {"error": {"code": "...", "message": "plain sentence", "fields": [{"loc": "objectives.0.property", "msg": "..."}],
               "retry_after_s": 30}}

Engine errors (ValueError, SystemExit, KeyError raised by meidnet) are the user's problem to fix and come back as 400
with the engine's own sentence. Anything unexpected is a 500; on a public host its text is hidden.
"""
from __future__ import annotations

import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from matter.jsonsafe import MatterJSONResponse
from matter.settings import Settings


class ApiError(Exception):
    """An error with a code and a status, raised by services and turned into the envelope here."""

    def __init__(self, code: str, message: str, status: int = 400, fields: list | None = None, retry_after_s: int | None = None):
        super().__init__(message)
        self.code, self.message, self.status, self.fields, self.retry_after_s = code, message, status, fields or [], retry_after_s


class NotAvailableInPhase(ApiError):
    def __init__(self, phase: int, what: str):
        super().__init__("not_available_in_phase", f"{what} arrives in Phase {phase} of MEIDNet Matter", status=501)


def envelope(code: str, message: str, status: int, fields=None, retry_after_s=None) -> MatterJSONResponse:
    body = {"error": {"code": code, "message": message}}
    if fields:
        body["error"]["fields"] = fields
    if retry_after_s is not None:
        body["error"]["retry_after_s"] = retry_after_s
    headers = {"Retry-After": str(retry_after_s)} if retry_after_s else None
    return MatterJSONResponse(body, status_code=status, headers=headers)


def _loc(loc) -> str:
    return ".".join(str(x) for x in loc if x not in ("body",))


class EngineExitMiddleware:
    """meidnet reports user errors with SystemExit, a BaseException that Starlette's handlers cannot register for;
    this turns it into the 400 envelope before it reaches the server."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        try:
            await self.app(scope, receive, send)
        except SystemExit as exc:
            response = envelope("engine_error", str(exc.code if exc.code is not None else exc), 400)
            await response(scope, receive, send)


def install_error_handlers(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(EngineExitMiddleware)

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return envelope(exc.code, exc.message, exc.status, exc.fields, exc.retry_after_s)

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError):
        fields = [{"loc": _loc(e.get("loc", ())), "msg": e.get("msg", "")} for e in exc.errors()]
        return envelope("validation_error", "the request does not match the API schema", 422, fields)

    @app.exception_handler(ValidationError)
    async def _pydantic_validation(request: Request, exc: ValidationError):
        fields = [{"loc": _loc(e.get("loc", ())), "msg": e.get("msg", "")} for e in exc.errors()]
        return envelope("validation_error", "a setting has an invalid value", 422, fields)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return envelope(code, str(exc.detail), exc.status_code)

    @app.exception_handler(ValueError)
    async def _value_error(request: Request, exc: ValueError):
        return envelope("engine_error", str(exc), 400)

    @app.exception_handler(KeyError)
    async def _key_error(request: Request, exc: KeyError):
        return envelope("engine_error", str(exc.args[0]) if exc.args else "unknown key", 400)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        message = "server error" if settings.public else "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        return envelope("server_error", message, 500)
