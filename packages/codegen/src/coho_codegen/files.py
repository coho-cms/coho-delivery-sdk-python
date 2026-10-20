from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx

from .config import CodegenConfig
from .generate import GENERATED_MARK, GeneratedFile
from .model import CodegenError, TypeModel, read_type_model


def read_type_model_file(path: Path) -> TypeModel:
    """The type model in `path`, read and checked."""
    if not path.exists():
        raise CodegenError(f"No type model at {path}: run coho-codegen pull")
    return _parse(path.read_bytes(), str(path))


@dataclass(frozen=True)
class Pulled:
    changed: bool
    model: TypeModel


def pull(config: CodegenConfig, path: Path, token: str, http: httpx.Client) -> Pulled:
    """
    Fetches the type model for the configured ref and writes it to `path` as it arrived, so
    the committed file is exactly what the server sent.

    The server's ETag is the SHA-256 of the body, and the file is the body, so the file's own
    hash asks whether anything changed; an unchanged model costs a `304`. A model this
    generator cannot read is refused before anything is written.
    """
    if not (config.url and config.account and config.project and config.ref):
        raise CodegenError("pull needs url, account, project and ref in the config")
    endpoint = (
        f"{config.url.rstrip('/')}/api/v1/accounts/{quote(config.account, safe='')}/projects/"
        f"{quote(config.project, safe='')}/refs/{quote(config.ref, safe='')}/type-model"
    )

    existing = path.read_bytes() if path.exists() else None
    headers = {"accept": "application/json", "authorization": f"Bearer {token}"}
    if existing is not None:
        headers["if-none-match"] = f'"{hashlib.sha256(existing).hexdigest()}"'

    response = send(http, endpoint, headers, config.url)
    if response.status_code == 304 and existing is not None:
        return Pulled(changed=False, model=_parse(existing, str(path)))
    if not response.is_success:
        raise CodegenError(failure(response, "Pulling the type model"))

    body = response.content
    model = _parse(body, endpoint)

    # Written beside the file and renamed over it, so a failure never leaves half a model.
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_bytes(body)
    temporary.replace(path)
    return Pulled(changed=True, model=model)


def send(http: httpx.Client, url: str, headers: dict[str, str], origin: str) -> httpx.Response:
    try:
        return http.get(url, headers=headers)
    except httpx.HTTPError as error:
        raise CodegenError(f"Cannot reach Coho at {origin}: {error}") from None


def write(files: list[GeneratedFile], out_dir: Path) -> None:
    """
    Writes `files` into `out_dir`, and removes the files an earlier run generated that this
    one does not, so a type taken off the ref takes its file with it. A file without the
    generated header is never removed.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    names = {file.path for file in files}
    for file in files:
        (out_dir / file.path).write_text(file.contents, encoding="utf-8")
    for path in out_dir.iterdir():
        if path.name in names or not path.is_file() or path.suffix != ".py":
            continue
        if path.read_text(encoding="utf-8").startswith(GENERATED_MARK):
            path.unlink()


def drift(files: list[GeneratedFile], out_dir: Path) -> list[str]:
    """
    How `out_dir` differs from `files`: each file missing or different, and each file there
    that nothing generates. Empty when the generated code is up to date.
    """
    problems: list[str] = []
    for file in files:
        path = out_dir / file.path
        if not path.exists():
            problems.append(f"{file.path} is missing")
        elif path.read_text(encoding="utf-8") != file.contents:
            problems.append(f"{file.path} differs from what the type model generates")
    if out_dir.exists():
        names = {file.path for file in files}
        for path in sorted(out_dir.iterdir()):
            if path.is_file() and path.suffix == ".py" and path.name not in names:
                problems.append(f"{path.name} is in the output directory, but nothing generates it")
    return problems


def _parse(body: bytes, source: str) -> TypeModel:
    try:
        parsed = json.loads(body)
    except ValueError:
        raise CodegenError(f"{source} is not JSON") from None
    return read_type_model(parsed)


def failure(response: httpx.Response, doing: str) -> str:
    detail = ""
    try:
        problem = response.json()
        if isinstance(problem, dict):
            parts = [problem.get("code"), problem.get("detail") or problem.get("title")]
            detail = ": ".join(part for part in parts if isinstance(part, str))
    except ValueError:
        pass  # Not a problem document; the status says enough.
    status = response.status_code
    hint = " Check COHO_TOKEN: it needs read access to the project." if status in (401, 403) else ""
    return f"{doing} failed with {status}{f' ({detail})' if detail else ''}.{hint}"
