"""Unit and database tests for rank roles."""

from __future__ import annotations

from types import SimpleNamespace

import aiohttp
import discord
import pytest
from cryptography.fernet import Fernet
from tortoise.exceptions import IntegrityError
from tortoise.queryset import QuerySet

from src.bot import BotFraggBot
from src.cogs import rankrole
from src.cogs.rankrole import RankRoleCog, plan_changes, tier_group
from src.config import Settings
from src.models import RankRole, RankRolePanel
from src.views.components import PUBLIC_ACTION_RE, public_custom_id
from tests.helpers import TEST_TRANSLATOR


@pytest.mark.parametrize(
    ("tier", "expected"),
    [
        (0, None),
        (2, None),
        (3, "iron"),
        (5, "iron"),
        (6, "bronze"),
        (8, "bronze"),
        (9, "silver"),
        (12, "gold"),
        (18, "diamond"),
        (21, "ascendant"),
        (24, "immortal"),
        (26, "immortal"),
        (27, "radiant"),
        (28, None),
        (99, None),
    ],
)
def test_tier_group_maps_every_competitive_tier(
    tier: int, expected: str | None
) -> None:
    """Verify that each tier id maps to its group and unranked ids map to nothing."""
    assert tier_group(tier) == expected


def test_every_tier_group_has_a_range() -> None:
    """Verify that no configured group is unreachable from a tier id."""
    assert {group for _, _, group in rankrole.TIER_RANGES} == set(rankrole.TIER_GROUPS)


def test_every_group_has_a_representative_emoji_tier() -> None:
    """Verify that each group's emoji tier maps back to that same group."""
    assert set(rankrole.TIER_EMOJI_TIERS) == set(rankrole.TIER_GROUPS)
    for group, tier in rankrole.TIER_EMOJI_TIERS.items():
        assert tier_group(tier) == group


def test_select_emoji_tolerates_a_missing_emoji() -> None:
    """Verify that an absent application emoji is left out rather than raising."""
    assert rankrole._select_emoji("") is None


def test_plan_changes_strips_other_mapped_roles() -> None:
    """Verify that moving tier removes the previously held mapped role."""
    stale, needs_add = plan_changes({10, 20, 999}, {10: "gold", 20: "diamond"}, 20)

    assert stale == [10]
    assert needs_add is False


def test_plan_changes_leaves_unmapped_roles_alone() -> None:
    """Verify that roles outside the guild mapping are never removed."""
    stale, needs_add = plan_changes({999}, {10: "gold"}, None)

    assert stale == []
    assert needs_add is False


def test_plan_changes_requests_a_missing_target() -> None:
    """Verify that a member without the target role is asked to add it."""
    stale, needs_add = plan_changes({999}, {10: "gold"}, 10)

    assert stale == []
    assert needs_add is True


def test_plan_changes_is_a_noop_when_already_correct() -> None:
    """Verify that holding exactly the target role produces no Discord writes."""
    stale, needs_add = plan_changes({10, 999}, {10: "gold"}, 10)

    assert stale == []
    assert needs_add is False


def test_plan_changes_strips_every_mapped_role_when_removing() -> None:
    """Verify that removal clears each mapped role the member holds."""
    stale, needs_add = plan_changes({10, 20, 999}, {10: "gold", 20: "diamond"}, None)

    assert stale == [10, 20]
    assert needs_add is False


def _bare_cog() -> RankRoleCog:
    """Build a cog without its bot so throttling can be tested alone."""
    cog = object.__new__(RankRoleCog)
    cog._recent = {}
    return cog


def test_throttle_allows_the_first_press_then_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a second press inside the window is refused."""
    monkeypatch.setattr(rankrole.time, "monotonic", lambda: 100.0)
    cog = _bare_cog()

    assert cog._throttled(7) is False
    assert cog._throttled(7) is True


def test_throttle_releases_after_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that the debounce window expires."""
    times = iter([100.0, 100.0 + rankrole.DEBOUNCE_SECONDS + 1])
    monkeypatch.setattr(rankrole.time, "monotonic", lambda: next(times))
    cog = _bare_cog()

    assert cog._throttled(7) is False
    assert cog._throttled(7) is False


def test_public_custom_id_round_trips() -> None:
    """Verify that a member-facing custom ID parses back to its action."""
    custom_id = public_custom_id("rankrole_add")

    match = PUBLIC_ACTION_RE.fullmatch(custom_id)

    assert match is not None
    assert match["action"] == "rankrole_add"
    assert match["payload"] == ""


def test_public_custom_id_rejects_a_colon_payload() -> None:
    """Verify that a payload containing a colon cannot produce a valid ID."""
    match = PUBLIC_ACTION_RE.fullmatch(public_custom_id("rankrole_add", "1:2"))

    assert match is None


class _FakeRole:
    """Minimal stand-in for a Discord role used by the role writer."""

    def __init__(self, role_id: int, position: int, *, everyone: bool = False) -> None:
        """Record the identity, ordering position, and everyone flag."""
        self.id = role_id
        self.position = position
        self.managed = False
        self._everyone = everyone

    def is_default(self) -> bool:
        """Report whether this is the guild's everyone role."""
        return self._everyone

    @property
    def mention(self) -> str:
        """Render the role the way a mention would appear."""
        return f"<@&{self.id}>"

    @property
    def name(self) -> str:
        """Name the role the way Discord would display it."""
        return f"Role {self.id}"

    def __ge__(self, other: object) -> bool:
        """Compare roles the way Discord orders them."""
        return self.position >= getattr(other, "position", -1)

    def __gt__(self, other: object) -> bool:
        """Compare roles the way Discord orders them."""
        return self.position > getattr(other, "position", -1)


class _FakeMember(discord.Member):
    """A Member subclass that records the role set one sync writes."""

    id = 42

    def __init__(self, roles: list[_FakeRole], error: Exception | None = None) -> None:
        """Start with the member's current roles and an optional failure."""
        self._roles = roles
        self.written: list[list[_FakeRole]] | None = None
        self.error = error

    @property  # type: ignore[override]
    def roles(self) -> list[_FakeRole]:
        """Return the member's current roles."""
        return self._roles

    async def edit(self, *, roles: list[_FakeRole], reason: str) -> None:
        """Capture the single role edit, or raise the configured failure."""
        if self.error is not None:
            raise self.error
        self.written = [roles]


class _FakeGuild:
    """Supply the roles and permissions one sync reads."""

    def __init__(self, roles: dict[int, _FakeRole], top: _FakeRole) -> None:
        """Record the role lookup table and the bot's highest role."""
        self.id = 1
        self._roles = roles
        self.me = SimpleNamespace(
            top_role=top, guild_permissions=SimpleNamespace(manage_roles=True)
        )

    def get_role(self, role_id: int) -> _FakeRole | None:
        """Return a configured role by id."""
        return self._roles.get(role_id)


