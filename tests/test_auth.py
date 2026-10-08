"""Behavior checks for auth."""

from __future__ import annotations

import asyncio
import base64
import json
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import discord
import pytest
from cryptography.fernet import Fernet

from src.cogs.valorant.alerts import AlertsCog
from src.models import (
    Account,
    User,
)
from src.services.auth import (
    AuthenticationRequired,
    AuthService,
    decode_jwt,
    token_expiry,
)
from src.services.crypto import AuthVault
from src.services.http import HTTPFailure
from src.services.shop import (
    ShopData,
    ShopService,
    ShopUnavailable,
)
from tests.helpers import (
    _fake_access_token,
    _fake_jwt,
    _localized_bot,
    _localized_interaction,
)

_OPTIONAL_URLS = (
    "SUPPORT_URL",
    "VOTE_URL",
    "WEBSITE_URL",
    "SHARD_LOG_WEBHOOK_URL",
)


async def test_expired_shop_cache_entry_is_removed_when_auth_fails() -> None:
    """Verify that expired shop cache entry is removed when auth fails."""

    class Auth:
        """Stub authentication with controlled Riot credentials and login outcomes for service tests."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return the test authorization headers for the fake account."""
            raise AuthenticationRequired("Riot credentials are unavailable")

    service = ShopService(SimpleNamespace(use_shop_cache=True), None, Auth(), None)
    account = SimpleNamespace(puuid="expired-shop-auth")
    service._cache[account.puuid] = ShopData([], [], [], int(time.time()) - 1, None)

    with pytest.raises(AuthenticationRequired):
        await service.storefront(account)

    assert account.puuid not in service._cache


