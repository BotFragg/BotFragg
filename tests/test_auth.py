"""Behavior and regression checks for auth."""

from __future__ import annotations

import asyncio
import base64
import json
import time
import time as clock
from types import SimpleNamespace
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import discord
import pytest
from cryptography.fernet import Fernet
from tortoise import Tortoise, connections
from tortoise.exceptions import DBConnectionError
from tortoise.queryset import UpdateQuery

from src.cogs.valorant.alerts import AlertsCog
from src.cogs.valorant.login import LoginCog
from src.localization import BotFraggTranslator
from src.models import (
    Account,
    User,
)
from src.services.accounts import delete_user_data
from src.services.auth import (
    AuthenticationRequired,
    AuthService,
    decode_jwt,
    token_expiry,
)
from src.services.crypto import AuthVault
from src.services.http import HTTPFailure, HTTPResult
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


def token(**claims):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"synthetic.{payload}.signature"


def lifetime_jwt(**claims):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"x.{payload}.x"


def auth_service(http=None):
    return AuthService(
        NS(
            token_refresh_buffer_minutes=5,
            auto_refresh_tokens=True,
            max_accounts_per_user=10,
        ),
        http or NS(),
        AuthVault(Fernet.generate_key().decode()),
    )


def refresh_jwt(**claims):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"synthetic.{payload}.synthetic"


@pytest.mark.usefixtures("database")
@pytest.mark.parametrize("committed, failures", [(False, 1), (False, 4), (True, 1)])
async def test_rotated_refresh_is_saved_without_repeating_exchange(
    monkeypatch, committed, failures
):
    service = auth_service(
        NS(
            request=AsyncMock(
                side_effect=[
                    HTTPResult(
                        200,
                        {
                            "access_token": _fake_access_token(),
                            "refresh_token": "rotated",
                        },
                    ),
                    HTTPResult(200, {"entitlements_token": "new-ent"}),
                ]
            )
        )
    )
    user = await User.create(id=110)
    account = await Account.create(
        puuid="rotated",
        user=user,
        username="Synthetic#TEST",
        auth_blob=service.vault.encrypt(
            {"rso": _fake_access_token(-1), "refresh_token": "old"}
        ),
    )
    original = UpdateQuery._execute
    failed = 0

    async def interrupted_save(query):
        nonlocal failed
        if query.model is Account and failed < failures:
            failed += 1
            if committed:
                await original(query)
            raise DBConnectionError("Synthetic interrupted save")
        return await original(query)

    monkeypatch.setattr(UpdateQuery, "_execute", interrupted_save)
    for _ in range(failures):
        with pytest.raises(DBConnectionError):
            await service.auth_headers(account)
    headers = await service.auth_headers(account)
    saved = await Account.get(puuid=account.puuid)
    assert headers["X-Riot-Entitlements-JWT"] == "new-ent"
    assert service.vault.decrypt(saved.auth_blob)["refresh_token"] == "rotated"  # noqa: S105
    assert service.http.request.await_count == 2


@pytest.mark.usefixtures("database")
@pytest.mark.parametrize("action", ["relogin", "logout", "delete"])
async def test_pending_refresh_respects_newer_credentials_and_deletion(
    monkeypatch, action
):
    service = auth_service(
        NS(
            request=AsyncMock(
                return_value=HTTPResult(
                    200,
                    {
                        "access_token": _fake_access_token(),
                        "refresh_token": "rotated",
                    },
                )
            )
        )
    )
    owner = await User.create(id=111)
    account = await Account.create(
        puuid="pending",
        user=owner,
        username="Synthetic#TEST",
        auth_blob=service.vault.encrypt(
            {"rso": _fake_access_token(-1), "refresh_token": "old"}
        ),
    )
    original = UpdateQuery._execute
    failed = False

    async def interrupted_save(query):
        nonlocal failed
        if query.model is Account and not failed:
            failed = True
            raise DBConnectionError("Synthetic interrupted save")
        return await original(query)

    monkeypatch.setattr(UpdateQuery, "_execute", interrupted_save)
    with pytest.raises(DBConnectionError):
        await service.auth_headers(account)
    assert service._pending_refresh
    if action == "relogin":
        await Account.filter(puuid=account.puuid).update(
            auth_version=1,
            auth_blob=service.vault.encrypt(
                {"rso": _fake_access_token(), "ent": "latest"}
            ),
        )
        assert (await service.auth_headers(account))[
            "X-Riot-Entitlements-JWT"
        ] == "latest"
    else:
        if action == "logout":
            await service.clear_credentials(account)
        else:
            async with service.cancel_logins(owner.id):
                await delete_user_data(owner.id)
        with pytest.raises(AuthenticationRequired):
            await service.auth_headers(account)
    assert not service._pending_refresh
    service.http.request.assert_awaited_once()