def _sync_cog(by_tier: dict[str, int], by_role: dict[int, str]) -> RankRoleCog:
    """Build a cog whose mapping lookup returns the given tables."""
    cog = object.__new__(RankRoleCog)

    async def mapped(guild: object) -> tuple[dict[str, int], dict[int, str]]:
        return by_tier, by_role

    cog._mapped_roles = mapped  # type: ignore[method-assign]
    return cog


async def test_sync_adds_the_target_role() -> None:
    """Verify that a member without the target gains exactly that role."""
    gold = _FakeRole(10, 5)
    other = _FakeRole(999, 9)
    everyone = _FakeRole(1, 0, everyone=True)
    guild = _FakeGuild({10: gold}, _FakeRole(50, 50))
    member = _FakeMember([everyone, other])
    cog = _sync_cog({"gold": 10}, {10: "gold"})

    key = await cog._sync_member(guild, member, "gold")

    assert key == "rankrole-updated"
    assert member.written == [[other, gold]]


async def test_sync_swaps_one_mapped_role_for_another() -> None:
    """Verify that a rank change replaces the old mapped role in one edit."""
    old = _FakeRole(10, 5)
    new = _FakeRole(20, 6)
    unrelated = _FakeRole(999, 9)
    everyone = _FakeRole(1, 0, everyone=True)
    guild = _FakeGuild({10: old, 20: new}, _FakeRole(50, 50))
    member = _FakeMember([everyone, old, unrelated])
    cog = _sync_cog({"gold": 10, "platinum": 20}, {10: "gold", 20: "platinum"})

    key = await cog._sync_member(guild, member, "platinum")

    assert key == "rankrole-updated"
    assert member.written == [[unrelated, new]]


async def test_sync_is_a_noop_when_the_role_is_already_held() -> None:
    """Verify that an already correct member produces no Discord write."""
    gold = _FakeRole(10, 5)
    guild = _FakeGuild({10: gold}, _FakeRole(50, 50))
    member = _FakeMember([_FakeRole(1, 0, everyone=True), gold])
    cog = _sync_cog({"gold": 10}, {10: "gold"})

    key = await cog._sync_member(guild, member, "gold")

    assert key == "rankrole-already"
    assert member.written is None


async def test_sync_strips_every_mapped_role_on_removal() -> None:
    """Verify that removal clears each mapped role and keeps unrelated ones."""
    gold = _FakeRole(10, 5)
    diamond = _FakeRole(20, 6)
    unrelated = _FakeRole(999, 9)
    guild = _FakeGuild({10: gold, 20: diamond}, _FakeRole(50, 50))
    member = _FakeMember([_FakeRole(1, 0, everyone=True), gold, diamond, unrelated])
    cog = _sync_cog({"gold": 10, "diamond": 20}, {10: "gold", 20: "diamond"})

    key = await cog._sync_member(guild, member, None)

    assert key == "rankrole-removed"
    assert member.written == [[unrelated]]


async def test_sync_refuses_a_role_above_the_bot() -> None:
    """Verify that a mapped role above the bot's top role is refused."""
    high = _FakeRole(10, 60)
    guild = _FakeGuild({10: high}, _FakeRole(50, 50))
    member = _FakeMember([_FakeRole(1, 0, everyone=True)])
    cog = _sync_cog({"gold": 10}, {10: "gold"})

    key = await cog._sync_member(guild, member, "gold")

    assert key == "rankrole-hierarchy"
    assert member.written is None


async def test_sync_reports_an_unmapped_tier() -> None:
    """Verify that a rank without a configured role is reported as unmapped."""
    guild = _FakeGuild({}, _FakeRole(50, 50))
    member = _FakeMember([_FakeRole(1, 0, everyone=True)])
    cog = _sync_cog({"gold": 10}, {10: "gold"})

    key = await cog._sync_member(guild, member, "radiant")

    assert key == "rankrole-tier-unmapped"
    assert member.written is None


async def test_sync_reports_a_forbidden_edit() -> None:
    """Verify that a refused role edit is reported, not raised."""
    gold = _FakeRole(10, 5)
    guild = _FakeGuild({10: gold}, _FakeRole(50, 50))
    member = _FakeMember([_FakeRole(1, 0, everyone=True)])
    member.error = discord.Forbidden(
        SimpleNamespace(status=403, reason="Forbidden"), "denied"
    )
    cog = _sync_cog({"gold": 10}, {10: "gold"})

    key = await cog._sync_member(guild, member, "gold")

    assert key == "rankrole-no-manage-roles"


async def test_sync_reports_a_failed_edit() -> None:
    """Verify that a transport failure during the edit is reported."""
    gold = _FakeRole(10, 5)
    guild = _FakeGuild({10: gold}, _FakeRole(50, 50))
    member = _FakeMember([_FakeRole(1, 0, everyone=True)])
    member.error = discord.HTTPException(
        SimpleNamespace(status=500, reason="Server Error"), "boom"
    )
    cog = _sync_cog({"gold": 10}, {10: "gold"})

    key = await cog._sync_member(guild, member, "gold")

    assert key == "rankrole-sync-failed"


