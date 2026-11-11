"""One error body for every failure: RFC 9457 Problem Details (`application/problem+json`) with the request_id.
With type "about:blank", title is the standard phrase of the status code (RFC 9457 4.2.1, RFC 9110 names)."""
import openai
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from research_assistant.core.logging import request_id_var
from research_assistant.schemas import Problem

TITLES = {400: "Bad Request", 401: "Unauthorized", 404: "Not Found", 405: "Method Not Allowed", 409: "Conflict",
          422: "Unprocessable Content", 429: "Too Many Requests", 500: "Internal Server Error", 502: "Bad Gateway",
          503: "Service Unavailable", 504: "Gateway Timeout"}


def problem(status: int, detail: str, instance: str) -> dict:
    return Problem(title=TITLES.get(status, "Error"), status=status, detail=detail, instance=instance,
                   request_id=request_id_var.get()).model_dump()


def problem_response(status: int, detail: str, instance: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(problem(status, detail, instance), status, headers=headers,
                        media_type="application/problem+json")


async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return problem_response(exc.status_code, str(exc.detail), request.url.path, exc.headers)


async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    body = problem(422, "The request body or parameters are invalid.", request.url.path)
    body["errors"] = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return JSONResponse(body, 422, media_type="application/problem+json")


def run_failure(exc: Exception) -> tuple[int, str]:
    """A failure in the middle of a run -> the status the `error` event carries (the HTTP status 200 is already sent)."""
    if isinstance(exc, TimeoutError):
        return 504, "The run took too long and was stopped."
    if isinstance(exc, openai.RateLimitError):  # 429 from the model provider: retry later
        return 429, "The model provider is rate limiting requests. Retry in a moment."
    if isinstance(exc, openai.APIError):  # provider 5xx, connection error, bad key
        return 502, "The model provider failed to answer."
    return 500, f"The run stopped ({type(exc).__name__}). Quote the request_id when reporting it."


def add_error_handlers(app: FastAPI) -> None:
    # Starlette's HTTPException also covers FastAPI's and the 404/405 of unknown routes
    app.add_exception_handler(StarletteHTTPException, http_error)
    app.add_exception_handler(RequestValidationError, validation_error)