@pytest.mark.usefixtures("database")
@pytest.mark.parametrize("operation", ["ensure", "refresh", "auth_headers"])
async def test_unreadable_credentials_are_recoverable_and_preserved(operation):
    user = await User.create(id=108)
    account = await Account.create(
        puuid="unreadable",
        user=user,
        username="Synthetic#TEST",
        auth_blob="invalid-ciphertext",
    )
    auth = auth_service()
    with pytest.raises(HTTPFailure, match="credentials"):
        await getattr(auth, operation)(account)
    saved = await Account.get(puuid=account.puuid)
    assert saved.auth_blob == "invalid-ciphertext" and saved.auth_version == 0


@pytest.mark.usefixtures("database")
async def test_login_can_reauthenticate_an_account_at_capacity():
    user = await User.create(id=103)
    await Account.create(
        puuid="synthetic-account", user=user, username="Example#NA", auth_blob=None
    )
    auth = SimpleNamespace(login_url=lambda _: "https://example.com/login")
    bot = SimpleNamespace(
        config=SimpleNamespace(max_accounts_per_user=1),
        auth=auth,
        translator=BotFraggTranslator(),
        register_component=lambda *args: None,
    )
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=103),
        client=bot,
        locale=discord.Locale.american_english,
        response=SimpleNamespace(defer=AsyncMock(), is_done=lambda: True),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    await LoginCog.login.callback(LoginCog(bot), interaction)
    assert "view" in interaction.followup.send.call_args.kwargs


@pytest.mark.usefixtures("database")
async def test_delete_during_refresh_becomes_login_required():
    user = await User.create(id=104)
    vault = AuthVault(Fernet.generate_key().decode())
    account = await Account.create(
        puuid="synthetic-race",
        user=user,
        username="Example#NA",
        auth_blob=vault.encrypt(
            {"rso": "x.eyJleHAiOjB9.x", "refresh_token": "synthetic"}
        ),
    )
    started, release = asyncio.Event(), asyncio.Event()

    async def request(*args, **kwargs):
        started.set()
        await release.wait()
        return SimpleNamespace(
            status=200, data={"access_token": "x.eyJleHAiOjQwMDAwMDAwMDB9.x"}
        )

    auth = AuthService(
        SimpleNamespace(token_refresh_buffer_minutes=5, auto_refresh_tokens=True),
        SimpleNamespace(request=request),
        vault,
    )
    task = asyncio.create_task(auth.auth_headers(account))
    await asyncio.wait_for(started.wait(), 1)
    await delete_user_data(user.id)
    release.set()
    with pytest.raises(AuthenticationRequired):
        await task


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        ["malformed"],
        {},
        {"riotClientVersion": None},
        {"riotClientVersion": []},
        {"riotClientVersion": "good", "riotClientBuild": []},
    ],
)
async def test_version_refresh_does_not_poison_auth_headers(payload):
    auth = AuthService(
        NS(),
        NS(request=AsyncMock(return_value=NS(status=200, data={"data": payload}))),
        NS(),
    )
    previous = {"riotClientVersion": "last-good-version"}
    auth._version = previous
    with pytest.raises(HTTPFailure):
        await auth.refresh_version()
    assert auth._version == previous
    assert auth.riot_headers["X-Riot-ClientVersion"] == "last-good-version"


async def test_bad_entitlement_never_becomes_a_persisted_header(database):
    vault = AuthVault(Fernet.generate_key().decode())
    auth = AuthService(
        NS(token_refresh_buffer_minutes=5, auto_refresh_tokens=True),
        NS(
            request=AsyncMock(
                return_value=NS(status=200, data={"entitlements_token": ["malformed"]})
            )
        ),
        vault,
    )
    owner = await User.create(id=101)
    account = await Account.create(
        puuid="synthetic",
        user=owner,
        username="Synthetic",
        auth_blob=vault.encrypt({"rso": token(exp=int(time.time()) + 3600)}),
    )
    with pytest.raises(HTTPFailure):
        await auth.auth_headers(account)
    saved = await Account.get(puuid=account.puuid)
    assert saved.auth_blob == account.auth_blob
    assert saved.auth_version == account.auth_version
    auth.http.request.return_value.data = {"entitlements_token": "recovered"}
    headers = await auth.auth_headers(account)
    assert headers["X-Riot-Entitlements-JWT"] == "recovered"
    assert all(isinstance(value, str) for value in headers.values())


