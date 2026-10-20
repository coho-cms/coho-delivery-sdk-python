from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import httpx
import pytest

from coho_codegen.cli import Context, run
from coho_codegen.generate import GENERATED_MARK

FIXTURES = Path(__file__).resolve().parents[3] / "spec" / "type-model" / "fixtures"
TOKEN = f"coho_pt_{'b' * 43}"


class Coho:
    """Coho's two answers codegen asks for: a token's description, and a ref's type model."""

    def __init__(self, model: bytes):
        self.model = model
        self.asked: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"code": "UNAUTHENTICATED", "title": "Unauthenticated"})
        if request.url.path == "/api/v1/token":
            return httpx.Response(
                200,
                json={
                    "account": {"id": "acct-1", "name": "Acme"},
                    "project": {"id": "proj-1", "name": "blog-sample"},
                    "token": {"id": "t1", "label": "lib", "role": "viewer"},
                },
            )
        if request.url.path == "/api/v1/accounts/acct-1/projects/proj-1/refs/dev/type-model":
            etag = f'"{hashlib.sha256(self.model).hexdigest()}"'
            if request.headers.get("if-none-match") == etag:
                return httpx.Response(304)
            return httpx.Response(200, content=self.model, headers={"etag": etag})
        return httpx.Response(404, json={"code": "NOT_FOUND", "title": "Not found"})


def context(
    cwd: Path, coho: Coho, environ: dict[str, str] | None = None
) -> tuple[Context, io.StringIO, io.StringIO]:
    out, err = io.StringIO(), io.StringIO()
    http = httpx.Client(transport=httpx.MockTransport(coho.handle))
    env = environ or {}
    return Context(cwd=cwd, environ=env.get, out=out, err=err, http=http, prompt=None), out, err


@pytest.fixture
def library(tmp_path: Path) -> Path:
    (tmp_path / "coho.config.json").write_text(
        json.dumps({"url": "https://coho.test", "ref": "v1.0.0", "outDir": "src/acme/coho"}) + "\n"
    )
    (tmp_path / ".env.example").write_text("# The token.\nCOHO_TOKEN=\nCOHO_REF=\n")
    return tmp_path


def test_init_asks_coho_whose_token_it_is_and_writes_the_config_and_the_env(library: Path) -> None:
    coho = Coho(b"{}")
    ctx, out, _ = context(library, coho)

    assert run(["init", "--url", "https://coho.test", "--token", TOKEN, "--ref", "dev"], ctx) == 0

    config = json.loads((library / "coho.config.json").read_text())
    assert config == {
        "url": "https://coho.test",
        "ref": "dev",
        "outDir": "src/acme/coho",
        "account": "acct-1",
        "project": "proj-1",
    }
    assert (library / ".env").read_text() == f"# The token.\nCOHO_TOKEN={TOKEN}\nCOHO_REF=\n"
    assert (library / ".env").stat().st_mode & 0o077 == 0
    assert "It reads blog-sample, in Acme, with the token in .env." in out.getvalue()


def test_init_writes_nothing_when_coho_refuses_the_token(library: Path) -> None:
    before = (library / "coho.config.json").read_text()
    ctx, _, err = context(library, Coho(b"{}"))

    assert run(["init", "--url", "https://coho.test", "--token", "coho_pt_wrong", "-y"], ctx) == 1

    assert "Coho refused the token" in err.getvalue()
    assert "401" in err.getvalue()
    assert (library / "coho.config.json").read_text() == before
    assert not (library / ".env").exists()


def test_pull_then_generate_then_check(library: Path) -> None:
    model = (FIXTURES / "cli-next-blog.json").read_bytes()
    coho = Coho(model)
    ctx, out, _ = context(library, coho)
    run(["init", "--url", "https://coho.test", "--token", TOKEN, "--ref", "dev"], ctx)

    assert run(["pull"], ctx) == 0
    assert (library / "coho-ir.json").read_bytes() == model
    assert run(["pull"], ctx) == 0
    assert "coho-ir.json is up to date." in out.getvalue()
    assert coho.asked[-1].headers["if-none-match"] == f'"{hashlib.sha256(model).hexdigest()}"'

    assert run(["generate"], ctx) == 0
    assert (library / "src/acme/coho/blog_post.py").read_text().startswith(GENERATED_MARK)
    assert run(["check"], ctx) == 0

    (library / "src/acme/coho/blog_post.py").write_text(f"{GENERATED_MARK}\n# changed\n")
    assert run(["check"], ctx) == 1


def test_generate_removes_what_it_no_longer_generates_and_nothing_else(library: Path) -> None:
    (library / "coho-ir.json").write_bytes((FIXTURES / "cli-next-blog.json").read_bytes())
    out_dir = library / "src/acme/coho"
    out_dir.mkdir(parents=True)
    (out_dir / "gone.py").write_text(f"{GENERATED_MARK} Do not edit.\n")
    (out_dir / "mine.py").write_text("# Not generated.\n")
    ctx, _, _ = context(library, Coho(b"{}"))

    assert run(["generate"], ctx) == 0

    assert not (out_dir / "gone.py").exists()
    assert (out_dir / "mine.py").exists()


def test_pull_needs_a_token(library: Path) -> None:
    ctx, _, err = context(library, Coho(b"{}"))
    assert run(["pull"], ctx) == 1
    assert "COHO_TOKEN is not set" in err.getvalue()


def test_create_copies_the_template_renamed_and_pinned(tmp_path: Path) -> None:
    template = tmp_path / "template"
    (template / "src" / "yourorg_content").mkdir(parents=True)
    (template / "pyproject.toml").write_text(
        '[project]\nname = "yourorg-content"\ndependencies = ["coho-delivery-sdk~=2026.1.0"]\n'
        '[dependency-groups]\ndev = ["coho-codegen~=2026.1.0", "pytest>=8"]\n'
    )
    (template / "src" / "yourorg_content" / "__init__.py").write_text(
        "from yourorg_content.coho import Coho\n"
    )
    (template / ".env").write_text("COHO_TOKEN=secret\n")
    ctx, out, _ = context(tmp_path, Coho(b"{}"))

    assert run(["create", "acme-blog-content", "--template", "template"], ctx) == 0

    created = tmp_path / "acme-blog-content"
    pyproject = (created / "pyproject.toml").read_text()
    assert 'name = "acme-blog-content"' in pyproject
    assert '"coho-delivery-sdk~=' in pyproject and '"pytest>=8"' in pyproject
    assert (
        created / "src" / "acme_blog_content" / "__init__.py"
    ).read_text() == "from acme_blog_content.coho import Coho\n"
    assert not (created / ".env").exists()
    assert "the package acme-blog-content, imported as acme_blog_content" in out.getvalue()

    assert run(["create", "acme-blog-content", "--template", "template"], ctx) == 1
