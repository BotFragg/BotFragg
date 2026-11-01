"""Behaviour checks for the /profile command and its card."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.cogs.valorant import profile as profile_cog
from src.cogs.valorant.profile import ProfileCog, _match_block
from src.services.auth import AuthenticationRequired
from src.services.catalog import (
    PLAYER_CARD_ITEM_TYPE_ID,
    PLAYER_TITLE_ITEM_TYPE_ID,
    Accessory,
)
from src.services.matches import MatchesUnavailable, MatchSummary, PlayerStats
from src.services.profile import LEVEL_XP_TARGET, PlayerProfile, ProfileUnavailable
from tests.helpers import (
    TEST_LOCALE,
    TEST_TRANSLATOR,
    _localized_bot,
    _localized_interaction,
)

ACCOUNT = SimpleNamespace(
    puuid="puuid-1",
    region="eu",
    user=SimpleNamespace(others_can_view_profile=True),
)


class Response:
    """Record the deferral of the interaction response."""

    def __init__(self) -> None:
        """Start with no recorded deferral."""
        self.deferred: bool | None = None

    async def defer(self, *, thinking: bool = False) -> None:
        """Record whether the command deferred with a thinking state."""
        self.deferred = thinking

    @staticmethod
    def is_done() -> bool:
        """Report that the interaction already responded."""
        return True


class Followup:
    """Record follow-up messages."""

    def __init__(self) -> None:
        """Start with no recorded messages."""
        self.sent: list[dict[str, object]] = []

    async def send(self, **kwargs: object) -> None:
        """Record one sent message."""
        self.sent.append(kwargs)


def interaction(*, followup: Followup | None = None) -> SimpleNamespace:
    """Build a fake interaction for the profile command."""
    return _localized_interaction(
        user=SimpleNamespace(id=1),
        response=Response(),
        followup=followup or Followup(),
        locale=TEST_LOCALE,
    )


def profile(**overrides: object) -> PlayerProfile:
    """Build one profile record for the card."""
    values: dict[str, object] = {
        "card_id": "card-1",
        "title_id": None,
        "level": 214,
        "xp": 2500,
        "tier": 19,
        "rr": 47,
        "wins": 29,
        "games": 50,
        "peak_tier": 24,
    }
    values.update(overrides)
    return PlayerProfile(**values)  # type: ignore[arg-type]


def summary(
    *,
    won: bool = True,
    rounds_won: int | None = 13,
    rounds_lost: int | None = 9,
    kills: int = 21,
    deaths: int = 14,
    assists: int = 5,
    headshot_hits: int = 3,
    total_hits: int = 10,
    score: int = 6400,
    rounds: int = 22,
    queue_id: str = "competitive",
    map_id: str = "map-1",
):
    """Build one match summary for the caller."""
    return MatchSummary(
        match_id="m1",
        map_id=map_id,
        queue_id=queue_id,
        players={
            "puuid-1": PlayerStats(
                agent_id="agent-1",
                killed=kills,
                died=deaths,
                assisted=assists,
                headshot_hits=headshot_hits,
                total_hits=total_hits,
                score=score,
                rounds=rounds,
                won=won,
                rounds_won=rounds_won,
                rounds_lost=rounds_lost,
            )
        },
    )


def emoji_service():
    """Build a fake emoji service with predictable strings."""
    return SimpleNamespace(
        rank_emoji=lambda tier: f"<rank{tier}>",
        agent_emoji=lambda agent: "<agent>",
        queue_emoji=lambda queue: f"<queue:{queue}>",
        battlepass_bars=AsyncMock(return_value=("█", "░")),
        ensure_profile_emojis=AsyncMock(),
    )


def build_bot(*, profile_data=None, matches=None, title_text=None, ranked=None):
    """Build a localized bot with fake profile, match, and catalog services."""
    profiles = SimpleNamespace(
        profile=AsyncMock(return_value=profile_data or profile())
    )
    recent = (
        AsyncMock(side_effect=matches)
        if isinstance(matches, Exception)
        else AsyncMock(return_value=[] if matches is None else matches)
    )
    catalog = SimpleNamespace(
        current_act=AsyncMock(return_value=("act-1", {"en-US": "V26 // ACT VI"})),
        ranks=AsyncMock(
            return_value={
                19: {"en-US": "Diamond 2"},
                24: {"en-US": "Immortal 1"},
            }
        ),
        maps=AsyncMock(return_value={"map-1": {"en-US": "Ascent"}}),
        accessory=AsyncMock(
            side_effect=lambda item_type, identifier: (
                Accessory(
                    name="Card",
                    icon="https://example.invalid/card.png",
                    names={"en-US": "Card"},
                    small_icon="https://example.invalid/card-small.png",
                )
                if item_type == PLAYER_CARD_ITEM_TYPE_ID
                else Accessory(
                    name="Title",
                    icon=None,
                    title_texts={"en-US": title_text},
                )
                if item_type == PLAYER_TITLE_ITEM_TYPE_ID and title_text
                else None
            )
        ),
    )
    return _localized_bot(
        profiles=profiles,
        matches=SimpleNamespace(
            recent=recent,
            ranked_changes=AsyncMock(return_value=ranked or {}),
        ),
        catalog=catalog,
        emoji_service=emoji_service(),
    )


async def run(
    monkeypatch, bot, *, viewer=None, followup=None, user=None, settings=None
):
    """Run the profile command with an authenticated account."""
    monkeypatch.setattr(
        profile_cog, "selected_account", AsyncMock(return_value=ACCOUNT)
    )
    monkeypatch.setattr(
        profile_cog,
        "account_viewer",
        AsyncMock(return_value=viewer or (ACCOUNT, False, "KumKaShree#Shree")),
    )
    monkeypatch.setattr(profile_cog, "get_user", AsyncMock(return_value=settings))
    followup = followup or Followup()
    cog = ProfileCog(bot)
    await cog.profile.callback(cog, interaction(followup=followup), user=user)
    return followup


async def test_profile_card_shows_rank_level_and_matches(monkeypatch):
    """The card must render every agreed block from the fetched data."""
    bot = build_bot(matches=[summary(), summary(won=False)])

    followup = await run(monkeypatch, bot)

    card = followup.sent[0]["embed"]
    assert card.title is None
    assert card.description.startswith("**KumKaShree#Shree**\n\n<rank19>")
    assert "<rank19> **Diamond 2** · 47 RR · 58% WR" in card.description
    assert "-# Peak <rank24> Immortal 1" in card.description
    assert f"Level 214 · 2,500 / {LEVEL_XP_TARGET:,} XP" in card.description
    assert "█████░░░░░" in card.description
    field = card.fields[0]
    assert field.name == TEST_TRANSLATOR.text(TEST_LOCALE, "profile-last-matches")
    assert "🟢 <queue:competitive> Competitive · **Ascent** 13-9" in field.value
    assert "<agent> 21/14/5 · 30% HS · 291 ACS" in field.value
    assert "🔴" in field.value
    assert card.footer.text == "EU · V26 // ACT VI"
    assert card.thumbnail.url == "https://example.invalid/card-small.png"


async def test_hidden_name_still_renders_the_card(monkeypatch):
    """The hide-name preference must replace the account label."""
    bot = build_bot()

    followup = await run(
        monkeypatch,
        bot,
        viewer=(ACCOUNT, True, TEST_TRANSLATOR.text(TEST_LOCALE, "account-hidden")),
    )

    hidden = TEST_TRANSLATOR.text(TEST_LOCALE, "account-hidden")
    assert followup.sent[0]["embed"].description.startswith(f"**{hidden}**")


async def test_unranked_account_renders_without_a_rating(monkeypatch):
    """An unranked account must still show its level and matches."""
    bot = build_bot(
        profile_data=profile(tier=0, rr=None, wins=0, games=0, peak_tier=None)
    )

    followup = await run(monkeypatch, bot)

    card = followup.sent[0]["embed"]
    assert card.description.startswith("**KumKaShree#Shree**\n\n")
    unranked = TEST_TRANSLATOR.text(TEST_LOCALE, "profile-unranked")
    assert f"**{unranked}**" in card.description
    assert "RR" not in card.description
    assert "WR" not in card.description


async def test_missing_account_asks_for_login(monkeypatch):
    """An unlinked caller must be told to log in."""
    monkeypatch.setattr(profile_cog, "selected_account", AsyncMock(return_value=None))
    followup = Followup()

    await ProfileCog(build_bot()).profile.callback(
        ProfileCog(build_bot()), interaction(followup=followup)
    )

    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "error-not-registered"
    )
    assert followup.sent[0]["ephemeral"] is True


async def test_unavailable_profile_uses_the_riot_error(monkeypatch):
    """A failed profile fetch must use the existing Riot-unavailable message."""
    bot = build_bot()
    bot.profiles.profile = AsyncMock(side_effect=ProfileUnavailable("down"))

    followup = await run(monkeypatch, bot)

    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "error-riot-services-unavailable"
    )


async def test_failed_matches_still_render_the_card(monkeypatch):
    """A match-history failure must not hide the rank and level."""
    bot = build_bot(matches=MatchesUnavailable("down"))

    followup = await run(monkeypatch, bot)

    card = followup.sent[0]["embed"]
    assert card.fields[0].value == (
        f"-# {TEST_TRANSLATOR.text(TEST_LOCALE, 'profile-no-matches')}"
    )


async def test_equipped_title_sits_under_the_name(monkeypatch):
    """The equipped title follows the name directly, then a gap before the rank."""
    bot = build_bot(profile_data=profile(title_id="title-1"), title_text="V1.0")

    followup = await run(monkeypatch, bot)

    description = followup.sent[0]["embed"].description
    assert description.startswith("**KumKaShree#Shree**\n-# V1.0\n\n<rank19>")


async def test_ranked_matches_show_the_rr_change(monkeypatch):
    """A competitive match must show the RR it gained or lost."""
    bot = build_bot(matches=[summary()], ranked={"m1": 17})

    followup = await run(monkeypatch, bot)

    assert "**Ascent** 13-9 · +17 RR" in followup.sent[0]["embed"].fields[0].value


async def test_ranked_matches_lose_rr_with_a_minus(monkeypatch):
    """A loss must render its RR change with a minus sign."""
    bot = build_bot(matches=[summary(won=False)], ranked={"m1": -12})

    followup = await run(monkeypatch, bot)

    assert "13-9 · -12 RR" in followup.sent[0]["embed"].fields[0].value


def test_match_block_omits_unavailable_stats():
    """A match without shots or rounds must drop those segments only."""
    match = summary(headshot_hits=0, total_hits=0, rounds=0, rounds_won=None)

    block = _match_block(
        match,
        puuid="puuid-1",
        map_names={"map-1": {"en-US": "Ascent"}},
        emoji_service=emoji_service(),
        translator=TEST_TRANSLATOR,
        locale=TEST_LOCALE,
    )

    assert "HS" not in block
    assert "ACS" not in block
    assert "13-9" not in block
    assert "<agent> 21/14/5" in block


def test_match_block_resolves_riot_map_asset_paths():
    """Match details send an asset path, so the map name must still render."""
    block = _match_block(
        summary(map_id="/Game/Maps/Ascent/Ascent"),
        puuid="puuid-1",
        map_names={"/game/maps/ascent/ascent": {"en-US": "Ascent"}},
        emoji_service=emoji_service(),
        translator=TEST_TRANSLATOR,
        locale=TEST_LOCALE,
    )

    assert "**Ascent**" in block


def test_match_stats_are_indented():
    """The stat line must start with a tab-like indent before the agent icon."""
    block = _match_block(
        summary(),
        puuid="puuid-1",
        map_names={"map-1": {"en-US": "Ascent"}},
        emoji_service=emoji_service(),
        translator=TEST_TRANSLATOR,
        locale=TEST_LOCALE,
    )

    stats_line = block.splitlines()[1]
    assert stats_line.startswith("-# ↳ <agent>")


FOREIGN = SimpleNamespace(id=2)


def sharing(enabled: bool):
    """Build a stored user record with the profile-sharing preference."""
    return SimpleNamespace(others_can_view_profile=enabled)


async def test_a_shared_foreign_profile_is_rendered(monkeypatch):
    """Another user's profile must render when they opted in."""
    bot = build_bot()

    followup = await run(monkeypatch, bot, user=FOREIGN, settings=sharing(True))

    assert followup.sent[0]["embed"].description.startswith("**KumKaShree#Shree**")


