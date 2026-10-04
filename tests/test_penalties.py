"""Focused tests for the private matchmaking-penalties command."""

from types import SimpleNamespace

import discord

from src.cogs.valorant.penalties import PenaltiesCog
from src.localization import BotFraggTranslator

TEST_TRANSLATOR = BotFraggTranslator()


def _interaction(user_id: int = 123) -> tuple[SimpleNamespace, list[dict[str, object]]]:
    """Build an interaction double that records embeds, views, and privacy."""
    messages: list[dict[str, object]] = []
    edits: list[dict[str, object]] = []

    class Response:
        """Capture whether an interaction response was deferred."""

        done = False

        async def defer(
            self, *, thinking: bool = False, ephemeral: bool = False
        ) -> None:
            """Accept private command defers and component update defers."""
            if thinking:
                assert ephemeral
            self.done = True

        def is_done(self) -> bool:
            """Return whether the response has already been acknowledged."""
            return self.done

    class Followup:
        """Capture private response messages."""

        async def send(self, **kwargs: object) -> None:
            """Record private messages and mirror Discord's view validation."""
            if "view" in kwargs and kwargs["view"] is None:
                raise TypeError("expected a View when the view argument is supplied")
            messages.append(kwargs)

    async def edit_original_response(
        *,
        embed: discord.Embed,
        view: discord.ui.View | None,
        allowed_mentions: discord.AllowedMentions | None = None,
    ) -> None:
        """Record the updated page for a button interaction."""
        edits.append(
            {"embed": embed, "view": view, "allowed_mentions": allowed_mentions}
        )

    interaction = SimpleNamespace(
        user=SimpleNamespace(id=user_id),
        response=Response(),
        followup=Followup(),
        edits=edits,
        edit_original_response=edit_original_response,
        client=SimpleNamespace(translator=TEST_TRANSLATOR),
        locale=discord.Locale.american_english,
    )
    return interaction, messages


def _penalties(count: int = 6) -> list[dict[str, object]]:
    """Return deterministic penalty rows for pagination tests."""
    return [
        {
            "infraction": "Queue Dodging" if index == 0 else f"Infraction {index}",
            "expires": None,
            "games_remaining": index,
            "platform_scope": "PC",
            "effects": ["queue-restriction"] if index == 0 else [],
            "warning_type": "QUEUE_DODGING" if index == 0 else None,
            "warning_tier": 2 if index == 0 else None,
        }
        for index in range(count)
    ]


async def test_penalties_command_shows_five_private_rows_and_hides_ign(
    monkeypatch,
) -> None:
    """Verify the command shows one private five-row page and respects hide_ign."""
    account = SimpleNamespace(puuid="player", username="SecretName#NA")
    selected: list[int] = []
    fetched: list[object] = []

    async def selected_account(user_id: int) -> SimpleNamespace:
        """Return the configured active Riot account."""
        selected.append(user_id)
        return account

    async def get_user(user_id: int) -> SimpleNamespace:
        """Return the user's privacy preference."""
        assert user_id == 123
        return SimpleNamespace(hide_ign=True)

    class Gameplay:
        """Return six normalized matchmaking penalties."""

        async def penalties(self, chosen: object) -> list[dict[str, object]]:
            """Record the selected account and return fixture penalties."""
            fetched.append(chosen)
            return _penalties()

    monkeypatch.setattr(
        "src.cogs.valorant.penalties.selected_account", selected_account
    )
    monkeypatch.setattr("src.cogs.valorant.penalties.get_user", get_user)
    interaction, messages = _interaction()
    cog = PenaltiesCog(
        SimpleNamespace(
            gameplay=Gameplay(),
            translator=TEST_TRANSLATOR,
            register_component=lambda *_args: None,
        )
    )

    await PenaltiesCog.penalties.callback(cog, interaction)

    assert selected == [123]
    assert fetched == [account]
    assert len(messages) == 1 and messages[0]["ephemeral"] is True
    card = messages[0]["embed"]
    assert len(card.fields) == 5
    assert [field.name for field in card.fields] == [
        "Queue Dodging",
        "Infraction 1",
        "Infraction 2",
        "Infraction 3",
        "Infraction 4",
    ]
    assert "Account" in (card.description or "")
    assert "SecretName" not in str(card.to_dict())
    assert "Queue restriction" in card.fields[0].value
    assert "QUEUE_DODGING" in card.fields[0].value
    assert card.footer.text == "Page 1 of 2"
    buttons = messages[0]["view"].children
    assert [button.action for button in buttons] == [
        "penalties_page",
        "penalties_page",
    ]
    assert [button.payload for button in buttons] == ["player,-1", "player,1"]


async def test_penalties_command_prompts_unregistered_user_to_log_in(
    monkeypatch,
) -> None:
    """Verify users without a selected Riot account get the login prompt privately."""

    async def selected_account(_user_id: int) -> None:
        """Return no active account for the unregistered user."""
        return None

    monkeypatch.setattr(
        "src.cogs.valorant.penalties.selected_account", selected_account
    )
    interaction, messages = _interaction()

    await PenaltiesCog.penalties.callback(
        PenaltiesCog(
            SimpleNamespace(
                gameplay=None,
                translator=TEST_TRANSLATOR,
                register_component=lambda *_args: None,
            )
        ),
        interaction,
    )

    assert len(messages) == 1 and messages[0]["ephemeral"] is True
    assert "/login" in messages[0]["embed"].description


