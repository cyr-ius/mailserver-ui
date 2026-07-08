"""Application exception hierarchy.

Routers and services raise these typed exceptions instead of scattering
``HTTPException`` throughout the codebase. A single set of handlers (registered
in ``main.py``) turns them into JSON responses, keeping status codes and error
shapes consistent and never leaking internals to the client.
"""

from fastapi import status


class BaseAPIException(Exception):
    """Base class for all application errors mapped to an HTTP response."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.headers = headers
        super().__init__(detail)


class BadRequestException(BaseAPIException):
    """Raised when the request payload is semantically invalid (HTTP 400)."""

    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_400_BAD_REQUEST, detail)


class NotFoundException(BaseAPIException):
    """Raised when a requested resource does not exist (HTTP 404)."""

    def __init__(self, resource: str, resource_id: object) -> None:
        super().__init__(
            status.HTTP_404_NOT_FOUND,
            f"{resource} with ID {resource_id} not found",
        )


class ConflictException(BaseAPIException):
    """Raised when a request conflicts with the current state (HTTP 409)."""

    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_409_CONFLICT, detail)


class UnauthorizedException(BaseAPIException):
    """Raised when authentication is missing or invalid (HTTP 401)."""

    def __init__(self, detail: str = "Not authenticated") -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, detail)


class ForbiddenException(BaseAPIException):
    """Raised when the caller lacks the required privileges (HTTP 403)."""

    def __init__(self, detail: str = "Forbidden") -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, detail)


class BadGatewayException(BaseAPIException):
    """Raised when an upstream dependency fails or is unreachable (HTTP 502)."""

    def __init__(self, detail: str = "Upstream service unavailable") -> None:
        super().__init__(status.HTTP_502_BAD_GATEWAY, detail)