async def test_a_private_foreign_profile_is_refused(monkeypatch):
    """A user who did not opt in must not have their profile fetched."""
    bot = build_bot()

    followup = await run(monkeypatch, bot, user=FOREIGN, settings=sharing(False))

    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "profile-user-not-sharing"
    )
    bot.profiles.profile.assert_not_awaited()


async def test_sharing_is_rechecked_after_reloading_the_account(monkeypatch):
    """Turning sharing off mid-command must still block the render."""
    private = SimpleNamespace(
        puuid="puuid-1",
        region="eu",
        user=SimpleNamespace(others_can_view_profile=False),
    )
    bot = build_bot()

    followup = await run(
        monkeypatch,
        bot,
        user=FOREIGN,
        settings=sharing(True),
        viewer=(private, False, "KumKaShree#Shree"),
    )

    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "profile-user-not-sharing"
    )
    bot.profiles.profile.assert_not_awaited()


async def test_a_foreign_user_without_an_account_is_reported(monkeypatch):
    """An unlinked target must get a third-person message, not the login one."""
    bot = build_bot()
    monkeypatch.setattr(profile_cog, "selected_account", AsyncMock(return_value=None))
    monkeypatch.setattr(profile_cog, "get_user", AsyncMock(return_value=sharing(True)))
    followup = Followup()
    cog = ProfileCog(bot)

    await cog.profile.callback(cog, interaction(followup=followup), user=FOREIGN)

    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, "profile-user-not-registered"
    )


