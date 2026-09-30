"""Normalize authenticated VALORANT storefront, accessory, and wallet data."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from weakref import WeakValueDictionary

from ..config import Settings
from ..models import Account
from .auth import AuthenticationRequired, AuthService, riot_region
from .catalog import Accessory, CatalogService, Skin
from .http import HTTPClient, HTTPFailure, HTTPResult, RateLimited

VP_UUID = "85ad13f7-3d1b-5128-9eb2-7cd8ee0b5741"
RP_UUID = "e59aa87c-4cbf-517a-5983-6e81511be9b7"
KC_UUID = "85ca954a-41f2-ce94-9b45-8ca3dd39a00d"


@dataclass(slots=True)
class Offer:
    """Represent a skin offer with its standard price and optional discount."""

    skin: Skin
    price: int
    expires: int
    discount_price: int | None = None
    discount_percent: int | None = None


@dataclass(slots=True)
class AccessoryOffer:
    """Represent one accessory and its Kingdom Credit price."""

    item: Accessory
    price: int


@dataclass(slots=True)
class ShopData:
    """Hold daily, accessory, and Night Market offers with their expiry times."""

    offers: list[Offer]
    accessory: list[dict[str, Any]]
    night_market: list[Offer]
    expires: int
    night_market_expires: int | None


class ShopService:
    """Retrieve and normalize Riot storefronts and wallet balances."""

    def __init__(
        self,
        config: Settings,
        http: HTTPClient,
        auth: AuthService,
        catalog: CatalogService,
    ) -> None:
        """Bind dependencies and initialize storefront data and per-account locks."""
        self.config = config
        self.http = http
        self.auth = auth
        self.catalog = catalog
        self._cache: dict[str, ShopData] = {}
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    def _account_lock(self, account_id: str) -> asyncio.Lock:
        """Return the shared in-process lock used for one account's shop requests."""
        lock = self._locks.get(account_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[account_id] = lock
        return lock

    async def clear_cached_storefront(self, account_id: str) -> None:
        """Remove an account's cached storefront after coordinating with active fetches."""
        async with self._account_lock(account_id):
            self._cache.pop(account_id, None)

    async def storefront(self, account: Account, *, use_cache: bool = True) -> ShopData:
        """Return a fresh or unexpired cached storefront for the linked account."""
        async with self._account_lock(account.puuid):
            cached = self._cache.get(account.puuid)
            if cached and cached.expires <= time.time():
                self._cache.pop(account.puuid, None)
                cached = None
            try:
                headers = await self.auth.auth_headers(account)
                if use_cache and self.config.use_shop_cache and cached:
                    return cached
                return await self._fetch_storefront(account, headers)
            except HTTPFailure as exc:
                raise ShopUnavailable(str(exc)) from exc

    async def _fetch_storefront(
        self, account: Account, headers: dict[str, str]
    ) -> ShopData:
        """Fetch, repair claims when possible, normalize offers, and cache the result."""
        response = await self._storefront_request(account, headers)
        raw = response.data if isinstance(response.data, dict) else {}
        if response.status in {400, 401} and raw.get("errorCode") == "BAD_CLAIMS":
            repaired = await self.auth.ensure(account, force=True)
            if not repaired.success:
                raise AuthenticationRequired("Riot rejected the stored credentials")
            account = await Account.get(puuid=account.puuid)
            headers = await self.auth.auth_headers(account)
            response = await self._storefront_request(account, headers)
            raw = response.data if isinstance(response.data, dict) else {}
            if response.status in {400, 401} and raw.get("errorCode") == "BAD_CLAIMS":
                raise AuthenticationRequired("Riot rejected the stored credentials")

        if response.status != 200 or not raw.get("SkinsPanelLayout"):
            if raw.get("errorCode") == "SCHEDULED_DOWNTIME":
                raise Maintenance("VALORANT is undergoing scheduled maintenance")
            raise ShopUnavailable("Riot returned an invalid storefront response")
        panel = raw["SkinsPanelLayout"]
        expires = int(time.time()) + int(
            panel.get("SingleItemOffersRemainingDurationInSeconds", 0)
        )
        offer_ids = panel.get("SingleItemOffers") or []
        prices = self._offer_prices(raw)
        offers = [
            Offer(skin, prices.get(str(offer_id), skin.price or 0), expires)
            for offer_id in offer_ids
            if (skin := self.catalog.get_skin(str(offer_id)))
        ]
        night_raw = (raw.get("BonusStore") or {}).get("BonusStoreOffers") or []
        night_expires = (
            int(time.time())
            + int(raw["BonusStore"].get("BonusStoreRemainingDurationInSeconds", 0))
            if raw.get("BonusStore")
            else None
        )
        night_market: list[Offer] = []
        for entry in night_raw:
            offer = entry.get("Offer") or {}
            skin = self.catalog.get_skin(str(offer.get("OfferID") or ""))
            if skin:
                night_market.append(
                    Offer(
                        skin,
                        int((offer.get("Cost") or {}).get(VP_UUID, 0)),
                        night_expires or expires,
                        int((entry.get("DiscountCosts") or {}).get(VP_UUID, 0)),
                        int(entry.get("DiscountPercent", 0)),
                    )
                )
        data = ShopData(
            offers=offers,
            accessory=(raw.get("AccessoryStore") or {}).get("AccessoryStoreOffers")
            or [],
            night_market=night_market,
            expires=expires,
            night_market_expires=night_expires,
        )
        self.catalog.update_prices(self._raw_offers(raw))
        self._cache[account.puuid] = data
        return data

    async def _storefront_request(
        self, account: Account, headers: dict[str, str]
    ) -> HTTPResult:
        """Request one account's regional storefront and normalize transport failures."""
        try:
            return await self.http.request(
                "POST",
                f"https://pd.{riot_region(account.region)}.a.pvp.net/store/v3/storefront/{account.puuid}",
                headers=headers,
                json={},
            )
        except (HTTPFailure, RateLimited) as exc:
            raise ShopUnavailable(str(exc)) from exc

    async def wallet(self, account: Account) -> dict[str, int]:
        """Return VP, Radianite, and Kingdom Credit balances for an account."""
        try:
            headers = await self.auth.auth_headers(account)
            response = await self.http.request(
                "GET",
                f"https://pd.{riot_region(account.region)}.a.pvp.net/store/v1/wallet/{account.puuid}",
                headers=headers,
            )
        except HTTPFailure as exc:
            raise ShopUnavailable(str(exc)) from exc
        if response.status != 200 or not isinstance(response.data, dict):
            raise ShopUnavailable("Could not fetch the wallet")
        balances = response.data.get("Balances") or {}
        return {
            "vp": int(balances.get(VP_UUID, 0)),
            "rp": int(balances.get(RP_UUID, 0)),
            "kc": int(balances.get(KC_UUID, 0)),
        }

    async def accessory_offers(self, data: ShopData) -> list[AccessoryOffer]:
        """Resolve the storefront's accessory rewards and their Kingdom Credit prices."""
        offers = []
        for entry in data.accessory:
            offer = entry.get("Offer") or {}
            price = int((offer.get("Cost") or {}).get(KC_UUID, 0))
            for reward in offer.get("Rewards") or []:
                item = await self.catalog.accessory(
                    str(reward.get("ItemTypeID") or ""),
                    str(reward.get("ItemID") or ""),
                )
                if item:
                    offers.append(AccessoryOffer(item, price))
        return offers

    @staticmethod
    def _raw_offers(raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract the raw single-item store offers across Riot response shapes."""
        panel = raw.get("SkinsPanelLayout") or {}
        return (
            panel.get("SingleItemStoreOffers") or raw.get("SingleItemStoreOffers") or []
        )

    def _offer_prices(self, raw: dict[str, Any]) -> dict[str, int]:
        """Build a skin-offer-to-VP-price lookup from the storefront payload."""
        prices: dict[str, int] = {}
        for entry in self._raw_offers(raw):
            offer = (
                entry.get("Offer") if isinstance(entry.get("Offer"), dict) else entry
            )
            identifier = str(offer.get("OfferID") or "")
            cost = offer.get("Cost") or {}
            if identifier and cost:
                prices[identifier] = int(
                    cost.get(VP_UUID, next(iter(cost.values()), 0))
                )
        return prices


class ShopUnavailable(RuntimeError):
    """Raised when Riot does not return a usable storefront or wallet."""


class Maintenance(ShopUnavailable):
    """Raised when VALORANT reports scheduled downtime."""