@pytest.mark.usefixtures("backend_database")
async def test_rank_role_mapping_is_unique_per_guild_and_tier() -> None:
    """Verify that the unique pair prevents a duplicate tier mapping."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)

    with pytest.raises(IntegrityError):
        await RankRole.create(guild_id=7, tier_group="gold", role_id=11)

    await RankRole.create(guild_id=8, tier_group="gold", role_id=11)
    assert await RankRole.filter(tier_group="gold").count() == 2


@pytest.mark.usefixtures("backend_database")
async def test_rank_role_panel_is_one_row_per_guild() -> None:
    """Verify that a guild has a single panel row keyed by its id."""
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    await RankRolePanel.filter(guild_id=7).update(message_id=None)

    panel = await RankRolePanel.get(guild_id=7)

    assert panel.channel_id == 100
    assert panel.message_id is None
    assert await RankRolePanel.all().count() == 1


@pytest.mark.usefixtures("backend_database")
async def test_apply_mapping_rejects_managed_and_everyone_roles() -> None:
    """Verify that unusable roles are refused before anything is stored."""
    cog = object.__new__(RankRoleCog)
    guild = SimpleNamespace(id=7, me=SimpleNamespace(top_role=_FakeRole(50, 50)))

    everyone = _FakeRole(1, 0, everyone=True)
    managed = _FakeRole(2, 5)
    managed.managed = True
    too_high = _FakeRole(3, 60)

    assert await cog.apply_mapping(guild, "gold", everyone) == "rankrole-role-invalid"
    assert await cog.apply_mapping(guild, "gold", managed) == "rankrole-role-invalid"
    assert await cog.apply_mapping(guild, "gold", too_high) == "rankrole-hierarchy"
    assert await RankRole.all().count() == 0


@pytest.mark.usefixtures("backend_database")
async def test_apply_mapping_upserts_one_row_per_tier() -> None:
    """Verify that remapping a tier replaces its role instead of adding a row."""
    cog = object.__new__(RankRoleCog)
    guild = SimpleNamespace(id=7, me=SimpleNamespace(top_role=_FakeRole(50, 50)))

    assert await cog.apply_mapping(guild, "gold", _FakeRole(10, 5)) is None
    assert await cog.apply_mapping(guild, "gold", _FakeRole(11, 6)) is None

    rows = await RankRole.filter(guild_id=7)
    assert len(rows) == 1
    assert rows[0].role_id == 11


@pytest.mark.usefixtures("backend_database")
async def test_guild_removal_forgets_rank_role_configuration() -> None:
    """Verify that leaving a guild deletes its panel and mappings."""
    from src.cogs.events import EventsCog

    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRole.create(guild_id=8, tier_group="gold", role_id=11)
    cog = object.__new__(EventsCog)

    await cog._forget_guild(SimpleNamespace(id=7))

    assert await RankRolePanel.filter(guild_id=7).count() == 0
    assert await RankRole.filter(guild_id=7).count() == 0
    assert await RankRole.filter(guild_id=8).count() == 1


def test_bot_still_requests_no_privileged_intents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that the real bot keeps members, presence, and content disabled."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DISCORD_TOKEN", "test")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    bot = BotFraggBot(Settings.from_env())

    assert bot.intents.members is False
    assert bot.intents.presences is False
    assert bot.intents.message_content is False
    assert bot.intents.guilds is True


class _FakeMessage:
    """Record edits and deletions of a posted panel message."""

    def __init__(
        self,
        message_id: int,
        *,
        delete_error: Exception | None = None,
        edit_error: Exception | None = None,
    ) -> None:
        """Store the identity and any configured per-operation failure."""
        self.id = message_id
        self.deleted = False
        self.edited: list[str | None] = []
        self.delete_error = delete_error
        self.edit_error = edit_error

    async def delete(self) -> None:
        """Record deletion, or raise the configured delete failure."""
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted = True

    async def edit(self, **kwargs: object) -> None:
        """Record the content written when a delete is refused."""
        if self.edit_error is not None:
            raise self.edit_error
        self.edited.append(kwargs.get("content"))  # type: ignore[arg-type]


async def _return(message: object) -> object:
    """Return a prepared message from an async send."""
    return message


class _FakeChannel:
    """Serve and record panel messages for one channel."""

    def __init__(
        self,
        *,
        message: _FakeMessage | None = None,
        fetch_error: Exception | None = None,
        send_error: Exception | None = None,
    ) -> None:
        """Configure what fetch and send return or raise."""
        self.message = message
        self.fetch_error = fetch_error
        self.send_error = send_error
        self.sent: list[dict[str, object]] = []

    async def fetch_message(self, message_id: int) -> _FakeMessage:
        """Return the stored message or raise the configured failure."""
        if self.fetch_error is not None:
            raise self.fetch_error
        if self.message is None:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "")
        return self.message

    async def send(self, **kwargs: object) -> _FakeMessage:
        """Record a new panel post or raise the configured failure."""
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(kwargs)
        return _FakeMessage(555)


def _panel_cog(channel: _FakeChannel | None) -> RankRoleCog:
    """Build a cog whose panel channel lookup returns one fake channel."""
    cog = object.__new__(RankRoleCog)
    cog.bot = SimpleNamespace(
        translator=TEST_TRANSLATOR,
        emoji_service=SimpleNamespace(rank_emoji=lambda _: ""),
    )

    async def panel_channel(guild: object, channel_id: int) -> object:
        return channel

    cog._panel_channel = panel_channel  # type: ignore[method-assign]
    return cog


def _panel_interaction() -> SimpleNamespace:
    """Build the interaction shape the panel builder and dashboard read."""
    interaction = SimpleNamespace(
        guild=SimpleNamespace(id=7, get_role=lambda role_id: None),
        locale="en-US",
        client=SimpleNamespace(translator=TEST_TRANSLATOR),
    )

    async def edit_original_response(**kwargs: object) -> None:
        interaction.edited = kwargs

    interaction.edit_original_response = edit_original_response
    return interaction


@pytest.mark.usefixtures("backend_database")
async def test_publish_posts_the_panel_once_and_stores_the_message() -> None:
    """Verify that publishing with no stored message posts and records it."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100)
    channel = _FakeChannel()
    cog = _panel_cog(channel)

    assert await cog.publish_panel(_panel_interaction()) is None

    panel = await RankRolePanel.get(guild_id=7)
    assert panel.message_id == 555
    assert len(channel.sent) == 1


@pytest.mark.usefixtures("backend_database")
async def test_publish_edits_the_stored_panel_without_reposting() -> None:
    """Verify that an existing panel is edited in place."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    message = _FakeMessage(200)
    channel = _FakeChannel(message=message)
    cog = _panel_cog(channel)

    assert await cog.publish_panel(_panel_interaction()) is None

    assert channel.sent == []
    assert len(message.edited) == 1


@pytest.mark.usefixtures("backend_database")
async def test_publish_reposts_when_the_stored_panel_is_gone() -> None:
    """Verify that a deleted panel is replaced rather than left dangling."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    channel = _FakeChannel()
    cog = _panel_cog(channel)

    assert await cog.publish_panel(_panel_interaction()) is None

    panel = await RankRolePanel.get(guild_id=7)
    assert panel.message_id == 555
    assert len(channel.sent) == 1


