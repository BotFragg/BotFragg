"""Riot OAuth callbacks, encrypted credentials, and refreshable auth headers."""

from __future__ import annotations

import asyncio
import base64
import json
import secrets
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, NotRequired, TypedDict
from urllib.parse import parse_qs, urlencode, urlparse
from weakref import WeakValueDictionary

from tortoise.exceptions import IntegrityError
from tortoise.expressions import F
from tortoise.transactions import in_transaction

from ..config import Settings
from ..models import Account, User
from .crypto import AuthVault
from .http import HTTPClient, HTTPFailure

CLIENT_ID = "riot-client"
REDIRECT_URI = "http://localhost/redirect"


class TokenData(TypedDict):
    """Riot token fields after trust-boundary validation."""

    access_token: str
    id_token: str | None
    refresh_token: str | None


class UserInfo(TypedDict):
    """Validated Riot identity fields used to display the linked account name."""

    game_name: str
    tag_line: str


class LoginCredentials(TypedDict):
    """Credential payload constructed from a validated login response."""

    rso: str
    idt: str | None
    refresh_token: str | None
    refresh_token_obtained: int
    ent: NotRequired[str]


@dataclass(slots=True)
class AuthResult:
    """Represent an authentication outcome and localized failure details."""

    success: bool
    account: Account | None = None
    error_key: str | None = None
    error_arguments: dict[str, Any] = field(default_factory=dict)


