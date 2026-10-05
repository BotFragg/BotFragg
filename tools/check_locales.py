"""Check Fluent catalogs, source message IDs, and translated placeholders."""

from __future__ import annotations

import ast as python_ast
import re
import sys
from pathlib import Path

import discord
from fluent.syntax import FluentParser, ast

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "locales"
MESSAGE_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$")
PLACEHOLDER = re.compile(r"\{\s*\$([a-zA-Z][a-zA-Z0-9_-]*)")
PREFIXES = {
    "account",
    "accounts",
    "alert",
    "alerts",
    "balance",
    "battlepass",
    "botinfo",
    "bundles",
    "command",
    "common",
    "component",
    "deletedata",
    "error",
    "group",
    "help",
    "link",
    "links",
    "login",
    "logout",
    "mission",
    "missions",
    "option",
    "penalties",
    "ping",
    "setting",
    "settings",
    "shard",
    "shop",
    "staff",
    "suggestion",
    "suggestions",
    "test",
}
DYNAMIC_MESSAGE_IDS = {
    "command-suggestion-description",
    "error-riot-services-unavailable",
    "login-account-already-linked",
    "login-account-details-missing",
    "login-account-details-unavailable",
    "login-attempt-expired",
    "login-code-missing",
    "login-code-rejected",
    "login-failed",
    "login-nonce-mismatch",
    "login-token-no-account",
    "suggestion-status-approved",
    "suggestion-status-denied",
    "penalties-effect-delayed-penalty",
    "penalties-effect-game-ban",
    "penalties-effect-queue-delay",
    "penalties-effect-queue-restriction",
    "penalties-effect-ranked-rating-penalty",
    "penalties-effect-riot-restriction",
    "penalties-effect-riot-notification",
    "penalties-effect-xp-multiplier",
    "penalties-effect-premier-restriction",
    "penalties-effect-warning",
}


def catalog(path: Path) -> dict[str, str]:
    """Parse one Fluent catalog and return its message source for placeholder checks."""
    source = path.read_text(encoding="utf-8")
    resource = FluentParser().parse(source)
    entries: dict[str, str] = {}
    errors = []
    for entry in resource.body:
        if isinstance(entry, ast.Junk):
            line = source[: entry.span.start].count("\n") + 1
            errors.append(f"invalid Fluent syntax near line {line}")
        elif isinstance(entry, ast.Message):
            message_id = entry.id.name
            if message_id in entries:
                errors.append(f"duplicate message ID {message_id!r}")
            entries[message_id] = source[entry.span.start : entry.span.end]
    if errors:
        raise ValueError("; ".join(errors))
    return entries


def source_message_ids() -> set[str]:
    """Find literal localization IDs in command, component, and bot source."""
    paths = [
        ROOT / "src" / "bot.py",
        ROOT / "src" / "localization.py",
        ROOT / "src" / "services" / "auth.py",
    ]
    paths.extend((ROOT / "src" / "cogs").rglob("*.py"))
    paths.extend((ROOT / "src" / "views").rglob("*.py"))
    ids = set(DYNAMIC_MESSAGE_IDS)
    for path in paths:
        tree = python_ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in python_ast.walk(tree):
            if (
                isinstance(node, python_ast.Constant)
                and isinstance(node.value, str)
                and MESSAGE_ID.fullmatch(node.value)
                and node.value.partition("-")[0] in PREFIXES
            ):
                ids.add(node.value)
    return ids


