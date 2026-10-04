"""Riot OAuth callbacks, encrypted credentials, and refreshable auth headers."""

from __future__ import annotations

import asyncio
import base64
import json
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from tortoise.exceptions import IntegrityError
from tortoise.expressions import F
from tortoise.transactions import in_transaction

from ..config import Settings
from ..models import Account, User
from .crypto import AuthVault
from .http import HTTPClient, HTTPFailure

CLIENT_ID = "riot-client"
REDIRECT_URI = "http://localhost/redirect"


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
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._login_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._version: dict[str, Any] = {}
        self._pending_nonces: dict[int, tuple[str, float]] = {}

    async def refresh_version(self) -> None:
        """Fetch Riot's current client version for authenticated request headers."""
        result = await self.http.request("GET", "https://valorant-api.com/v1/version")
        if result.status == 200 and isinstance(result.data, dict):
            self._version = result.data.get("data") or {}

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
        code = parse_qs(urlparse(callback_url.strip()).query).get("code", [None])[0]
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
        if (
            response.status != 200
            or not isinstance(response.data, dict)
            or not response.data.get("access_token")
        ):
            return AuthResult(
                False,
                error_key="login-code-rejected",
            )
        token_data = response.data
        claims = decode_jwt(token_data.get("id_token"))
        if claims.get("nonce") != pending[0]:
            return AuthResult(
                False,
                error_key="login-nonce-mismatch",
            )
        auth = {
            "rso": token_data["access_token"],
            "idt": token_data.get("id_token"),
            "refresh_token": token_data.get("refresh_token"),
            "refresh_token_obtained": int(time.time() * 1000),
        }
        puuid = str(decode_jwt(auth["rso"]).get("sub") or "")
        if not puuid:
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
            async with self._login_locks[discord_id], in_transaction():
                user, _ = await User.get_or_create(id=discord_id)
                user = await User.filter(id=discord_id).select_for_update().get()
                account = await Account.get_or_none(puuid=puuid)
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
        async with self._locks[account.puuid]:
            fresh = await Account.get_or_none(puuid=account.puuid)
            if not fresh:
                return AuthResult(False, account=account)
            return await self._ensure_locked(fresh, force=force)

    async def _ensure_locked(
        self, account: Account, *, force: bool = False
    ) -> AuthResult:
        """Check token lifetime and repair or refresh credentials while holding its lock."""
        auth = self.vault.decrypt(account.auth_blob)
        if not auth.get("rso"):
            return AuthResult(False, account=account)
        remaining = token_expiry(auth["rso"]) - time.time()
        if not force and remaining > self.config.token_refresh_buffer_minutes * 60:
            if auth.get("ent"):
                return AuthResult(True, account=account)
            return await self._repair_entitlement(
                account, auth, refresh_on_missing=True
            )
        if not self.config.auto_refresh_tokens:
            return AuthResult(remaining > 0 and bool(auth.get("ent")), account=account)
        return await self._refresh_locked(account, force=force)

    async def refresh(self, account: Account, *, force: bool = False) -> AuthResult:
        """Refresh one account's Riot tokens under its per-account lock."""
        async with self._locks[account.puuid]:
            fresh = await Account.get_or_none(puuid=account.puuid)
            if not fresh:
                return AuthResult(False, account=account)
            return await self._refresh_locked(fresh, force=force)

    async def _refresh_locked(
        self, account: Account, *, force: bool = False
    ) -> AuthResult:
        """Refresh tokens with version-checked persistence to protect concurrent updates."""
        auth = self.vault.decrypt(account.auth_blob)
        if (
            not force
            and token_expiry(auth.get("rso")) - time.time()
            > self.config.token_refresh_buffer_minutes * 60
            and auth.get("ent")
        ):
            return AuthResult(True, account=account)
        refresh_token = auth.get("refresh_token")
        if not refresh_token:
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
        if response.status in {400, 401} and data.get("error") in {
            "invalid_grant",
            "bad_claims",
        }:
            current = await Account.get(puuid=account.puuid)
            if current.auth_version == expected_version:
                await self._clear_credentials_locked(current)
                current = await Account.get(puuid=account.puuid)
            return AuthResult(False, account=current)
        if response.status != 200 or not data.get("access_token"):
            return AuthResult(False, account=account)
        new_auth = dict(auth)
        new_auth["rso"] = data["access_token"]
        if data.get("id_token"):
            new_auth["idt"] = data["id_token"]
        if data.get("refresh_token") and data["refresh_token"] != refresh_token:
            new_auth["refresh_token"] = data["refresh_token"]
            new_auth["refresh_token_obtained"] = int(time.time() * 1000)
        new_auth.pop("ent", None)
        changed = await Account.filter(
            puuid=account.puuid, auth_version=expected_version
        ).update(
            auth_blob=self.vault.encrypt(new_auth),
            auth_version=F("auth_version") + 1,
        )
        if not changed:
            current = await Account.get(puuid=account.puuid)
            return await self._ensure_locked(current)
        saved = await Account.get(puuid=account.puuid)
        return await self._repair_entitlement(saved, new_auth)

    async def clear_credentials(self, account: Account) -> None:
        """Remove the selected account's Riot tokens while coordinating with refreshes."""
        async with self._locks[account.puuid]:
            current = await Account.get_or_none(puuid=account.puuid)
            if current:
                await self._clear_credentials_locked(current)

    async def _clear_credentials_locked(self, account: Account) -> None:
        """Clear credentials only if the stored auth version still matches the caller."""
        await Account.filter(
            puuid=account.puuid, auth_version=account.auth_version
        ).update(auth_blob=None, auth_version=F("auth_version") + 1)

    async def auth_headers(self, account: Account) -> dict[str, str]:
        """Return fresh Riot authorization headers or raise when login is required."""
        async with self._locks[account.puuid]:
            current = await Account.get_or_none(puuid=account.puuid)
            if not current:
                raise AuthenticationRequired("Riot login is required")
            result = await self._ensure_locked(current)
            if not result.success or not result.account:
                raise AuthenticationRequired("Riot login is required")
            current = result.account
            auth = self.vault.decrypt(current.auth_blob)
            if not auth.get("rso") or not auth.get("ent"):
                raise AuthenticationRequired("Riot login is required")
            return {
                "Authorization": f"Bearer {auth['rso']}",
                "X-Riot-Entitlements-JWT": auth["ent"],
                **self.riot_headers,
            }

    async def _repair_entitlement(
        self,
        account: Account,
        auth: dict[str, Any],
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
        changed = await Account.filter(
            puuid=account.puuid, auth_version=account.auth_version
        ).update(
            auth_blob=self.vault.encrypt(new_auth), auth_version=F("auth_version") + 1
        )
        current = await Account.get(puuid=account.puuid)
        if changed:
            return AuthResult(True, account=current)
        current_auth = self.vault.decrypt(current.auth_blob)
        usable = (
            bool(current_auth.get("rso") and current_auth.get("ent"))
            and token_expiry(current_auth.get("rso")) - time.time()
            > self.config.token_refresh_buffer_minutes * 60
        )
        return AuthResult(usable, account=current)

    async def _user_info(self, auth: dict[str, Any]) -> dict[str, str] | None:
        """Fetch the Riot game name and tag line associated with an access token."""
        response = await self.http.request(
            "GET",
            "https://auth.riotgames.com/userinfo",
            headers={"Authorization": f"Bearer {auth['rso']}"},
        )
        if response.status != 200 or not isinstance(response.data, dict):
            return None
        account = response.data.get("acct") or {}
        if not account.get("game_name") or not account.get("tag_line"):
            return None
        return account

    async def _entitlement(self, auth: dict[str, Any]) -> str | None:
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
        if response.status != 200 or not isinstance(response.data, dict):
            return None
        return response.data.get("entitlements_token")

    async def _region(self, auth: dict[str, Any]) -> str | None:
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
        return (response.data.get("affinities") or {}).get("live")

    def _user_agent(self) -> str:
        """Build the Riot authentication user agent from the latest client build."""
        build = (
            self._version.get("riotClientBuild")
            or self._version.get("riotClientVersion")
            or "release-10.00-shipping-0-0000000"
        )
        return f"RiotClient/{build} rso-auth (Windows;10;;Professional, x64)"


def decode_jwt(token: str | None) -> dict[str, Any]:
    """Decode a JWT payload for claim lookup without performing signature validation."""
    if not token or token.count(".") < 1:
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