class AuthService:
    """Manage Riot login, token refresh, entitlement repair, and account linking."""

    def __init__(self, config: Settings, http: HTTPClient, vault: AuthVault) -> None:
        """Bind validated settings, the shared HTTP client, and token vault."""
        self.config = config
        self.http = http
        self.vault = vault
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
        self._login_locks: WeakValueDictionary[int, asyncio.Lock] = (
            WeakValueDictionary()
        )
        self._version: dict[str, Any] = {}
        # shortcut: pending saves survive only this process; restart recovery needs durable storage.
        self._pending_refresh: dict[tuple[str, int, datetime], tuple[int, str]] = {}
        self._pending_nonces: dict[int, tuple[str, float]] = {}
        self._login_cancellations: WeakValueDictionary[int, asyncio.Event] = (
            WeakValueDictionary()
        )

    def _credentials(self, account: Account) -> dict[str, Any]:
        """Normalize unreadable credentials without overwriting the stored blob."""
        try:
            return self.vault.decrypt(account.auth_blob)
        except ValueError as exc:
            raise HTTPFailure("Stored Riot credentials cannot be read") from exc

    @asynccontextmanager
    async def cancel_logins(self, discord_id: int) -> AsyncIterator[None]:
        """Invalidate login attempts and serialize deletion with their database commits."""
        async with self._login_locks.setdefault(discord_id, asyncio.Lock()):
            cancelled = self._login_cancellations.setdefault(
                discord_id, asyncio.Event()
            )
            cancelled.set()
            self._pending_nonces.pop(discord_id, None)
            try:
                yield
                for key in list(self._pending_refresh):
                    if key[1] == discord_id:
                        self._pending_refresh.pop(key, None)
            finally:
                self._pending_nonces.pop(discord_id, None)
                self._login_cancellations.pop(discord_id, None)

    async def refresh_version(self) -> None:
        """Fetch Riot's current client version for authenticated request headers."""
        self.prune_expired_nonces()
        result = await self.http.request("GET", "https://valorant-api.com/v1/version")
        version = result.data.get("data") if isinstance(result.data, dict) else None
        if (
            result.status != 200
            or not isinstance(version, dict)
            or not isinstance(version.get("riotClientVersion"), str)
            or not version["riotClientVersion"]
            or (
                version.get("riotClientBuild") is not None
                and not isinstance(version["riotClientBuild"], str)
            )
        ):
            raise HTTPFailure("Invalid VALORANT client version response")
        self._version = version

    @property
    def riot_headers(self) -> dict[str, str]:
        """Return the platform and current client-version headers expected by Riot."""
        version = self._version.get(
            "riotClientVersion", "release-10.00-shipping-0-0000000"
        )
        return {
            "X-Riot-ClientPlatform": "ewogICAgInBsYXRmb3JtVHlwZSI6ICJQQyIsCiAgICAicGxhdGZvcm1PUyI6ICJXaW5kb3dzIiwKICAgICJwbGF0Zm9ybU9TVmVyc2lvbiI6ICIxMC4wLjE5MDQyLjEuMjU2LjY0Yml0IiwKICAgICJwbGF0Zm9ybUNoaXBzZXQiOiAiVW5rbm93biIKfQ==",
            "X-Riot-ClientVersion": version,
        }

    def login_url(self, discord_id: int) -> str:
        """Create a Riot authorization URL and retain a short-lived per-user nonce."""
        self.prune_expired_nonces()
        nonce = secrets.token_urlsafe(24)
        self._pending_nonces[discord_id] = (nonce, time.monotonic() + 600)
        return "https://auth.riotgames.com/authorize?" + urlencode(
            {
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "response_type": "code",
                "scope": "openid link ban lol_region account offline_access",
                "nonce": nonce,
            }
        )

    async def redeem_callback(self, discord_id: int, callback_url: str) -> AuthResult:
        """Exchange a callback code, verify its nonce, and securely link the account.

        The callback nonce is single-use and expires after ten minutes. A Riot account
        already owned by another Discord user, or a user at the account limit, is
        rejected without replacing the existing owner.
        """
        try:
            code = parse_qs(urlparse(callback_url.strip()).query).get("code", [None])[0]
        except ValueError:
            return AuthResult(False, error_key="login-code-missing")
        if not code:
            return AuthResult(
                False,
                error_key="login-code-missing",
            )
        pending = self._pending_nonces.pop(discord_id, None)
        if not pending or pending[1] < time.monotonic():
            return AuthResult(
                False,
                error_key="login-attempt-expired",
            )
        cancelled = self._login_cancellations.setdefault(discord_id, asyncio.Event())
        try:
            response = await self.http.request(
                "POST",
                "https://auth.riotgames.com/token",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": self._user_agent(),
                },
                data=urlencode(
                    {
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": REDIRECT_URI,
                        "client_id": CLIENT_ID,
                    }
                ),
            )
        except HTTPFailure:
            return AuthResult(
                False,
                error_key="error-riot-auth-temporarily-unavailable",
            )
        if response.status != 200 or not isinstance(response.data, dict):
            return AuthResult(
                False,
                error_key="login-code-rejected",
            )
        try:
            token_data = _token_data(response.data)
        except HTTPFailure:
            return AuthResult(
                False, error_key="error-riot-auth-temporarily-unavailable"
            )
        claims = decode_jwt(token_data.get("id_token"))
        if claims.get("nonce") != pending[0]:
            return AuthResult(
                False,
                error_key="login-nonce-mismatch",
            )
        auth: LoginCredentials = {
            "rso": token_data["access_token"],
            "idt": token_data.get("id_token"),
            "refresh_token": token_data.get("refresh_token"),
            "refresh_token_obtained": int(time.time() * 1000),
        }
        puuid = decode_jwt(auth["rso"]).get("sub")
        if not isinstance(puuid, str) or not puuid:
            return AuthResult(
                False,
                error_key="login-token-no-account",
            )
        try:
            user_info, entitlement, region = await asyncio.gather(
                self._user_info(auth), self._entitlement(auth), self._region(auth)
            )
        except HTTPFailure:
            return AuthResult(
                False,
                error_key="login-account-details-unavailable",
            )
        if not user_info or not entitlement or not region:
            return AuthResult(
                False,
                error_key="login-account-details-missing",
            )
        auth["ent"] = entitlement
        username = f"{user_info['game_name']}#{user_info['tag_line']}"
        try:
            async with (
                self._login_locks.setdefault(discord_id, asyncio.Lock()),
                in_transaction(),
            ):
                if cancelled.is_set():
                    return AuthResult(False, error_key="login-attempt-expired")
                user, _ = await User.get_or_create(id=discord_id)
                user = await User.filter(id=discord_id).select_for_update().get()
                account = (
                    await Account.filter(puuid=puuid).select_for_update().get_or_none()
                )
                if account and account.user_id != discord_id:
                    return AuthResult(
                        False,
                        error_key="login-account-already-linked",
                    )
                if not account:
                    count = await Account.filter(user_id=discord_id).count()
                    if count >= self.config.max_accounts_per_user:
                        return AuthResult(
                            False,
                            error_key="login-account-limit",
                            error_arguments={
                                "max_accounts": self.config.max_accounts_per_user
                            },
                        )
                    account = await Account.create(
                        puuid=puuid,
                        user=user,
                        username=username,
                        region=region,
                        auth_blob=self.vault.encrypt(auth),
                    )
                else:
                    account.username = username
                    account.region = region
                    account.auth_blob = self.vault.encrypt(auth)
                    account.auth_version += 1
                    await account.save()
                user.current_account_id = puuid
                await user.save(update_fields=["current_account_id", "updated_at"])
        except IntegrityError:
            account = await Account.get_or_none(puuid=puuid)
            if account and account.user_id != discord_id:
                return AuthResult(
                    False,
                    error_key="login-account-already-linked",
                )
            raise
        return AuthResult(True, account=account)

    async def ensure(self, account: Account, *, force: bool = False) -> AuthResult:
        """Serialize credential checks for an account and return its usable auth state."""
        async with self._locks.setdefault(account.puuid, asyncio.Lock()):
            fresh = await account.persisted_row().get_or_none()
            if not fresh:
                self._pending_refresh.pop(
                    (account.puuid, account.user_id, account.created_at), None
                )
                return AuthResult(False, account=account)
            return await self._ensure_locked(fresh, force=force)

    async def _ensure_locked(
        self, account: Account, *, force: bool = False
    ) -> AuthResult:
        """Check token lifetime and repair or refresh credentials while holding its lock."""
        current = await self._save_pending_refresh(account)
        if current is None:
            return AuthResult(False)
        account = current
        auth = self._credentials(account)
        if not isinstance(auth.get("rso"), str) or not auth["rso"]:
            return AuthResult(False, account=account)
        remaining = token_expiry(auth["rso"]) - time.time()
        if not force and remaining > self.config.token_refresh_buffer_minutes * 60:
            if isinstance(auth.get("ent"), str) and auth["ent"]:
                return AuthResult(True, account=account)
            return await self._repair_entitlement(
                account, auth, refresh_on_missing=True
            )
        if not self.config.auto_refresh_tokens:
            return AuthResult(
                remaining > 0
                and isinstance(auth.get("ent"), str)
                and bool(auth["ent"]),
                account=account,
            )
        return await self._refresh_locked(account, force=force)

    async def refresh(self, account: Account, *, force: bool = False) -> AuthResult:
        """Refresh one account's Riot tokens under its per-account lock."""
        async with self._locks.setdefault(account.puuid, asyncio.Lock()):
            fresh = await account.persisted_row().get_or_none()
            if not fresh:
                self._pending_refresh.pop(
                    (account.puuid, account.user_id, account.created_at), None
                )
                return AuthResult(False, account=account)
            return await self._refresh_locked(fresh, force=force)

    async def _refresh_locked(
        self, account: Account, *, force: bool = False
    ) -> AuthResult:
        """Refresh tokens with version-checked persistence to protect concurrent updates."""
        current = await self._save_pending_refresh(account)
        if current is None:
            return AuthResult(False)
        account = current
        auth = self._credentials(account)
        if (
            not force
            and token_expiry(auth.get("rso")) - time.time()
            > self.config.token_refresh_buffer_minutes * 60
            and isinstance(auth.get("ent"), str)
            and auth["ent"]
        ):
            return AuthResult(True, account=account)
        refresh_token = auth.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            await self._clear_credentials_locked(account)
            return AuthResult(False, account=account)
        expected_version = account.auth_version
        response = await self.http.request(
            "POST",
            "https://auth.riotgames.com/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": self._user_agent(),
            },
            data=urlencode(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": CLIENT_ID,
                }
            ),
        )
        data = response.data if isinstance(response.data, dict) else {}
        if response.status in {408, 425} or response.status >= 500:
            raise HTTPFailure(
                f"Riot token refresh failed with status {response.status}"
            )
        if (
            response.status in {400, 401}
            and isinstance(data.get("error"), str)
            and data.get("error")
            in {
                "invalid_grant",
                "bad_claims",
            }
        ):
            current = await account.persisted_row().get_or_none()
            if current is None:
                return AuthResult(False)
            if current.auth_version == expected_version:
                await self._clear_credentials_locked(current)
                current = await account.persisted_row().get_or_none()
            return await self._ensure_locked(current) if current else AuthResult(False)
        if response.status != 200:
            raise HTTPFailure(
                f"Riot token refresh failed with status {response.status}"
            )
        token_data = _token_data(data)
        new_auth = dict(auth)
        new_auth["rso"] = token_data["access_token"]
        if token_data["id_token"]:
            new_auth["idt"] = token_data["id_token"]
        if token_data["refresh_token"] and token_data["refresh_token"] != refresh_token:
            new_auth["refresh_token"] = token_data["refresh_token"]
            new_auth["refresh_token_obtained"] = int(time.time() * 1000)
        new_auth.pop("ent", None)
        encrypted = self.vault.encrypt(new_auth)
        self._pending_refresh[(account.puuid, account.user_id, account.created_at)] = (
            expected_version,
            encrypted,
        )
        saved = await self._save_pending_refresh(account)
        if saved is None:
            return AuthResult(False)
        if saved.auth_version != expected_version + 1 or saved.auth_blob != encrypted:
            return await self._ensure_locked(saved)
        return await self._repair_entitlement(saved, new_auth)

    async def _save_pending_refresh(self, account: Account) -> Account | None:
        """Persist a returned token without repeating its exchange after a DB outage."""
        key = (account.puuid, account.user_id, account.created_at)
        pending = self._pending_refresh.get(key)
        if pending is None:
            return account
        expected_version, encrypted = pending
        if account.auth_version != expected_version:
            self._pending_refresh.pop(key, None)
            return account
        await (
            account.persisted_row()
            .filter(auth_version=expected_version)
            .update(auth_blob=encrypted, auth_version=F("auth_version") + 1)
        )
        current = await account.persisted_row().get_or_none()
        self._pending_refresh.pop(key, None)
        return current

    async def clear_credentials(self, account: Account) -> None:
        """Remove the selected account's Riot tokens while coordinating with refreshes."""
        async with self._locks.setdefault(account.puuid, asyncio.Lock()):
            current = await account.persisted_row().get_or_none()
            if current:
                await self._clear_credentials_locked(current)
            self._pending_refresh.pop(
                (account.puuid, account.user_id, account.created_at), None
            )

    async def _clear_credentials_locked(self, account: Account) -> None:
        """Clear credentials only if the stored auth version still matches the caller."""
        await (
            account.persisted_row()
            .filter(auth_version=account.auth_version)
            .update(auth_blob=None, auth_version=F("auth_version") + 1)
        )

    async def auth_headers(self, account: Account) -> dict[str, str]:
        """Return fresh Riot authorization headers or raise when login is required."""
        async with self._locks.setdefault(account.puuid, asyncio.Lock()):
            current = await account.persisted_row().get_or_none()
            if not current:
                self._pending_refresh.pop(
                    (account.puuid, account.user_id, account.created_at), None
                )
                raise AuthenticationRequired("Riot login is required")
            result = await self._ensure_locked(current)
            if not result.success or not result.account:
                raise AuthenticationRequired("Riot login is required")
            current = result.account
            auth = self._credentials(current)
            if any(
                not isinstance(auth.get(key), str) or not auth[key]
                for key in ("rso", "ent")
            ):
                raise AuthenticationRequired("Riot login is required")
            return {
                "Authorization": f"Bearer {auth['rso']}",
                "X-Riot-Entitlements-JWT": auth["ent"],
                **self.riot_headers,
            }

    async def _repair_entitlement(
        self,
        account: Account,
        auth: Mapping[str, Any],
        *,
        refresh_on_missing: bool = False,
    ) -> AuthResult:
        """Fetch and persist an entitlement token, optionally refreshing on absence."""
        entitlement = await self._entitlement(auth)
        if not entitlement:
            if refresh_on_missing:
                return await self._refresh_locked(account, force=True)
            return AuthResult(False, account=account)
        new_auth = dict(auth)
        new_auth["ent"] = entitlement
        changed = (
            await account.persisted_row()
            .filter(auth_version=account.auth_version)
            .update(
                auth_blob=self.vault.encrypt(new_auth),
                auth_version=F("auth_version") + 1,
            )
        )
        current = await account.persisted_row().get_or_none()
        if current is None:
            return AuthResult(False)
        if changed:
            return AuthResult(True, account=current)
        current_auth = self._credentials(current)
        usable = (
            all(
                isinstance(current_auth.get(key), str) and current_auth[key]
                for key in ("rso", "ent")
            )
            and token_expiry(current_auth.get("rso")) - time.time()
            > self.config.token_refresh_buffer_minutes * 60
        )
        return AuthResult(usable, account=current)

    def prune_expired_nonces(self) -> None:
        """Release abandoned login attempts after their ten-minute lifetime."""
        now = time.monotonic()
        self._pending_nonces = {
            key: pending
            for key, pending in self._pending_nonces.items()
            if pending[1] > now
        }

    async def _user_info(self, auth: Mapping[str, Any]) -> UserInfo | None:
        """Fetch the Riot game name and tag line associated with an access token."""
        response = await self.http.request(
            "GET",
            "https://auth.riotgames.com/userinfo",
            headers={"Authorization": f"Bearer {auth['rso']}"},
        )
        if response.status != 200 or not isinstance(response.data, dict):
            return None
        account = response.data.get("acct")
        if not isinstance(account, dict) or any(
            not isinstance(account.get(key), str) or not account[key]
            for key in ("game_name", "tag_line")
        ):
            raise HTTPFailure("Invalid Riot account details")
        return {"game_name": account["game_name"], "tag_line": account["tag_line"]}

    async def _entitlement(self, auth: Mapping[str, Any]) -> str | None:
        """Request an entitlement token and surface transient Riot failures."""
        response = await self.http.request(
            "POST",
            "https://entitlements.auth.riotgames.com/api/token/v1",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {auth['rso']}",
            },
        )
        if response.status in {408, 425} or response.status >= 500:
            raise HTTPFailure(
                f"Riot entitlement request failed with status {response.status}"
            )
        if response.status != 200:
            return None
        entitlement = (
            response.data.get("entitlements_token")
            if isinstance(response.data, dict)
            else None
        )
        if not isinstance(entitlement, str) or not entitlement:
            raise HTTPFailure("Invalid Riot entitlement response")
        return entitlement

    async def _region(self, auth: Mapping[str, Any]) -> str | None:
        """Resolve the VALORANT shard affinity associated with an ID token."""
        response = await self.http.request(
            "PUT",
            "https://riot-geo.pas.si.riotgames.com/pas/v1/product/valorant",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {auth['rso']}",
            },
            json={"id_token": auth.get("idt")},
        )
        if response.status != 200 or not isinstance(response.data, dict):
            return None
        affinities = response.data.get("affinities")
        if (
            not isinstance(affinities, dict)
            or not isinstance(affinities.get("live"), str)
            or not affinities["live"]
        ):
            raise HTTPFailure("Invalid Riot region response")
        return affinities["live"]

    def _user_agent(self) -> str:
        """Build the Riot authentication user agent from the latest client build."""
        build = (
            self._version.get("riotClientBuild")
            or self._version.get("riotClientVersion")
            or "release-10.00-shipping-0-0000000"
        )
        return f"RiotClient/{build} rso-auth (Windows;10;;Professional, x64)"


