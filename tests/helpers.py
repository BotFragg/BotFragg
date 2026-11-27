"""Synthetic tokens and localized Discord doubles shared by behavior tests."""

from __future__ import annotations

import base64
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

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


class _NoopNotices:
    """Stand in for the dev notice service in tests that do not exercise it."""

    async def allow(self, _interaction: object) -> bool:
        """Allow every interaction."""
        return True

    async def deliver(self, _interaction: object) -> None:
        """Deliver nothing."""


def _text(
    key: str, *, locale: discord.Locale = TEST_LOCALE, **arguments: object
) -> str:
    """Return a localized message for a catalog key."""
    return TEST_TRANSLATOR.text(locale, key, **arguments)


def _user(user_id: int = 1, **attributes: object) -> SimpleNamespace:
    """Build a fake Discord user with a stable identity."""
    return SimpleNamespace(id=user_id, display_name="Example", **attributes)


class RecordingResponse:
    """Capture the interaction response paths a command may use."""

    def __init__(self, *, done: bool = False) -> None:
        """Start with no recorded calls."""
        self.done = done
        self.sent: list[dict[str, object]] = []
        self.deferred: list[dict[str, object]] = []
        self.edited: list[dict[str, object]] = []

    def is_done(self) -> bool:
        """Report whether the interaction already responded."""
        return self.done

    async def send_message(self, content: object = None, **kwargs: object) -> None:
        """Record one initial response."""
        self.sent.append({"content": content, **kwargs})
        self.done = True

    async def defer(self, *, thinking: bool = False, ephemeral: bool = False) -> None:
        """Record one deferred response."""
        self.deferred.append({"thinking": thinking, "ephemeral": ephemeral})
        self.done = True

    async def edit_message(self, **kwargs: object) -> None:
        """Record one message edit."""
        self.edited.append(kwargs)

    async def edit_original_response(self, **kwargs: object) -> None:
        """Record one edit of the original response."""
        self.edited.append(kwargs)


class RecordingFollowup:
    """Capture follow-up messages sent after a deferred response."""

    def __init__(self) -> None:
        """Start with no recorded messages."""
        self.sent: list[dict[str, object]] = []

    async def send(self, content: object = None, **kwargs: object) -> None:
        """Record one follow-up message."""
        self.sent.append({"content": content, **kwargs})


def _response(*, done: bool = False, **overrides: object) -> SimpleNamespace:
    """Build an async-mock response with optional behavior overrides."""
    values: dict[str, object] = {
        "is_done": Mock(return_value=done),
        "send_message": AsyncMock(),
        "defer": AsyncMock(),
        "edit_message": AsyncMock(),
        "edit_original_response": AsyncMock(),
        "send_modal": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _followup(**overrides: object) -> SimpleNamespace:
    """Build an async-mock followup with optional behavior overrides."""
    values: dict[str, object] = {"send": AsyncMock()}
    values.update(overrides)
    return SimpleNamespace(**values)


def _localized_bot(**attributes: object) -> SimpleNamespace:
    """Build a fake bot with the runtime translator used by command cogs."""
    return SimpleNamespace(translator=TEST_TRANSLATOR, **attributes)


def _localized_interaction(**attributes: object) -> SimpleNamespace:
    """Build a fake interaction with its Discord locale and client translator."""
    locale = attributes.pop("locale", TEST_LOCALE)
    user = attributes.pop("user", None) or _user()
    response = attributes.pop("response", None) or _response(done=True)
    followup = attributes.pop("followup", None) or _followup()
    client = attributes.pop("client", None) or SimpleNamespace(
        translator=TEST_TRANSLATOR, dev_notices=_NoopNotices()
    )
    edit_original_response = (
        attributes.pop("edit_original_response", None) or AsyncMock()
    )
    return SimpleNamespace(
        client=client,
        locale=locale,
        user=user,
        response=response,
        followup=followup,
        edit_original_response=edit_original_response,
        **attributes,
    )
