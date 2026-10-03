from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# code -> (http status, retryable)
ERROR_CODES: dict[str, tuple[int, bool]] = {
    "VALIDATION_ERROR": (422, False),
    "UNAUTHORIZED": (401, False),
    "NOT_FOUND": (404, False),
    "UPI_NOT_FOUND": (404, False),
    "UPI_INACTIVE": (422, False),
    "TRANSACTION_NOT_FOUND": (404, False),
    "INSUFFICIENT_FUNDS": (422, False),
    "CURRENCY_MISMATCH": (422, False),
    "SAME_UPI": (422, False),
    "NOT_PERMITTED": (403, False),
    "CONSENT_REQUIRED": (403, False),
    "ORIGIN_NOT_ALLOWED": (403, False),
    "IDEMPOTENCY_KEY_REQUIRED": (400, False),
    "IDEMPOTENCY_KEY_REUSED": (409, False),
    "DUPLICATE_REFERENCE": (409, False),
    "CONFLICT": (409, False),
    "INVALID_STATE": (409, False),
    "COLLECT_EXPIRED": (409, False),
    "PIN_NOT_SET": (422, False),
    "PIN_INVALID": (422, False),
    "PIN_LOCKED": (423, False),
    "RATE_LIMITED": (429, True),
    "INTERNAL_ERROR": (500, True),
    "SERVICE_UNAVAILABLE": (503, True),
}


class BankError(Exception):
    def __init__(self, code: str, message: str, status_code: int | None = None, retryable: bool | None = None):
        default_status, default_retryable = ERROR_CODES.get(code, (400, False))
        self.code = code
        self.message = message
        self.status_code = status_code or default_status
        self.retryable = default_retryable if retryable is None else retryable
        super().__init__(message)

    def body(self) -> dict:
        return error_body(self.code, self.message, self.retryable)


def error_body(code: str, message: str, retryable: bool = False) -> dict:
    return {"error": {"code": code, "message": message, "retryable": retryable}}


_STATUS_TO_CODE = {400: "VALIDATION_ERROR", 401: "UNAUTHORIZED", 403: "NOT_PERMITTED", 404: "NOT_FOUND",
                   405: "NOT_FOUND", 409: "CONFLICT", 422: "VALIDATION_ERROR", 429: "RATE_LIMITED"}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(BankError)
    async def _bank_error(_: Request, exc: BankError):
        return JSONResponse(status_code=exc.status_code, content=exc.body())

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = _STATUS_TO_CODE.get(exc.status_code, "INTERNAL_ERROR" if exc.status_code >= 500 else "VALIDATION_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, str(exc.detail), exc.status_code >= 500),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        parts = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", []) if p not in ("body", "query", "header", "path"))
            parts.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
        return JSONResponse(status_code=422, content=error_body("VALIDATION_ERROR", "; ".join(parts)))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        return JSONResponse(status_code=500, content=error_body("INTERNAL_ERROR", "internal error", True))
