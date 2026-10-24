"""Every error leaves the API as {"error": {"code", "message", "details"?}} with a meaningful status."""
import logging

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from ..providers.http import NotFoundError, ProviderError

log = logging.getLogger(__name__)


def _error(code: str, message: str, http_status: int, details=None) -> Response:
    body = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return Response({"error": body}, status=http_status)


def api_exception_handler(exc, context):
    if isinstance(exc, NotFoundError):
        return _error("not_found", str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)
    if isinstance(exc, ProviderError):
        log.warning("upstream failure: %s", exc)
        return _error("upstream_unavailable", str(exc), status.HTTP_502_BAD_GATEWAY)
    if isinstance(exc, ValidationError):
        return _error("invalid_request", _first_message(exc.detail), status.HTTP_400_BAD_REQUEST, exc.detail)

    response = exception_handler(exc, context)
    if response is not None:
        detail = response.data.get("detail", "Request failed.") if isinstance(response.data, dict) else response.data
        return _error(getattr(exc, "default_code", "error"), str(detail), response.status_code)

    log.exception("unhandled error", exc_info=exc)
    return _error("internal_error", "Something went wrong on our side.", status.HTTP_500_INTERNAL_SERVER_ERROR)


def _first_message(detail) -> str:
    """Flatten DRF's nested error structure into one human sentence for the UI banner."""
    if isinstance(detail, dict):
        field, value = next(iter(detail.items()))
        message = _first_message(value)
        return message if field == "non_field_errors" else f"{field.replace('_', ' ').capitalize()}: {message}"
    if isinstance(detail, list) and detail:
        return _first_message(detail[0])
    return str(detail)