@pytest.mark.usefixtures("database")
async def test_concurrent_auth_ensure_serializes_entitlement_repair() -> None:
    """Verify that concurrent auth ensure serializes entitlement repair."""
    user = await User.create(id=654)
    vault = AuthVault(Fernet.generate_key().decode())
    account = await Account.create(
        puuid="auth-race",
        user=user,
        username="One#NA",
        auth_blob=vault.encrypt(
            {"rso": _fake_access_token(), "refresh_token": "refresh"}
        ),
    )

    class RejectingHTTP:
        """Reject entitlement requests to verify concurrent authentication checks serialize repair."""

        requests = 0

        async def request(self, *args, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            self.requests += 1
            return SimpleNamespace(status=400, data={"error": "invalid_grant"})

    http = RejectingHTTP()
    service = AuthService(
        SimpleNamespace(token_refresh_buffer_minutes=5, auto_refresh_tokens=True),
        http,
        vault,
    )
    entitlement_started = asyncio.Event()
    release_entitlement = asyncio.Event()
    entitlement_calls = 0

    async def entitlement(_auth) -> str | None:
        """Return the configured fake entitlement response."""
        nonlocal entitlement_calls
        entitlement_calls += 1
        if entitlement_calls == 1:
            entitlement_started.set()
            await release_entitlement.wait()
            return "entitlement"
        return None

    service._entitlement = entitlement
    first = asyncio.create_task(service.ensure(account))
    await asyncio.wait_for(entitlement_started.wait(), timeout=1)
    second = asyncio.create_task(service.ensure(account))
    try:
        await asyncio.sleep(0.01)
    finally:
        release_entitlement.set()

    first_result, second_result = await asyncio.wait_for(
        asyncio.gather(first, second), timeout=1
    )
    saved = await Account.get(puuid=account.puuid)
    assert first_result.success and second_result.success
    assert entitlement_calls == 1
    assert http.requests == 0
    assert vault.decrypt(saved.auth_blob)["ent"] == "entitlement"


@pytest.mark.usefixtures("database")
async def test_auth_refresh_transients_do_not_become_login_required() -> None:
    """Verify that auth refresh transients do not become login required."""
    user = await User.create(id=655)
    vault = AuthVault(Fernet.generate_key().decode())
    account = await Account.create(
        puuid="auth-refresh-transient",
        user=user,
        username="One#NA",
        auth_blob=vault.encrypt(
            {"rso": _fake_access_token(expires_in=-1), "refresh_token": "refresh"}
        ),
    )

    class FailingHTTP:
        """Return controlled Riot API failures for retry and authentication-state assertions."""

        async def request(self, *args, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            raise HTTPFailure("transport unavailable")

    service = AuthService(
        SimpleNamespace(token_refresh_buffer_minutes=5, auto_refresh_tokens=True),
        FailingHTTP(),
        vault,
    )

    with pytest.raises(HTTPFailure):
        await service.auth_headers(account)

    saved = await Account.get(puuid=account.puuid)
    assert vault.decrypt(saved.auth_blob).get("refresh_token")


@pytest.mark.usefixtures("database")
async def test_entitlement_transients_do_not_become_login_required() -> None:
    """Verify that entitlement transients do not become login required."""
    user = await User.create(id=657)
    vault = AuthVault(Fernet.generate_key().decode())
    account = await Account.create(
        puuid="auth-entitlement-transient",
        user=user,
        username="One#NA",
        auth_blob=vault.encrypt(
            {"rso": _fake_access_token(), "refresh_token": "refresh"}
        ),
    )

    class FailingHTTP:
        """Return controlled Riot API failures for retry and authentication-state assertions."""

        async def request(self, *args, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            raise HTTPFailure("transport unavailable")

    service = AuthService(
        SimpleNamespace(token_refresh_buffer_minutes=5, auto_refresh_tokens=True),
        FailingHTTP(),
        vault,
    )

    with pytest.raises(HTTPFailure):
        await service.auth_headers(account)

    saved = await Account.get(puuid=account.puuid)
    assert "ent" not in vault.decrypt(saved.auth_blob)


@pytest.mark.parametrize("status", [408, 425, 500, 503])
@pytest.mark.usefixtures("database")
async def test_auth_refresh_transient_status_does_not_become_login_required(
    status,
) -> None:
    """Verify that auth refresh transient status does not become login required."""
    user = await User.create(id=658)
    vault = AuthVault(Fernet.generate_key().decode())
    account = await Account.create(
        puuid="auth-refresh-http-error",
        user=user,
        username="One#NA",
        auth_blob=vault.encrypt(
            {"rso": _fake_access_token(expires_in=-1), "refresh_token": "refresh"}
        ),
    )

    class FailingHTTP:
        """Return controlled Riot API failures for retry and authentication-state assertions."""

        async def request(self, *args, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            return SimpleNamespace(status=status, data={})

    service = AuthService(
        SimpleNamespace(token_refresh_buffer_minutes=5, auto_refresh_tokens=True),
        FailingHTTP(),
        vault,
    )

    with pytest.raises(HTTPFailure):
        await service.auth_headers(account)


@pytest.mark.parametrize("status", [408, 425, 500, 503])
@pytest.mark.usefixtures("database")
async def test_entitlement_transient_status_does_not_become_login_required(
    status,
) -> None:
    """Verify that entitlement transient status does not become login required."""
    user = await User.create(id=659)
    vault = AuthVault(Fernet.generate_key().decode())
    account = await Account.create(
        puuid="auth-entitlement-http-error",
        user=user,
        username="One#NA",
        auth_blob=vault.encrypt(
            {"rso": _fake_access_token(), "refresh_token": "refresh"}
        ),
    )

    class FailingHTTP:
        """Return controlled Riot API failures for retry and authentication-state assertions."""

        async def request(self, *args, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            return SimpleNamespace(status=status, data={})

    service = AuthService(
        SimpleNamespace(token_refresh_buffer_minutes=5, auto_refresh_tokens=True),
        FailingHTTP(),
        vault,
    )

    with pytest.raises(HTTPFailure):
        await service.auth_headers(account)


async def test_shop_wallet_normalizes_transient_auth_failures() -> None:
    """Verify that shop wallet normalizes transient auth failures."""

    class FailingAuth:
        """Raise controlled credential errors so dependent services can classify login failures."""

        async def auth_headers(self, _account) -> dict[str, str]:
            """Return the test authorization headers for the fake account."""
            raise HTTPFailure("transport unavailable")

    service = ShopService(SimpleNamespace(), None, FailingAuth(), None)

    with pytest.raises(ShopUnavailable):
        await service.wallet(SimpleNamespace(puuid="wallet-auth"))


@pytest.mark.usefixtures("database")
async def test_concurrent_login_callbacks_respect_account_limit() -> None:
    """Verify that concurrent login callbacks respect account limit."""
    discord_id = 656
    vault = AuthVault(Fernet.generate_key().decode())
    token_calls = 0
    detail_calls = 0
    first_token_started = asyncio.Event()
    both_tokens_started = asyncio.Event()
    all_details_started = asyncio.Event()
    nonces: dict[str, str] = {}

    class LoginHTTP:
        """Provide controlled OAuth responses for concurrent login and account-limit scenarios."""

        async def request(self, method, url, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            nonlocal token_calls, detail_calls
            if url.endswith("/token"):
                form = parse_qs(kwargs["data"])
                code = form["code"][0]
                token_calls += 1
                if token_calls == 1:
                    first_token_started.set()
                if token_calls == 2:
                    both_tokens_started.set()
                await both_tokens_started.wait()
                puuid = f"riot-{code}"
                return SimpleNamespace(
                    status=200,
                    data={
                        "access_token": _fake_jwt(
                            sub=puuid, exp=int(time.time()) + 3600
                        ),
                        "id_token": _fake_jwt(nonce=nonces[code]),
                    },
                )

            detail_calls += 1
            if detail_calls == 6:
                all_details_started.set()
            await all_details_started.wait()
            if url.endswith("/userinfo"):
                authorization = kwargs["headers"]["Authorization"]
                puuid = decode_jwt(authorization.removeprefix("Bearer "))["sub"]
                return SimpleNamespace(
                    status=200,
                    data={"acct": {"game_name": puuid, "tag_line": "NA"}},
                )
            if url.endswith("/api/token/v1"):
                return SimpleNamespace(
                    status=200, data={"entitlements_token": "entitlement"}
                )
            if url.endswith("/product/valorant"):
                return SimpleNamespace(status=200, data={"affinities": {"live": "na"}})
            raise AssertionError(f"Unexpected Riot URL: {url}")

    service = AuthService(SimpleNamespace(max_accounts_per_user=1), LoginHTTP(), vault)

    first_url = service.login_url(discord_id)
    nonces["first"] = parse_qs(urlparse(first_url).query)["nonce"][0]
    first = asyncio.create_task(
        service.redeem_callback(discord_id, "http://localhost/redirect?code=first")
    )
    await asyncio.wait_for(first_token_started.wait(), timeout=1)

    second_url = service.login_url(discord_id)
    nonces["second"] = parse_qs(urlparse(second_url).query)["nonce"][0]
    second = asyncio.create_task(
        service.redeem_callback(discord_id, "http://localhost/redirect?code=second")
    )
    first_result, second_result = await asyncio.wait_for(
        asyncio.gather(first, second), timeout=2
    )

    assert sorted((first_result.success, second_result.success)) == [False, True]
    limit_failure = first_result if not first_result.success else second_result
    assert limit_failure.error_key == "login-account-limit"
    assert limit_failure.error_arguments == {"max_accounts": 1}
    assert await Account.filter(user_id=discord_id).count() == 1


@pytest.mark.usefixtures("database")
async def test_logout_clears_credentials_saved_during_refresh() -> None:
    """Verify that logout clears credentials saved during refresh."""
    user = await User.create(id=655)
    vault = AuthVault(Fernet.generate_key().decode())
    account = await Account.create(
        puuid="logout-race",
        user=user,
        username="One#NA",
        auth_blob=vault.encrypt(
            {"rso": _fake_access_token(), "refresh_token": "refresh"}
        ),
    )

    class RefreshHTTP:
        """Pause token refresh requests so logout can protect credentials updated concurrently."""

        async def request(self, *args, **kwargs):
            """Record request arguments and return the configured HTTP response."""
            return SimpleNamespace(
                status=200, data={"access_token": _fake_access_token()}
            )

    service = AuthService(
        SimpleNamespace(token_refresh_buffer_minutes=5, auto_refresh_tokens=True),
        RefreshHTTP(),
        vault,
    )
    entitlement_started = asyncio.Event()
    release_entitlement = asyncio.Event()

    async def entitlement(_auth) -> str:
        """Return the configured fake entitlement response."""
        entitlement_started.set()
        await release_entitlement.wait()
        return "entitlement"

    service._entitlement = entitlement
    refreshing = asyncio.create_task(service.refresh(account, force=True))
    await asyncio.wait_for(entitlement_started.wait(), timeout=1)
    logout = asyncio.create_task(service.clear_credentials(account))
    await asyncio.sleep(0)
    release_entitlement.set()

    result = await asyncio.wait_for(refreshing, timeout=1)
    await asyncio.wait_for(logout, timeout=1)
    saved = await Account.get(puuid=account.puuid)
    assert result.success
    assert saved.auth_blob is None


async def test_testalerts_reports_temporary_auth_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that testalerts reports temporary auth failure."""
    account = SimpleNamespace(username="Player#NA")
    alert = SimpleNamespace(account=account)
    sent: list[discord.Embed] = []

    async def selected_account(_user_id: int) -> SimpleNamespace:
        """Return the configured active account for the command under test."""
        return account

    async def first_alert(_user_id: int) -> SimpleNamespace:
        """Return the alert fixture used by the command under test."""
        return alert

    class Response:
        """Capture whether an interaction was deferred and whether its initial response was private."""

        async def defer(self, *, thinking: bool, ephemeral: bool) -> None:
            """Record that the fake interaction response was deferred."""
            assert thinking and ephemeral

        def is_done(self) -> bool:
            """Report whether the fake interaction response has been sent."""
            return True

    class Followup:
        """Capture outgoing embeds and privacy flags sent after an interaction's initial response."""

        async def send(self, *, embed: discord.Embed, ephemeral: bool) -> None:
            """Record the follow-up message sent through the fake interaction."""
            assert ephemeral
            sent.append(embed)

    class Auth:
        """Stub authentication with controlled Riot credentials and login outcomes for service tests."""

        async def ensure(self, _account: object) -> None:
            """Return the configured fake authentication result."""
            raise HTTPFailure("temporarily unavailable")

    monkeypatch.setattr("src.cogs.valorant.alerts.selected_account", selected_account)
    monkeypatch.setattr("src.cogs.valorant.alerts.first_alert", first_alert)
    interaction = _localized_interaction(
        user=SimpleNamespace(id=123), response=Response(), followup=Followup()
    )

    await AlertsCog.testalerts.callback(
        AlertsCog(_localized_bot(auth=Auth(), register_component=lambda *_args: None)),
        interaction,
    )

    assert sent[0].description == (
        "Riot authentication is currently unavailable. Please try again later."
    )


def test_jwt_decode_and_expiry() -> None:
    """Verify that JWT decode and expiry."""

    expires = int(time.time()) + 3600
    payload = (
        base64.urlsafe_b64encode(json.dumps({"sub": "puuid", "exp": expires}).encode())
        .decode()
        .rstrip("=")
    )
    token = f"x.{payload}.y"
    assert decode_jwt(token)["sub"] == "puuid"
    assert token_expiry(token) == expires
    assert decode_jwt("broken") == {}
