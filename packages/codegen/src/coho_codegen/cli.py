"""`coho-codegen`: create a content library, point it at a project, and generate its code."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

import httpx

from . import dotenv
from .config import CodegenConfig, edit_config, load_config
from .create import bundled_template, create, package_of
from .files import drift, pull, read_type_model_file, write
from .generate import generate
from .init import describe_token
from .model import CodegenError

USAGE = """\
Usage: coho-codegen <command> [--config coho.config.json]

Commands:
  create <directory>  Create a content library from the template, named after its
                      directory, or --name. --template <folder> uses another template.
  init      Point this library at a Coho project: asks Coho which account and project a
            project token is for, and writes them to the config and the token to .env.
            --url <url>, --token <token> (or COHO_TOKEN), --ref <tag>, -y to ask nothing.
  pull      Fetch the type model for the configured ref into the type model file.
            Needs COHO_TOKEN, from the environment or a .env beside the config.
            --ref <ref> pulls another tag or branch than the config names.
  generate  Write Python for the type model into the output directory.
  check     Fail if the output directory differs from what generate would write."""


class Prompt:
    """Questions for whoever runs a command, when it runs in a terminal."""

    def ask(self, question: str, fallback: str) -> str:
        answer = input(f"{question}{f' ({fallback})' if fallback else ''}: ").strip()
        return answer or fallback

    def ask_secret(self, question: str) -> str:
        return getpass.getpass(f"{question}: ").strip()


@dataclass
class Context:
    """Where a command runs: its directory, its environment, its output, and how it reaches Coho."""

    cwd: Path
    environ: Callable[[str], str | None]
    out: TextIO
    err: TextIO
    http: httpx.Client
    prompt: Prompt | None
    shown: Callable[[Path], str] = field(init=False)

    def __post_init__(self) -> None:
        def shown(path: Path) -> str:
            try:
                return str(path.relative_to(self.cwd)) or "."
            except ValueError:
                return str(path)

        self.shown = shown


def main(argv: Sequence[str] | None = None) -> None:
    with httpx.Client(timeout=30) as http:
        context = Context(
            cwd=Path.cwd(),
            environ=os.environ.get,
            out=sys.stdout,
            err=sys.stderr,
            http=http,
            prompt=Prompt() if sys.stdin.isatty() else None,
        )
        sys.exit(run(sys.argv[1:] if argv is None else argv, context))


def run(argv: Sequence[str], context: Context) -> int:
    try:
        return _run(argv, context)
    except CodegenError as error:
        # Something to fix, not a bug: the message says what.
        print(f"error: {error}", file=context.err)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coho-codegen", add_help=False)
    parser.add_argument("command", nargs="?")
    parser.add_argument("directory", nargs="?")
    parser.add_argument("-c", "--config", default="coho.config.json")
    parser.add_argument("--ref")
    parser.add_argument("--url")
    parser.add_argument("--token")
    parser.add_argument("--name")
    parser.add_argument("--template")
    parser.add_argument("-y", "--yes", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    return parser


def _run(argv: Sequence[str], context: Context) -> int:
    parser = _parser()
    options, unknown = parser.parse_known_args(argv)
    if options.help:
        print(USAGE, file=context.out)
        return 0
    if unknown:
        raise CodegenError(f"Unknown option '{unknown[0]}'. See coho-codegen --help.")
    if options.command is None:
        print(USAGE, file=context.err)
        return 1
    if options.directory is not None and options.command != "create":
        raise CodegenError(
            f"One command at a time: '{options.command}', then '{options.directory}'"
        )

    if options.command == "create":
        return _create(options, context)

    config_file = (context.cwd / options.config).resolve()
    if options.command == "init":
        return _init(options, config_file, context)

    loaded = load_config(config_file)
    if options.command == "pull":
        # A .env beside the config may hold the token for local runs. CI sets the variable,
        # which wins: a value already in the environment is never replaced.
        token = _value(context.environ("COHO_TOKEN")) or _value(
            dotenv.read(config_file.parent / ".env").get("COHO_TOKEN")
        )
        if token is None:
            raise CodegenError("COHO_TOKEN is not set: pull needs a project token with read access")
        config = loaded.config if options.ref is None else loaded.config.with_ref(options.ref)
        pulled = pull(config, loaded.type_model, token, context.http)
        shown = context.shown(loaded.type_model)
        print(
            f"Updated {shown} from {pulled.model['source']['ref']}."
            if pulled.changed
            else f"{shown} is up to date.",
            file=context.out,
        )
        return 0
    if options.command == "generate":
        generated = generate(read_type_model_file(loaded.type_model))
        write(generated.files, loaded.out_dir)
        for warning in generated.warnings:
            print(f"warning: {warning}", file=context.err)
        count = len(generated.files)
        print(
            f"Wrote {count} {'file' if count == 1 else 'files'} to {context.shown(loaded.out_dir)}.",
            file=context.out,
        )
        return 0
    if options.command == "check":
        problems = drift(generate(read_type_model_file(loaded.type_model)).files, loaded.out_dir)
        if not problems:
            print("Generated code is up to date.", file=context.out)
            return 0
        for problem in problems:
            print(f"{context.shown(loaded.out_dir)}: {problem}", file=context.err)
        print("Generated code is out of date: run coho-codegen generate.", file=context.err)
        return 1

    print(f"Unknown command '{options.command}'.\n\n{USAGE}", file=context.err)
    return 1


def _create(options: argparse.Namespace, context: Context) -> int:
    if options.directory is None:
        raise CodegenError(
            "create needs the directory to create, such as: coho-codegen create acme-content"
        )
    directory = (context.cwd / options.directory).resolve()
    name = options.name or directory.name
    if options.template is not None:
        template = (context.cwd / options.template).resolve()
    else:
        bundled = bundled_template()
        if bundled is None:
            raise CodegenError(
                "This coho-codegen has no template bundled with it: pass --template, a checkout of "
                "https://github.com/coho-cms/coho-template-python"
            )
        template = bundled
    create(directory, name, template)

    print(
        f"Created {context.shown(directory)}: the package {name}, imported as {package_of(name)}.",
        file=context.out,
    )
    print("\nNext:", file=context.out)
    print(f"  cd {context.shown(directory)}", file=context.out)
    print("  uv sync", file=context.out)
    print(
        "  uv run coho-codegen init --url <your Coho URL> --ref <a tag, or dev>", file=context.out
    )
    return 0


def _init(options: argparse.Namespace, config_file: Path, context: Context) -> int:
    """
    Asks for what was not given, in a terminal, and checks the token with Coho before anything
    is written: a token Coho refuses leaves the library as it was.
    """
    prompt = None if options.yes else context.prompt
    existing = load_config(config_file).config if config_file.exists() else CodegenConfig()

    url: str = options.url or (
        prompt.ask("Coho URL, as `coho status` shows it", existing.url or "")
        if prompt
        else existing.url or ""
    )
    # COHO_TOKEN only with a URL to ask: the coho CLI reads the same variable, so it may be set for that.
    token = (
        options.token
        or (_value(context.environ("COHO_TOKEN")) if url else None)
        or (
            _value(prompt.ask_secret("Project token, coho_pt_… (blank to set it later)"))
            if url and prompt
            else None
        )
        or ""
    )
    if token and not url:
        raise CodegenError("A token needs the Coho URL to ask: pass --url")
    described = describe_token(url, token, context.http) if token else None
    ref: str = options.ref or (
        prompt.ask("Tag to generate from", existing.ref or "") if prompt else ""
    )

    edit_config(
        config_file,
        {
            "url": url,
            "account": described.account.id if described else None,
            "project": described.project.id if described else None,
            "ref": ref,
        },
    )
    if token:
        dotenv.write(
            config_file.parent / ".env", config_file.parent / ".env.example", "COHO_TOKEN", token
        )

    out = context.out
    print(f"Updated {config_file.name}.", file=out)
    if described is not None:
        project = described.project.name or described.project.id
        account = described.account.name or described.account.id
        print(f"It reads {project}, in {account}, with the token in .env.", file=out)
        # The library only reads types; a token that can do more is more to lose if it leaks.
        if described.role != "viewer":
            print(
                f"That token is a {described.role}. The library only reads, so a viewer token is "
                "enough: coho token create --role viewer",
                file=out,
            )

    config = load_config(config_file).config
    unset = [
        key
        for key, value in (
            ("url", config.url),
            ("account", config.account),
            ("project", config.project),
            ("ref", config.ref),
        )
        if not value
    ]
    print("\nNext:", file=out)
    if unset:
        print(f"  set {', '.join(unset)} in {config_file.name}", file=out)
    if not token:
        print(
            "  cp .env.example .env, and set COHO_TOKEN: a project token with read access", file=out
        )
    print("  uv run coho-codegen pull", file=out)
    print("  uv run coho-codegen generate", file=out)
    return 0


def _value(value: str | None) -> str | None:
    """An empty value, such as `COHO_TOKEN=`, counts as unset."""
    return value.strip() if value and value.strip() else None