async def test_penalties_command_reports_empty_results_without_pagination(
    monkeypatch,
) -> None:
    """Verify empty Riot results receive one private embed without controls."""
    account = SimpleNamespace(puuid="player", username="Player#NA")

    async def selected_account(_user_id: int) -> SimpleNamespace:
        """Return the configured active account."""
        return account

    async def get_user(_user_id: int) -> SimpleNamespace:
        """Use the normal visible account-name preference."""
        return SimpleNamespace(hide_ign=False)

    class Gameplay:
        """Return an empty Riot penalty list."""

        async def penalties(self, _account: object) -> list[dict[str, object]]:
            """Return no penalties."""
            return []

    monkeypatch.setattr(
        "src.cogs.valorant.penalties.selected_account", selected_account
    )
    monkeypatch.setattr("src.cogs.valorant.penalties.get_user", get_user)
    interaction, messages = _interaction()

    await PenaltiesCog.penalties.callback(
        PenaltiesCog(
            SimpleNamespace(
                gameplay=Gameplay(),
                translator=TEST_TRANSLATOR,
                register_component=lambda *_args: None,
            )
        ),
        interaction,
    )

    assert len(messages) == 1 and messages[0]["ephemeral"] is True
    assert (
        messages[0]["embed"].description == "No penalties were found for **Player#NA**."
    )
    assert "view" not in messages[0]


async def test_penalties_command_omits_view_for_a_single_page(monkeypatch) -> None:
    """Verify single-page results omit Discord's optional view argument."""
    account = SimpleNamespace(puuid="player", username="Player#NA")

    async def selected_account(_user_id: int) -> SimpleNamespace:
        """Return the configured active account."""
        return account

    async def get_user(_user_id: int) -> SimpleNamespace:
        """Use the normal visible account-name preference."""
        return SimpleNamespace(hide_ign=False)

    class Gameplay:
        """Return one matchmaking penalty."""

        async def penalties(self, _account: object) -> list[dict[str, object]]:
            """Return the only penalty page."""
            return _penalties(count=1)

    monkeypatch.setattr(
        "src.cogs.valorant.penalties.selected_account", selected_account
    )
    monkeypatch.setattr("src.cogs.valorant.penalties.get_user", get_user)
    interaction, messages = _interaction()

    await PenaltiesCog.penalties.callback(
        PenaltiesCog(
            SimpleNamespace(
                gameplay=Gameplay(),
                translator=TEST_TRANSLATOR,
                register_component=lambda *_args: None,
            )
        ),
        interaction,
    )

    assert len(messages) == 1
    assert len(messages[0]["embed"].fields) == 1
    assert "view" not in messages[0]


async def test_penalties_page_refetches_original_owned_account_and_edits_message(
    monkeypatch,
) -> None:
    """Verify page navigation is owner-bound and updates the original embed."""
    account = SimpleNamespace(puuid="player", username="Player#NA")
    resolved: list[tuple[int, str]] = []
    fetched: list[object] = []

    async def account_for_user(user_id: int, puuid: str) -> SimpleNamespace:
        """Return the account only after checking its owner."""
        resolved.append((user_id, puuid))
        return account

    async def get_user(_user_id: int) -> SimpleNamespace:
        """Use the normal visible account-name preference."""
        return SimpleNamespace(hide_ign=False)

    class Gameplay:
        """Return current penalty rows for the requested account."""

        async def penalties(self, chosen: object) -> list[dict[str, object]]:
            """Record the account and return six rows."""
            fetched.append(chosen)
            return _penalties()

    monkeypatch.setattr(
        "src.cogs.valorant.penalties.account_for_user", account_for_user
    )
    monkeypatch.setattr("src.cogs.valorant.penalties.get_user", get_user)
    interaction, messages = _interaction()
    cog = PenaltiesCog(
        SimpleNamespace(
            gameplay=Gameplay(),
            translator=TEST_TRANSLATOR,
            register_component=lambda *_args: None,
        )
    )

    await cog.penalties_page(interaction, "player,1")

    assert resolved == [(123, "player")]
    assert fetched == [account]
    assert messages == []
    assert len(interaction.edits) == 1
    card = interaction.edits[0]["embed"]
    assert [field.name for field in card.fields] == ["Infraction 5"]
    assert card.footer.text == "Page 2 of 2"
    assert [button.payload for button in interaction.edits[0]["view"].children] == [
        "player,0",
        "player,2",
    ]


async def test_penalties_page_rejects_an_account_owned_by_someone_else(
    monkeypatch,
) -> None:
    """Verify crafted pagination controls cannot request another user's account."""

    async def account_for_user(_user_id: int, _puuid: str) -> None:
        """Reject an account UUID that does not belong to the caller."""
        return None

    monkeypatch.setattr(
        "src.cogs.valorant.penalties.account_for_user", account_for_user
    )
    interaction, messages = _interaction()
    cog = PenaltiesCog(
        SimpleNamespace(
            gameplay=None,
            translator=TEST_TRANSLATOR,
            register_component=lambda *_args: None,
        )
    )

    await cog.penalties_page(interaction, "other-player,1")

    assert len(messages) == 1 and messages[0]["ephemeral"] is True
    assert "account is no longer available" in messages[0]["embed"].description
    assert interaction.edits == []
