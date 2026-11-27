"""Fluent catalogs for Discord command metadata and BotFragg messages."""

from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from fluent.runtime import AbstractResourceLoader, FluentLocalization, FluentResource

if TYPE_CHECKING:
    from fluent.syntax.ast import Resource

log = logging.getLogger(__name__)
DEFAULT_LOCALE = "en-US"
LOCALES_DIR = Path(__file__).resolve().parents[1] / "locales"


class _FluentFileLoader(AbstractResourceLoader):
    """Read Fluent resources without fluent.runtime's deprecated codec loader."""

    # shortcut: fluent.runtime 0.4.0 is the latest release; remove this loader
    # once it stops using codecs.open().

    def __init__(self, root: Path) -> None:
        """Store the directory containing one subdirectory per locale."""
        self.root = root

    def resources(
        self, locale: str, resource_ids: list[str]
    ) -> Generator[list[Resource]]:
        """Yield parsed resources for one locale, skipping missing files."""
        resources: list[Resource] = []
        for resource_id in resource_ids:
            path = self.root / locale / resource_id
            if path.is_file():
                resources.append(FluentResource(path.read_text(encoding="utf-8")))
        if resources:
            yield resources


class BotFraggTranslator(app_commands.Translator):
    """Translate Discord command metadata and runtime messages from Fluent files."""

    def __init__(self, locales_dir: Path = LOCALES_DIR) -> None:
        """Load catalog files lazily and keep one fallback bundle per locale."""
        self._loader = _FluentFileLoader(locales_dir)
        self._catalogs: dict[str, FluentLocalization] = {}

    def _catalog(self, locale: str) -> FluentLocalization:
        """Create and cache a locale bundle with English as a fallback."""
        if locale not in self._catalogs:
            locales = [locale]
            if locale != DEFAULT_LOCALE:
                locales.append(DEFAULT_LOCALE)
            self._catalogs[locale] = FluentLocalization(
                locales, ["messages.ftl"], self._loader
            )
        return self._catalogs[locale]

    def text(
        self, locale: discord.Locale | str | None, key: str, **arguments: object
    ) -> str:
        """Format a message, falling back to the English catalog when needed."""
        locale_code = locale.value if isinstance(locale, discord.Locale) else locale
        locale_code = locale_code or DEFAULT_LOCALE
        try:
            value = self._catalog(locale_code).format_value(key, arguments)
        except Exception:
            log.exception(f"could not format '{key}' for {locale_code}")
            value = None
        if value is not None:
            return value
        if locale_code != DEFAULT_LOCALE:
            try:
                value = self._catalog(DEFAULT_LOCALE).format_value(key, arguments)
            except Exception:
                log.exception(f"could not format '{key}' in English")
            if value is not None:
                return value
        if key.islower() and " " not in key:
            log.error(f"missing English message '{key}'")
        return key

    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContext,
    ) -> str | None:
        """Return a translated command string or defer to Discord's English source."""
        key = string.extras.get("key")
        if not isinstance(key, str):
            return None
        translated = self.text(locale, key)
        return translated if translated not in {key, string.message} else None
