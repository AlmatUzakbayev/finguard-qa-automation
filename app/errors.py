"""A single error format for the whole API: {"code": "...", "detail": "..."}.

Clients (and tests) can rely on the machine-readable `code` instead of parsing text.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status_code: int, code: str, detail: str, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.headers = headers


def unauthorized(detail: str = "Not authenticated") -> AppError:
    return AppError(401, "UNAUTHORIZED", detail, headers={"WWW-Authenticate": "Bearer"})


def not_found(what: str) -> AppError:
    return AppError(404, "NOT_FOUND", f"{what} not found")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "detail": exc.detail},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]} for err in exc.errors()]
        return JSONResponse(
            status_code=422,
            content={"code": "VALIDATION_ERROR", "detail": "Request validation failed", "errors": errors},
        )
