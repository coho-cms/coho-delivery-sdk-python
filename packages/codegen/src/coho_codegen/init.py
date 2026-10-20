"""Points a library made from the template at a Coho project."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from .files import failure, send
from .model import CodegenError

TOKEN_PREFIX = "coho_pt_"
"""How a project token announces itself."""


@dataclass(frozen=True)
class Named:
    id: str
    name: str | None


@dataclass(frozen=True)
class TokenDescription:
    """What a project token says about itself: Coho's `GET /api/v1/token`."""

    account: Named
    project: Named
    role: str


def describe_token(url: str, token: str, http: httpx.Client) -> TokenDescription:
    """
    Asks Coho at `url` which account and project `token` is for. A token names its own
    project, so nothing else is needed to find them: no account or project ids to copy.
    """
    if not url.startswith(("http://", "https://")):
        raise CodegenError(f"'{url}' is not a URL, such as https://app.coho.example")
    if not token.startswith(TOKEN_PREFIX):
        raise CodegenError(
            f"A project token starts {TOKEN_PREFIX}. Create one with: coho token create --role viewer"
        )

    response = send(
        http,
        f"{url.rstrip('/')}/api/v1/token",
        {"accept": "application/json", "authorization": f"Bearer {token}"},
        url,
    )
    if response.is_success:
        try:
            body = response.json()
            return TokenDescription(
                account=Named(body["account"]["id"], body["account"].get("name")),
                project=Named(body["project"]["id"], body["project"].get("name")),
                role=body["token"]["role"],
            )
        except (ValueError, KeyError, TypeError) as error:
            raise CodegenError(
                f"Coho's description of the token is not what this tool reads: {error}"
            ) from None

    hint = {
        401: " Check that it is a current project token, not revoked or expired.",
        403: " The account is suspended or closed.",
        404: " Check the URL: it is Coho's, as `coho status` shows it, not delivery's.",
    }.get(response.status_code, "")
    said = failure(response, "Asking Coho about the token").replace(
        " Check COHO_TOKEN: it needs read access to the project.", ""
    )
    raise CodegenError(f"Coho refused the token. {said}{hint}")