async def test_own_profile_ignores_the_sharing_setting(monkeypatch):
    """The caller always sees their own profile, even with sharing off."""
    bot = build_bot()

    followup = await run(monkeypatch, bot, settings=sharing(False))

    assert followup.sent[0]["embed"].description.startswith("**KumKaShree#Shree**")


async def test_a_foreign_profile_uses_the_targets_hide_name_setting(monkeypatch):
    """The target's own privacy settings, not the viewer's, decide the label."""
    bot = build_bot()
    hidden = TEST_TRANSLATOR.text(TEST_LOCALE, "account-hidden")

    followup = await run(
        monkeypatch,
        bot,
        user=FOREIGN,
        settings=sharing(True),
        viewer=(ACCOUNT, True, hidden),
    )

    assert followup.sent[0]["embed"].description.startswith(f"**{hidden}**")


async def test_foreign_views_are_rate_limited(monkeypatch):
    """A second third-party view inside the window must not fetch again."""
    bot = build_bot()
    monkeypatch.setattr(
        profile_cog, "selected_account", AsyncMock(return_value=ACCOUNT)
    )
    monkeypatch.setattr(
        profile_cog,
        "account_viewer",
        AsyncMock(return_value=(ACCOUNT, False, "KumKaShree#Shree")),
    )
    monkeypatch.setattr(profile_cog, "get_user", AsyncMock(return_value=sharing(True)))
    cog = ProfileCog(bot)

    await cog.profile.callback(cog, interaction(followup=Followup()), user=FOREIGN)
    second = Followup()
    await cog.profile.callback(cog, interaction(followup=second), user=FOREIGN)

    description = second.sent[0]["embed"].description
    assert description.startswith("Wait")
    assert bot.profiles.profile.await_count == 1