@pytest.mark.parametrize(
    "endpoint, payload",
    [
        ("_user_info", {"acct": ["malformed"]}),
        ("_user_info", {"acct": {"game_name": 5, "tag_line": "NA"}}),
        ("_user_info", {"acct": {"game_name": "Synthetic", "tag_line": []}}),
        ("_region", {"affinities": ["malformed"]}),
        ("_region", {"affinities": {"live": ["na"]}}),
    ],
)
async def test_malformed_login_details_are_recoverable(endpoint, payload):
    auth = AuthService(
        NS(), NS(request=AsyncMock(return_value=NS(status=200, data=payload))), NS()
    )
    try:
        result = await getattr(auth, endpoint)({"rso": "synthetic", "idt": "synthetic"})
    except HTTPFailure:
        return
    assert result is None


@pytest.mark.parametrize("field", ["access_token", "id_token", "refresh_token"])
@pytest.mark.parametrize("value", [[], {}, 5, ""])
async def test_malformed_refresh_preserves_last_credentials(database, field, value):
    vault = AuthVault(Fernet.generate_key().decode())
    request = AsyncMock(
        return_value=NS(
            status=200,
            data={"access_token": token(exp=int(time.time()) + 3600), field: value},
        )
    )
    service = AuthService(
        NS(token_refresh_buffer_minutes=5, auto_refresh_tokens=True),
        NS(request=request),
        vault,
    )
    owner = await User.create(id=101)
    old = {
        "rso": token(exp=int(time.time()) - 1),
        "refresh_token": "last-good",
        "ent": "last-good-entitlement",
    }
    account = await Account.create(
        puuid="synthetic",
        user=owner,
        username="Synthetic",
        auth_blob=vault.encrypt(old),
    )
    with pytest.raises(HTTPFailure):
        await service.auth_headers(account)
    saved = await Account.get(puuid=account.puuid)
    assert saved.auth_blob == account.auth_blob
    assert saved.auth_version == account.auth_version


@pytest.mark.parametrize("value", [None, [], {}, 5])
def test_jwt_decoder_rejects_nonstring_tokens(value):
    assert decode_jwt(value) == {}


@pytest.mark.parametrize("error", ["invalid_grant", "bad_claims"])
@pytest.mark.parametrize("login_phase", ["none", "request", "clear"])
async def test_refresh_rejection_checks_the_current_login(database, error, login_phase):
    vault = AuthVault(Fernet.generate_key().decode())
    user = await User.create(id=101)
    account = await Account.create(
        puuid="synthetic",
        user=user,
        username="Synthetic",
        auth_blob=vault.encrypt({"rso": refresh_jwt(exp=1), "refresh_token": "old"}),
    )
    newer = {
        "rso": refresh_jwt(exp=clock.time() + 3600, kind="new-login"),
        "ent": "new-entitlement",
        "refresh_token": "new-refresh",
    }

    async def publish_login():
        await Account.filter(puuid=account.puuid).update(
            auth_blob=vault.encrypt(newer), auth_version=1
        )

    async def request(*args, **kwargs):
        if login_phase == "request":
            await publish_login()
        return NS(status=400, data={"error": error})

    service = AuthService(
        NS(auto_refresh_tokens=True, token_refresh_buffer_minutes=5),
        NS(request=request),
        vault,
    )
    if login_phase == "clear":
        original_clear = service._clear_credentials_locked

        async def clear(current):
            await publish_login()
            await original_clear(current)

        service._clear_credentials_locked = clear
    if login_phase == "none":
        with pytest.raises(AuthenticationRequired):
            await service.auth_headers(account)
        assert (await Account.get(puuid=account.puuid)).auth_blob is None
    else:
        headers = await service.auth_headers(account)
        saved = await Account.get(puuid=account.puuid)
        assert vault.decrypt(saved.auth_blob) == newer
        assert headers["Authorization"] == f"Bearer {newer['rso']}"
        assert headers["X-Riot-Entitlements-JWT"] == newer["ent"]


