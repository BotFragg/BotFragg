"""Synthetic tokens and localized Discord doubles shared by behavior tests."""

from __future__ import annotations

import base64
import json
import time
from types import SimpleNamespace

import discord

from src.localization import BotFraggTranslator


def _fake_access_token(expires_in: int = 3600) -> str:
    """Create a JWT-shaped access token with the requested expiry."""
    expiry = int(time.time()) + expires_in
    payload = (
        base64.urlsafe_b64encode(json.dumps({"exp": expiry}).encode())
        .decode()
        .rstrip("=")
    )
    return f"x.{payload}.x"


def _fake_jwt(**claims: object) -> str:
    """Create a JWT-shaped token containing the supplied claims."""
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"x.{payload}.x"


TEST_TRANSLATOR = BotFraggTranslator()

TEST_LOCALE = discord.Locale.american_english


def _localized_bot(**attributes: object) -> SimpleNamespace:
    """Build a fake bot with the runtime translator used by command cogs."""
    return SimpleNamespace(translator=TEST_TRANSLATOR, **attributes)


def _localized_interaction(**attributes: object) -> SimpleNamespace:
    """Build a fake interaction with its Discord locale and client translator."""
    return SimpleNamespace(
        client=SimpleNamespace(translator=TEST_TRANSLATOR),
        locale=TEST_LOCALE,
        **attributes,
    )
