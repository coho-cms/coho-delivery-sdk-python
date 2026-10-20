from __future__ import annotations

from .types import Problem


class CohoDeliveryError(Exception):
    """
    A refusal from the delivery API, or an answer the client could not read.

    Branch on `code`, which is stable. The server's codes include `REF_NOT_FOUND`,
    `KEY_REQUIRED`, `PROJECT_NOT_FOUND`, `INVALID_QUERY`, `RESOLUTION_LIMIT`,
    `ARTIFACT_UNREADABLE` and `POOL_UNAVAILABLE`; the last two are the server's problem, not
    the request's. A preview adds `UNAUTHENTICATED`, for a token that has expired or been
    revoked, and `ACCOUNT_SUSPENDED`, `ACCOUNT_CLOSED` and `USER_SUSPENDED`. An answer that is
    not a problem document, such as a proxy's error page, has the code `UNEXPECTED_RESPONSE`.
    """

    status: int
    code: str

    problem: Problem | None
    """The problem document as the server sent it, when there was one."""

    def __init__(self, status: int, code: str, message: str, problem: Problem | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.problem = problem