async def test_refresh_does_not_attach_old_tokens_to_a_newer_version(
    database, monkeypatch
):
    vault = AuthVault(Fernet.generate_key().decode())
    user = await User.create(id=101)
    account = await Account.create(
        puuid="synthetic",
        user=user,
        username="Old",
        auth_blob=vault.encrypt(
            {"rso": refresh_jwt(exp=1), "refresh_token": "old-refresh"}
        ),
    )
    login_auth = {
        "rso": refresh_jwt(exp=clock.time() + 3600, kind="new-login"),
        "ent": "new-login-ent",
        "refresh_token": "new-login-refresh",
    }
    request = AsyncMock(
        return_value=NS(
            status=200,
            data={
                "access_token": refresh_jwt(
                    exp=clock.time() + 3600, kind="old-refresh"
                ),
                "refresh_token": "rotated-old-refresh",
            },
        )
    )
    service = AuthService(
        NS(token_refresh_buffer_minutes=10, auto_refresh_tokens=True),
        NS(request=request),
        vault,
    )
    service._entitlement = AsyncMock(return_value="old-refresh-ent")
    original_row = Account.persisted_row
    calls = 0

    def row(self):
        nonlocal calls
        calls += 1
        query = original_row(self)
        if calls != 2:
            return query

        async def read_after_login():
            await Account.filter(puuid=self.puuid).update(
                auth_blob=vault.encrypt(login_auth), auth_version=2
            )
            return await query.get_or_none()

        return NS(get_or_none=read_after_login)

    monkeypatch.setattr(Account, "persisted_row", row)
    result = await service._refresh_locked(account, force=True)
    saved = await Account.get(puuid=account.puuid)
    assert result.success and saved.auth_version == 2
    assert vault.decrypt(saved.auth_blob) == login_auth
    service._entitlement.assert_not_awaited()


async def test_login_row_lock_preserves_credentials_against_concurrent_refresh(
    monkeypatch,
    postgres_url,
):
    await Tortoise.init(
        db_url=postgres_url,
        modules={"models": ["src.models.entities"]},
    )
    await Tortoise.generate_schemas(safe=True)
    login_task = refresh_task = None
    release_login = asyncio.Event()
    try:
        vault = AuthVault(Fernet.generate_key().decode())
        user = await User.create(id=901)
        account = await Account.create(
            puuid="synthetic-concurrent",
            user=user,
            username="Old",
            auth_blob=vault.encrypt(
                {"rso": refresh_jwt(exp=1), "refresh_token": "old-refresh"}
            ),
        )
        login_token = refresh_jwt(
            sub=account.puuid, exp=clock.time() + 3600, kind="login"
        )
        refresh_token = refresh_jwt(
            sub=account.puuid, exp=clock.time() + 3600, kind="refresh"
        )
        service = AuthService(
            NS(
                max_accounts_per_user=5,
                auto_refresh_tokens=True,
                token_refresh_buffer_minutes=10,
            ),
            NS(),
            vault,
        )
        service.login_url(user.id)
        nonce = service._pending_nonces[user.id][0]
        login_ready, refresh_requested, refresh_entitlement = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )

        async def request(method, url, **kwargs):
            if "grant_type=authorization_code" in kwargs["data"]:
                return NS(
                    status=200,
                    data={
                        "access_token": login_token,
                        "refresh_token": "login-refresh",
                        "id_token": refresh_jwt(nonce=nonce),
                    },
                )
            refresh_requested.set()
            return NS(
                status=200,
                data={
                    "access_token": refresh_token,
                    "refresh_token": "rotated-old-refresh",
                },
            )

        async def entitlement(auth):
            if auth["rso"] == refresh_token:
                refresh_entitlement.set()
                return "old-refresh-ent"
            return "login-ent"

        service.http = NS(request=request)
        service._user_info = AsyncMock(
            return_value={"game_name": "NewLogin", "tag_line": "AUDIT"}
        )
        service._region = AsyncMock(return_value="eu")
        service._entitlement = entitlement
        original_save = Account.save

        async def save(self, *args, **kwargs):
            if vault.decrypt(self.auth_blob).get("rso") == login_token:
                login_ready.set()
                await release_login.wait()
            return await original_save(self, *args, **kwargs)

        monkeypatch.setattr(Account, "save", save)
        login_task = asyncio.create_task(
            service.redeem_callback(user.id, "http://localhost/redirect?code=synthetic")
        )
        await asyncio.wait_for(login_ready.wait(), 5)
        refresh_task = asyncio.create_task(service.refresh(account, force=True))
        await asyncio.wait_for(refresh_requested.wait(), 5)
        async with asyncio.timeout(5):
            while not refresh_entitlement.is_set():
                blocked = await connections.get("default").execute_query_dict(
                    "SELECT pid FROM pg_stat_activity WHERE pid <> pg_backend_pid() "
                    "AND datname = current_database() AND wait_event_type = 'Lock'"
                )
                if blocked:
                    break
                await asyncio.sleep(0.01)
        assert not refresh_entitlement.is_set(), (
            "Refresh bypassed the login's Account row lock"
        )
        release_login.set()
        login, refresh = await asyncio.wait_for(
            asyncio.gather(login_task, refresh_task), 5
        )
        final = await Account.get(puuid=account.puuid)
        assert login.success and refresh.success
        assert final.auth_version == 1
        assert vault.decrypt(final.auth_blob)["rso"] == login_token
        assert vault.decrypt(final.auth_blob)["ent"] == "login-ent"
    finally:
        release_login.set()
        for task in (login_task, refresh_task):
            if task is not None:
                task.cancel()
        await asyncio.gather(
            *(task for task in (login_task, refresh_task) if task is not None),
            return_exceptions=True,
        )
        await User.filter(id=901).delete()
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_stale_account_cannot_read_new_owners_credentials(database):
    auth = auth_service()
    first = await User.create(id=101)
    second = await User.create(id=202)
    old = await Account.create(puuid="synthetic", user=first, username="old")
    await delete_user_data(first.id)
    await Account.create(
        puuid=old.puuid,
        user=second,
        username="new",
        auth_blob=auth.vault.encrypt(
            {
                "rso": lifetime_jwt(exp=int(time.time()) + 3600),
                "ent": "new-owner-entitlement",
            }
        ),
    )
    with pytest.raises(AuthenticationRequired):
        await auth.auth_headers(old)
    assert not (await auth.ensure(old)).success
    assert not (await auth.refresh(old, force=True)).success