@pytest.mark.usefixtures("backend_database")
async def test_publish_does_not_duplicate_on_a_fetch_failure() -> None:
    """Verify that a permission or transient fetch error blocks publishing."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    channel = _FakeChannel(
        fetch_error=discord.Forbidden(
            SimpleNamespace(status=403, reason="Forbidden"), ""
        )
    )
    cog = _panel_cog(channel)

    assert await cog.publish_panel(_panel_interaction()) == "rankrole-panel-blocked"

    panel = await RankRolePanel.get(guild_id=7)
    assert panel.message_id == 200
    assert channel.sent == []


@pytest.mark.usefixtures("backend_database")
async def test_retire_deletes_the_panel_and_clears_the_message_id() -> None:
    """Verify that retiring deletes the posted message and forgets it."""
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    message = _FakeMessage(200)
    cog = _panel_cog(_FakeChannel(message=message))

    assert await cog.retire_panel(_panel_interaction(), SimpleNamespace(id=7)) is True

    panel = await RankRolePanel.get(guild_id=7)
    assert message.deleted is True
    assert panel.message_id is None


@pytest.mark.usefixtures("backend_database")
async def test_retire_disables_the_panel_when_delete_is_refused() -> None:
    """Verify that an undeletable panel is edited to a disabled state."""
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    message = _FakeMessage(
        200,
        delete_error=discord.Forbidden(
            SimpleNamespace(status=403, reason="Forbidden"), ""
        ),
    )
    cog = _panel_cog(_FakeChannel(message=message))

    assert await cog.retire_panel(_panel_interaction(), SimpleNamespace(id=7)) is True

    assert message.deleted is False
    assert len(message.edited) == 1


@pytest.mark.usefixtures("backend_database")
async def test_retire_keeps_the_message_id_when_the_panel_is_unreadable() -> None:
    """Verify that an unreadable panel keeps its reference instead of orphaning."""
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    channel = _FakeChannel(
        fetch_error=discord.Forbidden(
            SimpleNamespace(status=403, reason="Forbidden"), ""
        )
    )
    cog = _panel_cog(channel)

    assert await cog.retire_panel(_panel_interaction(), SimpleNamespace(id=7)) is False

    panel = await RankRolePanel.get(guild_id=7)
    assert panel.message_id == 200


@pytest.mark.usefixtures("backend_database")
async def test_retire_forgets_the_panel_row_when_its_channel_is_gone() -> None:
    """Verify that a deleted channel lets the stale reference be dropped."""
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    cog = object.__new__(RankRoleCog)

    async def panel_channel(guild: object, channel_id: int) -> None:
        return None

    cog._panel_channel = panel_channel  # type: ignore[method-assign]

    assert await cog.retire_panel(_panel_interaction(), SimpleNamespace(id=7)) is True

    panel = await RankRolePanel.get(guild_id=7)
    assert panel.message_id is None


@pytest.mark.usefixtures("backend_database")
async def test_rank_role_panel_refuses_a_second_row_for_one_guild() -> None:
    """Verify that the guild primary key enforces one panel per guild."""
    await RankRolePanel.create(guild_id=7, channel_id=100)

    with pytest.raises(IntegrityError):
        await RankRolePanel.create(guild_id=7, channel_id=101)


def _unreadable_panel_cog() -> RankRoleCog:
    """Build a cog whose panel message cannot be read back."""
    channel = _FakeChannel(
        fetch_error=discord.Forbidden(
            SimpleNamespace(status=403, reason="Forbidden"), ""
        )
    )
    return _panel_cog(channel)


@pytest.mark.usefixtures("backend_database")
async def test_refresh_reports_failure_when_the_panel_is_unreadable() -> None:
    """Verify that a refresh that cannot read the panel reports failure."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)

    assert (
        await _unreadable_panel_cog().refresh_panel(_panel_interaction())
        == "rankrole-panel-blocked"
    )


@pytest.mark.usefixtures("backend_database")
async def test_refresh_reports_success_when_there_is_nothing_to_do() -> None:
    """Verify that an unposted panel is not treated as a failure."""
    cog = _panel_cog(None)

    assert await cog.refresh_panel(_panel_interaction()) is None


@pytest.mark.usefixtures("backend_database")
async def test_reset_all_aborts_when_the_panel_cannot_be_retired() -> None:
    """Verify that a failed retire keeps the mappings and the panel row."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    cog = _unreadable_panel_cog()

    problem = await cog.reset_all(
        _panel_interaction(),
        SimpleNamespace(id=7, get_role=lambda role_id: None),
        "all",
    )

    assert problem == "rankrole-panel-blocked"
    assert await RankRole.filter(guild_id=7).count() == 1
    assert (await RankRolePanel.get(guild_id=7)).message_id == 200


@pytest.mark.usefixtures("backend_database")
async def test_reset_panel_aborts_when_the_panel_cannot_be_retired() -> None:
    """Verify that a blocked panel reset leaves the stored row intact."""
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    cog = _unreadable_panel_cog()

    problem = await cog.reset_all(
        _panel_interaction(),
        SimpleNamespace(id=7, get_role=lambda role_id: None),
        "panel",
    )

    assert problem == "rankrole-panel-blocked"
    assert (await RankRolePanel.get(guild_id=7)).message_id == 200


@pytest.mark.usefixtures("backend_database")
async def test_reset_all_clears_mappings_once_the_panel_is_retired() -> None:
    """Verify that a successful reset retires the panel and drops the mappings."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    message = _FakeMessage(200)
    cog = _panel_cog(_FakeChannel(message=message))

    problem = await cog.reset_all(
        _panel_interaction(),
        SimpleNamespace(id=7, get_role=lambda role_id: None),
        "all",
    )

    assert problem is None
    assert message.deleted is True
    assert await RankRole.filter(guild_id=7).count() == 0


@pytest.mark.usefixtures("backend_database")
async def test_reset_tier_keeps_the_panel_when_mappings_remain() -> None:
    """Verify that resetting one tier updates the panel instead of deleting it."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRole.create(guild_id=7, tier_group="silver", role_id=11)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    message = _FakeMessage(200)
    cog = _panel_cog(_FakeChannel(message=message))

    problem = await cog.reset_all(
        _panel_interaction(),
        SimpleNamespace(id=7, get_role=lambda role_id: None),
        "gold",
    )

    assert problem is None
    assert message.deleted is False
    assert len(message.edited) == 1
    assert await RankRole.filter(guild_id=7).count() == 1


class _RecordingInteraction:
    """Capture every response a handler or control produces."""

    def __init__(self, user: object, guild: object) -> None:
        """Bind the caller, their guild, and empty response sinks."""
        self.user = user
        self.guild = guild
        self.locale = "en-US"
        self.followups: list[dict[str, object]] = []
        self.edits: list[dict[str, object]] = []
        self.deferred = 0

        class _Response:
            def __init__(self, outer: _RecordingInteraction) -> None:
                self.outer = outer

            async def defer(self, **_kwargs: object) -> None:
                self.outer.deferred += 1

            def is_done(self) -> bool:
                return self.outer.deferred > 0

            async def send_message(self, **kwargs: object) -> None:
                self.outer.followups.append(kwargs)

        class _Followup:
            def __init__(self, outer: _RecordingInteraction) -> None:
                self.outer = outer

            async def send(self, **kwargs: object) -> None:
                self.outer.followups.append(kwargs)

        self.response = _Response(self)
        self.followup = _Followup(self)
        self.client = SimpleNamespace(translator=TEST_TRANSLATOR)

    async def edit_original_response(self, **kwargs: object) -> None:
        """Record a dashboard or step edit."""
        self.edits.append(kwargs)


def _handler_cog(by_tier: dict[str, int], by_role: dict[int, str]) -> RankRoleCog:
    """Build a cog with a bot stub and a fixed mapping table."""
    cog = _sync_cog(by_tier, by_role)
    cog.bot = SimpleNamespace(
        translator=TEST_TRANSLATOR,
        emoji_service=SimpleNamespace(rank_emoji=lambda _: ""),
        profiles=SimpleNamespace(),
    )
    cog._recent = {}
    return cog


def _synced_guild(role_id: int) -> tuple[_FakeGuild, _FakeRole]:
    """Build a guild whose bot can assign one mapped role."""
    role = _FakeRole(role_id, 5)
    guild = _FakeGuild({role_id: role}, _FakeRole(50, 50))
    guild.id = 7
    return guild, role


@pytest.mark.usefixtures("backend_database")
async def test_add_role_checks_configuration_before_calling_riot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that an unconfigured guild never reaches the Riot API."""
    called: list[int] = []

    async def selected(discord_id: int) -> None:
        called.append(discord_id)
        return None

    monkeypatch.setattr(rankrole, "selected_account", selected)
    guild, _ = _synced_guild(10)
    member = _FakeMember([_FakeRole(1, 0, everyone=True)])
    interaction = _RecordingInteraction(member, guild)
    cog = _handler_cog({"gold": 10}, {10: "gold"})

    await cog.add_role(interaction, "")

    assert called == []
    assert interaction.followups[0]["embed"].description == TEST_TRANSLATOR.text(
        "en-US", "rankrole-not-configured"
    )