async def test_the_cooldown_expires(monkeypatch):
    """After the window another third-party view is allowed again."""
    clock = [1000.0]
    monkeypatch.setattr(profile_cog.time, "monotonic", lambda: clock[0])
    bot = build_bot()
    monkeypatch.setattr(
        profile_cog, "selected_account", AsyncMock(return_value=ACCOUNT)
    )
    monkeypatch.setattr(
        profile_cog,
        "account_viewer",
        AsyncMock(return_value=(ACCOUNT, False, "KumKaShree#Shree")),
    )
    monkeypatch.setattr(profile_cog, "get_user", AsyncMock(return_value=sharing(True)))
    cog = ProfileCog(bot)

    await cog.profile.callback(cog, interaction(followup=Followup()), user=FOREIGN)
    clock[0] += profile_cog.FOREIGN_VIEW_COOLDOWN_SECONDS + 1
    again = Followup()
    await cog.profile.callback(cog, interaction(followup=again), user=FOREIGN)

    assert again.sent[0]["embed"].description.startswith("**KumKaShree#Shree**")
    assert bot.profiles.profile.await_count == 2


async def test_own_profile_is_not_rate_limited(monkeypatch):
    """The caller's own profile must render on every press."""
    bot = build_bot()
    monkeypatch.setattr(
        profile_cog, "selected_account", AsyncMock(return_value=ACCOUNT)
    )
    monkeypatch.setattr(
        profile_cog,
        "account_viewer",
        AsyncMock(return_value=(ACCOUNT, False, "KumKaShree#Shree")),
    )
    cog = ProfileCog(bot)

    await cog.profile.callback(cog, interaction(followup=Followup()))
    second = Followup()
    await cog.profile.callback(cog, interaction(followup=second))

    assert second.sent[0]["embed"].description.startswith("**KumKaShree#Shree**")