def _token_data(data: dict[str, Any]) -> TokenData:
    """Validate token response fields before using or persisting credentials."""
    for key in ("access_token", "id_token", "refresh_token"):
        value = data.get(key)
        if key != "access_token" and value is None:
            continue
        if not isinstance(value, str) or not value:
            raise HTTPFailure(f"Invalid Riot {key}")
    return {
        "access_token": data["access_token"],
        "id_token": data.get("id_token"),
        "refresh_token": data.get("refresh_token"),
    }


def decode_jwt(token: str | None) -> dict[str, Any]:
    """Decode a JWT payload for claim lookup without performing signature validation."""
    if not isinstance(token, str) or token.count(".") < 1:
        return {}
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        value = json.loads(base64.urlsafe_b64decode(payload))
        return value if isinstance(value, dict) else {}
    except ValueError, json.JSONDecodeError:
        return {}


def token_expiry(token: str | None) -> float:
    """Return the token's Unix expiry time, or zero when it cannot be decoded."""
    try:
        return float(decode_jwt(token).get("exp", 0))
    except TypeError, ValueError:
        return 0


def riot_region(region: str | None) -> str:
    """Map missing and LATAM/Brazil affinities to Riot's North America API host."""
    return "na" if not region or region in {"latam", "br"} else region


class AuthenticationRequired(RuntimeError):
    """Raised when a Riot request cannot proceed without a new user login."""