@pytest.mark.usefixtures("backend_database")
async def test_add_role_reports_a_missing_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a member without a linked account is told to log in."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)

    async def selected(discord_id: int) -> None:
        return None

    monkeypatch.setattr(rankrole, "selected_account", selected)
    guild, _ = _synced_guild(10)
    member = _FakeMember([_FakeRole(1, 0, everyone=True)])
    interaction = _RecordingInteraction(member, guild)
    cog = _handler_cog({"gold": 10}, {10: "gold"})

    await cog.add_role(interaction, "")

    assert interaction.followups[0]["embed"].description == TEST_TRANSLATOR.text(
        "en-US", "rankrole-needs-account"
    )


@pytest.mark.usefixtures("backend_database")
async def test_add_role_assigns_the_role_for_the_current_rank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a ranked member receives their mapped role."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)

    async def selected(discord_id: int) -> object:
        return SimpleNamespace()

    async def profile(account: object) -> object:
        return SimpleNamespace(tier=12)

    monkeypatch.setattr(rankrole, "selected_account", selected)
    guild, role = _synced_guild(10)
    member = _FakeMember([_FakeRole(1, 0, everyone=True)])
    interaction = _RecordingInteraction(member, guild)
    cog = _handler_cog({"gold": 10}, {10: "gold"})
    cog.bot.profiles.profile = profile

    await cog.add_role(interaction, "")

    assert member.written == [[role]]


@pytest.mark.usefixtures("backend_database")
async def test_add_role_removes_the_role_when_unranked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that an unranked member has the previous rank role stripped."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)

    async def selected(discord_id: int) -> object:
        return SimpleNamespace()

    async def profile(account: object) -> object:
        return SimpleNamespace(tier=0)

    monkeypatch.setattr(rankrole, "selected_account", selected)
    guild, role = _synced_guild(10)
    member = _FakeMember([_FakeRole(1, 0, everyone=True), role])
    interaction = _RecordingInteraction(member, guild)
    cog = _handler_cog({"gold": 10}, {10: "gold"})
    cog.bot.profiles.profile = profile

    await cog.add_role(interaction, "")

    assert member.written == [[]]
    assert interaction.followups[0]["embed"].description == TEST_TRANSLATOR.text(
        "en-US", "rankrole-unranked"
    )


@pytest.mark.usefixtures("backend_database")
async def test_remove_role_strips_every_mapped_role() -> None:
    """Verify that the Remove button clears mapped roles without any Riot call."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRole.create(guild_id=7, tier_group="silver", role_id=11)
    guild = _FakeGuild({10: _FakeRole(10, 5), 11: _FakeRole(11, 4)}, _FakeRole(50, 50))
    gold = guild.get_role(10)
    silver = guild.get_role(11)
    member = _FakeMember([_FakeRole(1, 0, everyone=True), gold, silver])
    interaction = _RecordingInteraction(member, guild)
    cog = _handler_cog({"gold": 10, "silver": 11}, {10: "gold", 11: "silver"})

    await cog.remove_role(interaction, "")

    assert member.written == [[]]


@pytest.mark.usefixtures("backend_database")
async def test_channel_picker_aborts_when_the_old_panel_lingers() -> None:
    """Verify that a failed retire leaves the configured channel untouched."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    cog = _unreadable_panel_cog()
    guild = SimpleNamespace(id=7, get_role=lambda role_id: None)
    picker = rankrole._ChannelPicker(cog, _panel_interaction(), guild)
    picker._values = [SimpleNamespace(id=999)]
    interaction = _RecordingInteraction(_FakeMember([]), guild)

    await picker.callback(interaction)

    panel = await RankRolePanel.get(guild_id=7)
    assert panel.channel_id == 100
    assert interaction.followups[0]["embed"].description == TEST_TRANSLATOR.text(
        "en-US", "rankrole-panel-blocked"
    )