async def test_a_failed_foreign_fetch_releases_the_slot(monkeypatch):
    """A fetch failure must not spend the caller's cooldown."""
    bot = build_bot()
    bot.profiles.profile = AsyncMock(side_effect=ProfileUnavailable("down"))
    monkeypatch.setattr(
        profile_cog, "selected_account", AsyncMock(return_value=ACCOUNT)
    )
    monkeypatch.setattr(
        profile_cog,
        "account_viewer",
        AsyncMock(return_value=(ACCOUNT, False, "KumKaShree#Shree")),
    )
    monkeypatch.setattr(profile_cog, "get_user", AsyncMock(return_value=sharing(True)))
    cog = ProfileCog(bot)

    first = Followup()
    await cog.profile.callback(cog, interaction(followup=first), user=FOREIGN)
    second = Followup()
    await cog.profile.callback(cog, interaction(followup=second), user=FOREIGN)

    expected = TEST_TRANSLATOR.text(TEST_LOCALE, "error-riot-services-unavailable")
    assert first.sent[0]["embed"].description == expected
    assert second.sent[0]["embed"].description == expected
    assert bot.profiles.profile.await_count == 2


async def test_a_refused_foreign_view_releases_the_slot(monkeypatch):
    """A refused view must not spend the caller's cooldown either."""
    bot = build_bot()
    monkeypatch.setattr(
        profile_cog, "selected_account", AsyncMock(return_value=ACCOUNT)
    )
    monkeypatch.setattr(profile_cog, "get_user", AsyncMock(return_value=sharing(False)))
    cog = ProfileCog(bot)

    first = Followup()
    await cog.profile.callback(cog, interaction(followup=first), user=FOREIGN)
    second = Followup()
    await cog.profile.callback(cog, interaction(followup=second), user=FOREIGN)

    expected = TEST_TRANSLATOR.text(TEST_LOCALE, "profile-user-not-sharing")
    assert first.sent[0]["embed"].description == expected
    assert second.sent[0]["embed"].description == expected


@pytest.mark.parametrize(
    ("foreign", "key"),
    [
        (False, "error-riot-login-expired"),
        (True, "profile-user-login-expired"),
    ],
)
async def test_an_expired_login_names_who_needs_to_sign_in(monkeypatch, foreign, key):
    """A dead target session must not tell the viewer to log in themselves."""
    bot = build_bot()
    bot.profiles.profile = AsyncMock(side_effect=AuthenticationRequired("expired"))

    followup = await run(
        monkeypatch,
        bot,
        user=FOREIGN if foreign else None,
        settings=sharing(True),
    )

    assert followup.sent[0]["embed"].description == TEST_TRANSLATOR.text(
        TEST_LOCALE, key
    )
