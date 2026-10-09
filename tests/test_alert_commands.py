"""Behavior and regression checks for alert commands."""

from __future__ import annotations

import time
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from cryptography.fernet import Fernet

from src.cogs.valorant.alerts import AlertsCog
from src.models import Account, Alert, User
from src.services.auth import AuthService
from src.services.catalog import Skin
from src.services.crypto import AuthVault
from src.services.http import HTTPResult
from src.services.shop import ShopService
from tests.helpers import _fake_jwt, _localized_bot, _localized_interaction


def test_alert_keeps_qotix_direct_skin_input() -> None:
    """Verify that alert keeps Qotix direct skin input."""
    command = AlertsCog.alert
    assert [parameter.name for parameter in command.parameters] == ["skin"]


@pytest.mark.parametrize("alert_login_valid", [False, True])
async def test_testalerts_uses_alert_account_login(backend_database, alert_login_valid):
    owner = await User.create(id=101, current_account_id="selected")
    auth = AuthService(
        NS(token_refresh_buffer_minutes=5, auto_refresh_tokens=False),
        NS(),
        AuthVault(Fernet.generate_key().decode()),
    )

    def credentials(puuid):
        return auth.vault.encrypt(
            {
                "rso": _fake_jwt(sub=puuid, exp=int(time.time()) + 3600),
                "ent": "synthetic-entitlement",
            }
        )

    await Account.create(
        puuid="selected",
        user=owner,
        username="Selected#TEST",
        region="na",
        auth_blob=None if alert_login_valid else credentials("selected"),
    )
    linked = await Account.create(
        puuid="alert-account",
        user=owner,
        username="AlertOwner#TEST",
        region="na",
        auth_blob=credentials("alert-account") if alert_login_valid else None,
    )
    skin = Skin(str(UUID(int=1)), "synthetic-offer", "Synthetic skin", None, None)
    await Alert.create(account=linked, skin_uuid=skin.uuid)
    request = AsyncMock(
        return_value=HTTPResult(
            200,
            {
                "SkinsPanelLayout": {
                    "SingleItemOffersRemainingDurationInSeconds": 3600,
                    "SingleItemOffers": [skin.uuid],
                }
            },
        )
    )
    catalog = NS(get_skin=lambda _: skin, update_prices=lambda _: None)
    shop = ShopService(NS(use_shop_cache=False), NS(request=request), auth, catalog)
    cog = AlertsCog(
        _localized_bot(
            register_component=lambda *args: None,
            auth=auth,
            shop=shop,
            catalog=catalog,
            emoji_service=NS(skin_name=lambda name, tier: name),
        )
    )
    interaction = _localized_interaction(
        user=NS(id=owner.id, send=AsyncMock()),
        response=NS(defer=AsyncMock(), is_done=lambda: True),
        followup=NS(send=AsyncMock()),
    )
    await AlertsCog.testalerts.callback(cog, interaction)
    if alert_login_valid:
        request.assert_awaited_once()
        assert request.await_args.args[1].endswith("/storefront/alert-account")
        interaction.user.send.assert_awaited_once()
        assert (
            "AlertOwner#TEST"
            in interaction.user.send.await_args.kwargs["embed"].description
        )
        key = "test-alerts-sent"
    else:
        request.assert_not_awaited()
        interaction.user.send.assert_not_awaited()
        key = "error-riot-login-expired"
    sent = interaction.followup.send.await_args.kwargs
    assert sent["embed"].description == cog.bot.translator.text(interaction.locale, key)