@pytest.mark.usefixtures("backend_database")
async def test_channel_picker_stores_the_new_channel() -> None:
    """Verify that choosing a fresh channel is stored once the panel is retired."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    message = _FakeMessage(200)
    cog = _panel_cog(_FakeChannel(message=message))
    guild = SimpleNamespace(id=7, get_role=lambda role_id: None)
    picker = rankrole._ChannelPicker(cog, _panel_interaction(), guild)
    picker._values = [SimpleNamespace(id=999)]

    await picker.callback(_RecordingInteraction(_FakeMember([]), guild))

    panel = await RankRolePanel.get(guild_id=7)
    assert panel.channel_id == 999
    assert panel.message_id is None
    assert message.deleted is True


@pytest.mark.usefixtures("backend_database")
async def test_public_button_runs_the_registered_handler() -> None:
    """Verify that a public panel button reaches its registered action."""
    button = rankrole.PublicActionButton("rankrole_add", label="Add")
    calls: list[str] = []

    async def handler(interaction: object, payload: str) -> None:
        calls.append(payload)

    interaction = _RecordingInteraction(_FakeMember([]), SimpleNamespace(id=7))
    interaction.client = SimpleNamespace(
        translator=TEST_TRANSLATOR, component_handlers={"rankrole_add": handler}
    )

    await button.callback(interaction)

    assert calls == [""]


@pytest.mark.usefixtures("backend_database")
async def test_public_button_reports_an_unregistered_action() -> None:
    """Verify that a button with no registered handler replies with an error."""
    button = rankrole.PublicActionButton("rankrole_missing", label="Add")
    interaction = _RecordingInteraction(_FakeMember([]), SimpleNamespace(id=7))
    interaction.client = SimpleNamespace(translator=TEST_TRANSLATOR)

    await button.callback(interaction)

    assert interaction.followups[0]["ephemeral"] is True
    assert interaction.followups[0]["embed"].description == TEST_TRANSLATOR.text(
        "en-US", "component-button-unavailable"
    )


@pytest.mark.usefixtures("backend_database")
async def test_public_button_survives_a_failing_handler() -> None:
    """Verify that a handler exception is reported instead of escaping."""

    async def handler(interaction: object, payload: str) -> None:
        raise RuntimeError("boom")

    button = rankrole.PublicActionButton("rankrole_add", label="Add")
    interaction = _RecordingInteraction(_FakeMember([]), SimpleNamespace(id=7))
    interaction.client = SimpleNamespace(
        translator=TEST_TRANSLATOR, component_handlers={"rankrole_add": handler}
    )

    await button.callback(interaction)

    assert interaction.followups[0]["embed"].description == TEST_TRANSLATOR.text(
        "en-US", "error-command-failed"
    )


@pytest.mark.usefixtures("backend_database")
async def test_reset_tier_restores_the_mapping_when_the_panel_fails() -> None:
    """Verify that a failed tier reset leaves the stored mapping in place."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRole.create(guild_id=7, tier_group="silver", role_id=11)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    cog = _unreadable_panel_cog()

    problem = await cog.reset_all(
        _panel_interaction(),
        SimpleNamespace(id=7, get_role=lambda role_id: None),
        "gold",
    )

    assert problem == "rankrole-panel-blocked"
    restored = await RankRole.get(guild_id=7, tier_group="gold")
    assert restored.role_id == 10
    assert await RankRole.filter(guild_id=7).count() == 2


@pytest.mark.usefixtures("backend_database")
async def test_refresh_reports_failure_when_the_panel_was_deleted() -> None:
    """Verify that a deleted panel is reported so staff can publish again."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)

    assert (
        await _panel_cog(_FakeChannel()).refresh_panel(_panel_interaction())
        == "rankrole-panel-stale"
    )


@pytest.mark.usefixtures("backend_database")
async def test_refresh_reports_failure_when_the_channel_is_gone() -> None:
    """Verify that a deleted channel is reported rather than treated as success."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)

    assert (
        await _panel_cog(None).refresh_panel(_panel_interaction())
        == "rankrole-needs-channel"
    )


@pytest.mark.usefixtures("backend_database")
async def test_dashboard_lists_mapped_and_missing_tiers() -> None:
    """Verify that the staff dashboard shows mappings and the remaining gaps."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100)
    cog = _panel_cog(_FakeChannel())

    card = await cog._dashboard_embed(_panel_interaction(), _dash_guild())

    fields = {field.name: field.value for field in card.fields}
    coverage = fields[
        TEST_TRANSLATOR.text("en-US", "rankrole-dashboard-coverage-field")
    ]
    ranks = fields[TEST_TRANSLATOR.text("en-US", "rankrole-dashboard-mapped-field")]
    gaps = fields[TEST_TRANSLATOR.text("en-US", "rankrole-dashboard-unmapped-field")]
    assert "1 of 9 ranks mapped" in coverage
    assert TEST_TRANSLATOR.text("en-US", "rankrole-tier-gold") in ranks
    assert "<@&10>" in ranks
    assert "Iron" in gaps
    assert card.footer.text == TEST_TRANSLATOR.text(
        "en-US", "rankrole-dashboard-footer"
    )


def _dash_guild() -> SimpleNamespace:
    """Build the guild shape the dashboard reads."""
    return SimpleNamespace(id=7, get_role=lambda role_id: None)


@pytest.mark.usefixtures("backend_database")
async def test_dashboard_reports_an_empty_mapping_set() -> None:
    """Verify that the dashboard explains an entirely unmapped server."""
    cog = _panel_cog(_FakeChannel())

    card = await cog._dashboard_embed(_panel_interaction(), _dash_guild())

    fields = {field.name: field.value for field in card.fields}
    assert fields[
        TEST_TRANSLATOR.text("en-US", "rankrole-dashboard-mapped-field")
    ] == TEST_TRANSLATOR.text("en-US", "rankrole-dashboard-empty-mapped")
    gaps = fields[TEST_TRANSLATOR.text("en-US", "rankrole-dashboard-unmapped-field")]
    for _group, key in rankrole.TIER_ROLES:
        assert TEST_TRANSLATOR.text("en-US", key) in gaps
    coverage = fields[
        TEST_TRANSLATOR.text("en-US", "rankrole-dashboard-coverage-field")
    ]
    assert "0 of 9 ranks mapped" in coverage


@pytest.mark.usefixtures("backend_database")
async def test_save_button_warns_when_the_panel_cannot_be_updated() -> None:
    """Verify that a stale panel produces a retry hint after a successful save."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    cog = _unreadable_panel_cog()
    guild = _synced_guild(10)[0]
    dashboard = _panel_interaction()
    owner = SimpleNamespace(cog=cog, guild=guild, group="silver", role=_FakeRole(11, 6))
    button = rankrole._SaveButton(cog, dashboard, owner)
    interaction = _RecordingInteraction(_FakeMember([]), guild)

    await button.callback(interaction)

    assert interaction.followups[0]["content"] == TEST_TRANSLATOR.text(
        "en-US", "rankrole-panel-blocked"
    )