def source_message_variables() -> dict[str, set[str]]:
    """Return the named arguments supplied at each literal translation call."""
    variables: dict[str, set[str]] = {
        message_id: set() for message_id in DYNAMIC_MESSAGE_IDS
    }

    def literal(node: python_ast.expr | None) -> str | None:
        return (
            node.value
            if isinstance(node, python_ast.Constant) and isinstance(node.value, str)
            else None
        )

    def dictionary_keys(node: python_ast.expr | None) -> set[str]:
        if not isinstance(node, python_ast.Dict):
            return set()
        return {
            key.value
            for key in node.keys
            if isinstance(key, python_ast.Constant) and isinstance(key.value, str)
        }

    for path in (ROOT / "src").rglob("*.py"):
        tree = python_ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in python_ast.walk(tree):
            if not isinstance(node, python_ast.Call):
                continue
            function = node.func
            name = (
                function.id
                if isinstance(function, python_ast.Name)
                else function.attr
                if isinstance(function, python_ast.Attribute)
                else ""
            )
            key = None
            supplied = {item.arg for item in node.keywords if item.arg is not None}
            if name == "locale_str":
                key = next(
                    (
                        literal(item.value)
                        for item in node.keywords
                        if item.arg == "key"
                    ),
                    None,
                )
                supplied = set()
            elif name in {"translated", "error", "text"} and len(node.args) > 1:
                key = literal(node.args[1])
            elif name == "localized_embed":
                key = literal(node.args[1]) if len(node.args) > 1 else None
                description_args = next(
                    (
                        item.value
                        for item in node.keywords
                        if item.arg == "description_args"
                    ),
                    None,
                )
                if key:
                    supplied = dictionary_keys(description_args)
            if key:
                if name == "localized_embed":
                    title_key = next(
                        (
                            literal(item.value)
                            for item in node.keywords
                            if item.arg == "title_key"
                        ),
                        None,
                    )
                    title_args = next(
                        (
                            item.value
                            for item in node.keywords
                            if item.arg == "title_args"
                        ),
                        None,
                    )
                    if title_key:
                        supplied_title = dictionary_keys(title_args)
                        previous = variables.setdefault(title_key, supplied_title)
                        if previous != supplied_title:
                            raise ValueError(
                                f"Inconsistent arguments for {title_key!r}"
                            )
                previous = variables.setdefault(key, supplied)
                if previous != supplied:
                    raise ValueError(f"Inconsistent arguments for {key!r}")
    return variables


def main() -> int:
    """Validate all supported locale files against the English source catalog."""
    english_path = LOCALES / "en-US" / "messages.ftl"
    if not english_path.is_file():
        print(f"Missing English catalog: {english_path.relative_to(ROOT)}")
        return 1
    try:
        english = catalog(english_path)
    except (OSError, ValueError) as exc:
        print(f"Invalid English catalog: {exc}")
        return 1

    missing = sorted(source_message_ids() - english.keys())
    if missing:
        print("Missing English message IDs:")
        for message_id in missing:
            print(f"  {message_id}")
        return 1

    source_variables = source_message_variables()
    for message_id, supplied in source_variables.items():
        if message_id not in english:
            continue
        catalog_variables = set(PLACEHOLDER.findall(english[message_id]))
        if catalog_variables != supplied:
            print(
                f"en-US:{message_id} placeholders differ: "
                f"expected source arguments {sorted(supplied)}, "
                f"found {sorted(catalog_variables)}"
            )
            return 1

    supported = {locale.value for locale in discord.Locale}
    for directory in (path for path in LOCALES.iterdir() if path.is_dir()):
        if directory.name not in supported:
            print(f"Unsupported Discord locale directory: {directory.name}")
            return 1
        if not (directory / "messages.ftl").is_file():
            print(f"Missing catalog file in locale directory: {directory.name}")
            return 1
    catalogs = list(LOCALES.glob("*/messages.ftl"))
    for path in catalogs:
        locale = path.parent.name
        if locale not in supported:
            print(f"Unsupported Discord locale directory: {locale}")
            return 1
        if path == english_path:
            continue
        try:
            translated = catalog(path)
        except (OSError, ValueError) as exc:
            print(f"Invalid {locale} catalog: {exc}")
            return 1
        unknown = sorted(translated.keys() - english.keys())
        if unknown:
            print(f"{locale} contains unknown message IDs: {', '.join(unknown)}")
            return 1
        for message_id, text in translated.items():
            source_variables = set(PLACEHOLDER.findall(english[message_id]))
            translated_variables = set(PLACEHOLDER.findall(text))
            if source_variables != translated_variables:
                print(
                    f"{locale}:{message_id} placeholders differ: "
                    f"expected {sorted(source_variables)}, got {sorted(translated_variables)}"
                )
                return 1

    print(f"Validated {len(catalogs)} Discord locale catalog(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
