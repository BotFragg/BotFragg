"""Behavior and regression checks for cache expiry."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from cryptography.fernet import Fernet

from src.services.auth import AuthService
from src.services.catalog import Skin
from src.services.crypto import AuthVault
from src.services.shop import ShopService


def make_shop(raw):
    skin = Skin("skin", "offer", "Example skin", None, None)
    http = SimpleNamespace(
        request=AsyncMock(return_value=SimpleNamespace(status=200, data=raw))
    )
    auth = SimpleNamespace(auth_headers=AsyncMock(return_value={}))
    catalog = SimpleNamespace(get_skin=lambda _: skin, update_prices=lambda _: None)
    return ShopService(SimpleNamespace(use_shop_cache=True), http, auth, catalog)


def test_expired_login_attempts_and_inactive_shops_are_pruned(monkeypatch):
    """Expiration must release state even when the original user never returns."""
    from src.services.shop import ShopData

    clock = [1000]
    monkeypatch.setattr("src.services.auth.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("src.services.shop.time.time", lambda: clock[0])
    auth = AuthService(
        SimpleNamespace(), SimpleNamespace(), AuthVault(Fernet.generate_key().decode())
    )
    auth.login_url(1)
    clock[0] = 1601
    auth.login_url(2)
    assert set(auth._pending_nonces) == {2}
    shop = make_shop({})
    shop._cache["expired"] = ShopData([], [], [], 1600, None)
    shop._cache["active"] = ShopData([], [], [], 2000, None)
    shop.prune_expired()
    assert set(shop._cache) == {"active"}