@pytest.mark.usefixtures("backend_database")
async def test_reset_picker_reports_a_blocked_panel_without_confirming() -> None:
    """Verify that a failed reset shows the reason instead of a success message."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    cog = _unreadable_panel_cog()
    dashboard = _panel_interaction()
    guild = SimpleNamespace(id=7, get_role=lambda role_id: None)
    picker = rankrole._ResetPicker(cog, dashboard, guild)
    picker._values = ["all"]
    interaction = _RecordingInteraction(_FakeMember([]), guild)

    await picker.callback(interaction)

    assert interaction.edits == []
    assert interaction.followups[0]["embed"].description == TEST_TRANSLATOR.text(
        "en-US", "rankrole-panel-blocked"
    )


async def test_public_button_round_trips_through_its_custom_id() -> None:
    """Verify that a restarted bot rebuilds the same button from its ID."""
    original = rankrole.PublicActionButton(
        "rankrole_add",
        label="Add / Update my role",
        emoji=None,
        style=discord.ButtonStyle.success,
        disabled=False,
    )
    item = discord.ui.Button(
        label=original.item.label,
        style=original.item.style,
        custom_id=original.item.custom_id,
    )
    match = PUBLIC_ACTION_RE.fullmatch(original.item.custom_id)
    assert match is not None

    rebuilt = await rankrole.PublicActionButton.from_custom_id(
        SimpleNamespace(), item, match
    )

    assert rebuilt.action == "rankrole_add"
    assert rebuilt.payload == ""
    assert rebuilt.item.label == "Add / Update my role"
    assert rebuilt.item.style is discord.ButtonStyle.success
    assert rebuilt.item.custom_id == original.item.custom_id


def test_public_custom_id_rejects_an_uppercase_action() -> None:
    """Verify that action names outside the lowercase contract never match."""
    assert PUBLIC_ACTION_RE.fullmatch("botfragg_public:rankrole_Add:") is None
    assert PUBLIC_ACTION_RE.fullmatch("botfragg_public:rankrole-add:") is None


@pytest.mark.usefixtures("backend_database")
async def test_mapping_view_starts_with_no_selection() -> None:
    """Verify that the mapping step opens unselected and offering every rank."""
    cog = _panel_cog(_FakeChannel())
    guild = _synced_guild(10)[0]
    view = rankrole._MappingView(cog, _panel_interaction(), guild, {"gold": 10})

    assert view.group is None
    assert view.role is None
    assert [option.value for option in view.rank_select.options] == [
        group for group, _ in rankrole.TIER_ROLES
    ]
    assert len(view.children) == 3


@pytest.mark.usefixtures("backend_database")
async def test_rank_select_notes_the_current_mapping() -> None:
    """Verify that each rank option describes the role it currently awards."""
    cog = _panel_cog(_FakeChannel())
    guild = _synced_guild(10)[0]
    view = rankrole._MappingView(cog, _panel_interaction(), guild, {"gold": 10})

    gold = next(option for option in view.rank_select.options if option.value == "gold")
    iron = next(option for option in view.rank_select.options if option.value == "iron")

    assert gold.description == TEST_TRANSLATOR.text(
        "en-US", "rankrole-choice-current", role="Role 10"
    )
    assert iron.description == TEST_TRANSLATOR.text("en-US", "rankrole-choice-unmapped")


@pytest.mark.usefixtures("backend_database")
async def test_refresh_reports_blocked_on_a_network_error() -> None:
    """Verify that a dropped connection is not mistaken for a deleted panel."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    channel = _FakeChannel(fetch_error=aiohttp.ServerDisconnectedError())
    cog = _panel_cog(channel)

    assert await cog.refresh_panel(_panel_interaction()) == "rankrole-panel-blocked"


@pytest.mark.usefixtures("backend_database")
async def test_retire_keeps_the_pointer_on_a_network_error() -> None:
    """Verify that a network failure never clears the stored panel reference."""
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    channel = _FakeChannel(fetch_error=aiohttp.ServerDisconnectedError())
    cog = _panel_cog(channel)

    retired = await cog.retire_panel(_panel_interaction(), SimpleNamespace(id=7))

    assert retired is False
    panel = await RankRolePanel.get(guild_id=7)
    assert panel.message_id == 200


@pytest.mark.usefixtures("backend_database")
async def test_publish_does_not_duplicate_on_a_network_error() -> None:
    """Verify that a transport failure blocks publishing instead of reposting."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    channel = _FakeChannel(fetch_error=aiohttp.ServerDisconnectedError())
    cog = _panel_cog(channel)

    assert await cog.publish_panel(_panel_interaction()) == "rankrole-panel-blocked"
    assert channel.sent == []


@pytest.mark.usefixtures("backend_database")
async def test_reset_tier_restores_the_mapping_on_a_network_error() -> None:
    """Verify that a dropped connection during reset still restores the tier."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRole.create(guild_id=7, tier_group="silver", role_id=11)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    channel = _FakeChannel(fetch_error=aiohttp.ServerDisconnectedError())
    cog = _panel_cog(channel)
    guild = SimpleNamespace(id=7, get_role=lambda role_id: None)

    problem = await cog.reset_all(_panel_interaction(), guild, "gold")

    assert problem == "rankrole-panel-blocked"
    restored = await RankRole.get(guild_id=7, tier_group="gold")
    assert restored.role_id == 10


async def test_panel_channel_treats_only_not_found_as_deleted() -> None:
    """Verify that a gone channel resolves to None while failures propagate."""

    class _Guild:
        def get_channel(self, channel_id: int) -> None:
            return None

        async def fetch_channel(self, channel_id: int) -> None:
            raise aiohttp.ServerDisconnectedError()

    with pytest.raises(aiohttp.ServerDisconnectedError):
        await RankRoleCog._panel_channel(_Guild(), 100)


async def test_panel_channel_returns_none_for_a_deleted_channel() -> None:
    """Verify that a genuinely deleted channel resolves to None."""

    class _Guild:
        def get_channel(self, channel_id: int) -> None:
            return None

        async def fetch_channel(self, channel_id: int) -> None:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "")

    assert await RankRoleCog._panel_channel(_Guild(), 100) is None


@pytest.mark.usefixtures("backend_database")
async def test_sync_reports_a_dropped_connection_as_sync_failed() -> None:
    """Verify that a transport failure during the edit is reported."""
    gold = _FakeRole(10, 5)
    guild = _FakeGuild({10: gold}, _FakeRole(50, 50))
    member = _FakeMember([_FakeRole(1, 0, everyone=True)])
    member.error = aiohttp.ServerDisconnectedError()
    cog = _sync_cog({"gold": 10}, {10: "gold"})

    key = await cog._sync_member(guild, member, "gold")

    assert key == "rankrole-sync-failed"


@pytest.mark.usefixtures("backend_database")
async def test_sync_reports_a_socket_error_as_sync_failed() -> None:
    """Verify that a low-level OS error during the edit is reported."""
    gold = _FakeRole(10, 5)
    guild = _FakeGuild({10: gold}, _FakeRole(50, 50))
    member = _FakeMember([_FakeRole(1, 0, everyone=True)])
    member.error = OSError("network unreachable")
    cog = _sync_cog({"gold": 10}, {10: "gold"})

    key = await cog._sync_member(guild, member, "gold")

    assert key == "rankrole-sync-failed"