@pytest.mark.asyncio
async def test_stale_logout_cannot_clear_new_owners_credentials(database):
    auth = auth_service()
    first = await User.create(id=101)
    second = await User.create(id=202)
    old = await Account.create(puuid="synthetic", user=first, username="old")
    await delete_user_data(first.id)
    replacement = await Account.create(
        puuid=old.puuid,
        user=second,
        username="new",
        auth_blob=auth.vault.encrypt({"rso": "new-owner-token"}),
    )
    await auth.clear_credentials(old)
    fresh = await Account.get(puuid=replacement.puuid)
    assert fresh.auth_blob is not None, (
        "Stale owner cleared replacement owner credentials"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement_owner", [101, 202])
async def test_refresh_cas_cannot_overwrite_recreated_account(
    database, replacement_owner
):
    auth = auth_service()
    first = await User.create(id=101)
    old = await Account.create(
        puuid="synthetic",
        user=first,
        username="old",
        auth_blob=auth.vault.encrypt(
            {"rso": lifetime_jwt(exp=1), "refresh_token": "old-refresh"}
        ),
    )
    replacement_blob = auth.vault.encrypt(
        {"rso": "replacement-token", "ent": "replacement-ent"}
    )

    async def request(method, url, **kwargs):
        if url.endswith("/token"):
            await delete_user_data(first.id)
            second = await User.create(id=replacement_owner)
            await Account.create(
                puuid=old.puuid, user=second, username="new", auth_blob=replacement_blob
            )
            return NS(
                status=200,
                data={
                    "access_token": lifetime_jwt(exp=int(time.time()) + 3600),
                    "refresh_token": "old-rotated",
                },
            )
        return NS(status=200, data={"entitlements_token": "old-entitlement"})

    auth.http = NS(request=request)
    assert not (await auth.refresh(old, force=True)).success
    replacement = await Account.get(puuid=old.puuid)
    assert replacement.auth_blob == replacement_blob, (
        "auth_version reset lets a stale refresh replace the new owner auth"
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
    import base64
    import json

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
