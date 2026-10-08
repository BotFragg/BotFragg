"""Behavior and regression checks for localization."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import discord
import pytest
from cryptography.fernet import Fernet

from src.cogs.valorant.settings import SETTINGS, SettingsCog
from src.localization import BotFraggTranslator
from src.services.auth import AuthService
from src.services.crypto import AuthVault


def token(**claims):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"synthetic.{payload}.signature"


@pytest.mark.parametrize("locale", ["el", "hu", "vi"])
def test_localized_suggestion_commands_have_distinct_names(locale):
    translator = BotFraggTranslator()
    assert translator.text(locale, "command-suggest-name") != translator.text(
        locale, "group-suggestion-name"
    )


def test_locale_checker_rejects_sibling_command_name_collisions(tmp_path):
    """The normal locale checker must catch the audited registration collision."""
    from pathlib import Path

    from tools.check_locales import command_name_errors, source_command_names

    path = tmp_path / "el" / "messages.ftl"
    path.parent.mkdir()
    original = Path("locales/el/messages.ftl").read_text(encoding="utf-8")
    path.write_text(original, encoding="utf-8")
    scopes = source_command_names()
    assert command_name_errors(path, scopes) == []
    name = BotFraggTranslator().text("el", "command-suggest-name")
    original = original.replace(
        "group-suggestion-name = "
        + BotFraggTranslator().text("el", "group-suggestion-name"),
        "group-suggestion-name = " + name,
    )
    path.write_text(original, encoding="utf-8")
    assert len(command_name_errors(path, scopes)) == 1


@pytest.mark.parametrize("field", ["access_token", "id_token", "refresh_token"])
async def test_malformed_callback_tokens_return_localized_error(field):
    vault = AuthVault(Fernet.generate_key().decode())
    request = AsyncMock()
    service = AuthService(NS(), NS(request=request), vault)
    service.login_url(101)
    nonce = service._pending_nonces[101][0]
    data = {
        "access_token": token(sub="synthetic"),
        "id_token": token(nonce=nonce),
        field: ["malformed"],
    }
    request.return_value = NS(status=200, data=data)
    result = await service.redeem_callback(
        101, "http://localhost/redirect?code=synthetic"
    )
    assert not result.success
    assert result.error_key == "error-riot-auth-temporarily-unavailable"
    assert request.await_count == 1


@pytest.mark.parametrize("callback", ["http://[", "http://[not-an-ip]/?code=synthetic"])
async def test_invalid_callback_url_returns_a_localized_failure(callback):
    auth = AuthService(NS(), NS(request=AsyncMock()), NS())
    auth.login_url(101)
    result = await auth.redeem_callback(101, callback)
    assert not result.success and result.error_key == "login-code-missing"
    assert 101 in auth._pending_nonces
    assert auth.http.request.await_count == 0


@pytest.mark.parametrize("field", list(SETTINGS))
@pytest.mark.parametrize("locale", list(discord.Locale))
async def test_settings_prompt_uses_the_interaction_locale(field, locale, monkeypatch):
    import src.cogs.valorant.settings as module

    monkeypatch.setattr(module, "get_user", AsyncMock(return_value=NS(id=101)))
    bot = NS(register_component=lambda *args: None, translator=BotFraggTranslator())
    interaction = NS(
        user=NS(id=101),
        client=bot,
        locale=locale,
        response=NS(defer=AsyncMock()),
        followup=NS(send=AsyncMock()),
    )
    english_label, key = SETTINGS[field]
    # discord.py's ChoiceTransformer returns the original registered Choice.
    choice = discord.app_commands.Choice(name=english_label, value=field)
    await SettingsCog.settings_set.callback(SettingsCog(bot), interaction, choice)
    sent = interaction.followup.send.call_args.kwargs
    localized_label = bot.translator.text(interaction.locale, key)
    assert localized_label in sent["embed"].description
    assert localized_label in sent["view"].children[0].item.placeholder


async def test_callback_without_a_code_is_a_localized_failure():
    auth = AuthService(NS(), NS(request=AsyncMock()), NS())
    result = await auth.redeem_callback(101, "http://localhost/redirect")
    assert result.error_key == "login-code-missing"
    assert auth.http.request.await_count == 0