@pytest.mark.usefixtures("backend_database")
async def test_reset_tier_restores_the_mapping_on_a_database_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a database blip after the delete still restores the tier."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRole.create(guild_id=7, tier_group="silver", role_id=11)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    cog = _panel_cog(_FakeChannel(message=_FakeMessage(200)))
    guild = SimpleNamespace(id=7, get_role=lambda role_id: None)

    async def failing_refresh(interaction: object) -> None:
        raise ConnectionError("database went away")

    monkeypatch.setattr(cog, "refresh_panel", failing_refresh)

    problem = await cog.reset_all(_panel_interaction(), guild, "gold")

    assert problem == "rankrole-panel-blocked"
    restored = await RankRole.get(guild_id=7, tier_group="gold")
    assert restored.role_id == 10
    assert await RankRole.filter(guild_id=7).count() == 2


@pytest.mark.usefixtures("backend_database")
async def test_publish_withdraws_the_panel_when_it_cannot_be_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that an untracked panel is withdrawn instead of being duplicated."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100)
    channel = _FakeChannel()
    cog = _panel_cog(channel)
    posted = _FakeMessage(555)
    channel.send = lambda **kwargs: _return(posted)  # type: ignore[method-assign]

    async def failing_save(*args: object, **kwargs: object) -> None:
        raise ConnectionError("database went away")

    monkeypatch.setattr(RankRolePanel, "save", failing_save)

    assert await cog.publish_panel(_panel_interaction()) == "rankrole-panel-blocked"
    assert posted.deleted is True


@pytest.mark.usefixtures("backend_database")
async def test_refresh_reports_blocked_on_a_database_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a database failure while reading settings is reported."""

    async def failing_get(*args: object, **kwargs: object) -> None:
        raise ConnectionError("database went away")

    monkeypatch.setattr(RankRolePanel, "get_or_none", failing_get)
    cog = _panel_cog(_FakeChannel())

    assert await cog.refresh_panel(_panel_interaction()) == "rankrole-panel-blocked"


@pytest.mark.usefixtures("backend_database")
async def test_reset_tier_reports_a_lost_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a failed restore is reported as a lost mapping."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRole.create(guild_id=7, tier_group="silver", role_id=11)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    cog = _unreadable_panel_cog()
    guild = SimpleNamespace(id=7, get_role=lambda role_id: None)

    async def failing_create(*args: object, **kwargs: object) -> None:
        raise ConnectionError("database went away")

    monkeypatch.setattr(RankRole, "create", failing_create)

    problem = await cog.reset_all(_panel_interaction(), guild, "gold")

    assert problem == "rankrole-mapping-lost"


@pytest.mark.usefixtures("backend_database")
async def test_publish_reports_an_untracked_panel_when_withdrawal_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a panel which can be neither recorded nor removed is flagged."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100)
    channel = _FakeChannel()
    cog = _panel_cog(channel)
    posted = _FakeMessage(
        555,
        delete_error=discord.Forbidden(SimpleNamespace(status=403, reason="No"), ""),
    )
    channel.send = lambda **kwargs: _return(posted)  # type: ignore[method-assign]

    async def failing_save(*args: object, **kwargs: object) -> None:
        raise ConnectionError("database went away")

    monkeypatch.setattr(RankRolePanel, "save", failing_save)

    assert await cog.publish_panel(_panel_interaction()) == "rankrole-panel-untracked"


@pytest.mark.usefixtures("backend_database")
async def test_publish_records_the_panel_when_the_first_save_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a single database blip is retried instead of withdrawing."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100)
    channel = _FakeChannel()
    cog = _panel_cog(channel)
    attempts: list[int] = []
    original = RankRolePanel.save

    async def flaky_save(panel: RankRolePanel, **kwargs: object) -> None:
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("database went away")
        await original(panel, **kwargs)

    monkeypatch.setattr(RankRolePanel, "save", flaky_save)

    assert await cog.publish_panel(_panel_interaction()) is None
    assert len(attempts) == 2
    panel = await RankRolePanel.get(guild_id=7)
    assert panel.message_id == 555


@pytest.mark.usefixtures("backend_database")
async def test_reset_failure_still_redraws_the_dashboard() -> None:
    """Verify that a blocked reset refreshes the dashboard before returning."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    cog = _unreadable_panel_cog()
    guild = SimpleNamespace(id=7, get_role=lambda role_id: None)
    interaction = _panel_interaction()

    problem = await cog.reset_all(interaction, guild, "all")

    assert problem == "rankrole-panel-blocked"
    assert interaction.edited


@pytest.mark.usefixtures("backend_database")
async def test_reset_tier_retries_a_restore_that_blips_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a single database blip does not cost the tier mapping."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRole.create(guild_id=7, tier_group="silver", role_id=11)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    cog = _unreadable_panel_cog()
    guild = SimpleNamespace(id=7, get_role=lambda role_id: None)
    attempts: list[int] = []
    original = RankRole.create

    async def flaky_create(*args: object, **kwargs: object) -> object:
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("database went away")
        return await original(*args, **kwargs)

    monkeypatch.setattr(RankRole, "create", flaky_create)

    problem = await cog.reset_all(_panel_interaction(), guild, "gold")

    assert problem == "rankrole-panel-blocked"
    assert len(attempts) == 2
    restored = await RankRole.get(guild_id=7, tier_group="gold")
    assert restored.role_id == 10


@pytest.mark.usefixtures("backend_database")
async def test_channel_picker_reports_a_database_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a failed channel write is reported and keeps the old channel."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100)
    cog = _panel_cog(_FakeChannel())
    guild = SimpleNamespace(id=7, get_role=lambda role_id: None)
    picker = rankrole._ChannelPicker(cog, _panel_interaction(), guild)
    picker._values = [SimpleNamespace(id=999)]
    interaction = _RecordingInteraction(_FakeMember([]), guild)

    async def failing_upsert(*args: object, **kwargs: object) -> None:
        raise ConnectionError("database went away")

    monkeypatch.setattr(RankRolePanel, "update_or_create", failing_upsert)

    await picker.callback(interaction)

    panel = await RankRolePanel.get(guild_id=7)
    assert panel.channel_id == 100
    assert interaction.followups[0]["embed"].description == TEST_TRANSLATOR.text(
        "en-US", "error-command-failed"
    )


@pytest.mark.usefixtures("backend_database")
async def test_reset_all_reports_a_database_error_while_deleting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a failed mapping delete is reported, not raised."""
    await RankRole.create(guild_id=7, tier_group="gold", role_id=10)
    await RankRolePanel.create(guild_id=7, channel_id=100, message_id=200)
    cog = _panel_cog(_FakeChannel(message=_FakeMessage(200)))
    guild = SimpleNamespace(id=7, get_role=lambda role_id: None)

    async def failing_delete(*args: object, **kwargs: object) -> None:
        raise ConnectionError("database went away")

    monkeypatch.setattr(QuerySet, "delete", failing_delete)

    problem = await cog.reset_all(_panel_interaction(), guild, "all")

    assert problem == "error-command-failed"
