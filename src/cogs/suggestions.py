"""Discord suggestion submission, following, and owner-only review commands."""

from __future__ import annotations

from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from ..bot import BotFraggBot
from ..models import Suggestion
from ..services.suggestions import (
    create_suggestion,
    delete_suggestion,
    follow_suggestion,
    record_suggestion_delivery,
    review_suggestion,
    unfollow_suggestion,
)
from ..views.ui import embed, error, translated


class SuggestionsCog(commands.Cog):
    """Own the public suggestion workflow and its review notifications."""

    suggestions = app_commands.Group(
        name=app_commands.locale_str("suggestion", key="group-suggestion-name"),
        description=app_commands.locale_str(
            "Track or review feature suggestions",
            key="group-suggestion-description",
        ),
    )

    def __init__(self, bot: BotFraggBot) -> None:
        """Bind suggestion commands to the running bot."""
        self.bot = bot

    @app_commands.command(
        name=app_commands.locale_str("suggest", key="command-suggest-name"),
        description=app_commands.locale_str(
            "Suggest a feature for BotFragg", key="command-suggest-description"
        ),
    )
    @app_commands.rename(
        suggestion=app_commands.locale_str(
            "suggestion", key="option-suggest-suggestion-name"
        )
    )
    @app_commands.describe(
        suggestion=app_commands.locale_str(
            "Describe the feature you want to suggest",
            key="option-suggest-suggestion-description",
        )
    )
    @app_commands.guild_only()
    async def suggest(
        self,
        interaction: discord.Interaction,
        suggestion: app_commands.Range[str, 1, 1000],
    ) -> None:
        """Persist a feature suggestion and publish it to the configured log channel."""
        await interaction.response.defer(thinking=True)
        channel_id = self.bot.config.suggestion_log_channel_id
        if not channel_id:
            await error(interaction, "suggestions-not-configured")
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                await error(interaction, "suggestion-channel-unavailable")
                return
        if not isinstance(channel, discord.abc.Messageable):
            await error(interaction, "suggestion-channel-not-messageable")
            return
        record = await create_suggestion(interaction.user.id, suggestion, channel_id)
        if record is None:
            await error(interaction, "error-command-failed")
            return
        log_locale = interaction.guild_locale or interaction.locale
        card = embed(
            f"> {suggestion}",
            title=self.bot.translator.text(
                log_locale, "suggestion-title", number=record.id
            ),
        )
        card.set_author(
            name=str(interaction.user), icon_url=interaction.user.display_avatar.url
        )
        card.set_footer(
            text=interaction.guild.name
            if interaction.guild
            else translated(interaction, "common-direct-message")
        )
        try:
            message = await channel.send(embed=card)
        except discord.HTTPException:
            await delete_suggestion(record.id)
            await error(interaction, "suggestion-delivery-failed")
            return
        delivered = await record_suggestion_delivery(record, message.id)
        if delivered is not None and delivered.status != "pending":
            await self._update_suggestion_log(delivered)
        await interaction.followup.send(
            embed=embed(
                translated(
                    interaction,
                    "suggestion-submitted",
                    number=record.id,
                )
            )
        )

    @suggestions.command(
        name=app_commands.locale_str("track", key="command-suggestion-track-name"),
        description=app_commands.locale_str(
            "Follow a feature suggestion",
            key="command-suggestion-track-description",
        ),
    )
    @app_commands.rename(
        id=app_commands.locale_str("id", key="option-suggestion-track-id-name")
    )
    @app_commands.describe(
        id=app_commands.locale_str(
            "ID of the suggestion to follow",
            key="option-suggestion-track-id-description",
        )
    )
    @app_commands.guild_only()
    async def track(self, interaction: discord.Interaction, id: int) -> None:
        """Follow a pending suggestion or privately show its existing review."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        created = await follow_suggestion(id, interaction.user.id)
        if created is None:
            await error(interaction, "suggestion-not-found", number=id)
            return
        if isinstance(created, Suggestion):
            await interaction.followup.send(
                embed=self._review_card(created, interaction.locale), ephemeral=True
            )
            return
        message = (
            self.bot.translator.text(
                interaction.locale, "suggestion-following", number=id
            )
            if created
            else self.bot.translator.text(
                interaction.locale, "suggestion-already-following", number=id
            )
        )
        await interaction.followup.send(embed=embed(message), ephemeral=True)

    @suggestions.command(
        name=app_commands.locale_str("untrack", key="command-suggestion-untrack-name"),
        description=app_commands.locale_str(
            "Stop following a feature suggestion",
            key="command-suggestion-untrack-description",
        ),
    )
    @app_commands.rename(
        id=app_commands.locale_str("id", key="option-suggestion-untrack-id-name")
    )
    @app_commands.describe(
        id=app_commands.locale_str(
            "ID of the suggestion to stop following",
            key="option-suggestion-untrack-id-description",
        )
    )
    @app_commands.guild_only()
    async def untrack(self, interaction: discord.Interaction, id: int) -> None:
        """Remove the caller's follow from another user's suggestion."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        result = await unfollow_suggestion(id, interaction.user.id)
        if result == "missing":
            await error(interaction, "suggestion-not-found", number=id)
            return
        if result == "own":
            await error(interaction, "suggestion-cannot-unfollow-own")
            return
        await interaction.followup.send(
            embed=embed(
                self.bot.translator.text(
                    interaction.locale, "suggestion-unfollowed", number=id
                )
                if result == "removed"
                else self.bot.translator.text(
                    interaction.locale, "suggestion-not-following", number=id
                )
            ),
            ephemeral=True,
        )

    @suggestions.command(
        name="approve",
        description="Approve a feature suggestion",
        extras={"owner_only": True},
    )
    @app_commands.guild_only()
    async def approve(
        self,
        interaction: discord.Interaction,
        id: int,
        reason: app_commands.Range[str, 1, 1000],
    ) -> None:
        """Submit an owner-only approval review for the selected suggestion."""
        await self._review_suggestion(interaction, id, reason, "approved")

    @suggestions.command(
        name="deny",
        description="Deny a feature suggestion",
        extras={"owner_only": True},
    )
    @app_commands.guild_only()
    async def deny(
        self,
        interaction: discord.Interaction,
        id: int,
        reason: app_commands.Range[str, 1, 1000],
    ) -> None:
        """Submit an owner-only denial review for the selected suggestion."""
        await self._review_suggestion(interaction, id, reason, "denied")

    async def _review_suggestion(
        self,
        interaction: discord.Interaction,
        id: int,
        reason: str,
        status: Literal["approved", "denied"],
    ) -> None:
        """Authorize a review, update its record, and notify its followers."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not await self.bot.is_owner(interaction.user):
            await error(interaction, "suggestion-owner-only")
            return
        try:
            result = await review_suggestion(id, status, reason)
        except ValueError as exc:
            await interaction.followup.send(embed=embed(str(exc)), ephemeral=True)
            return
        if result is None:
            await interaction.followup.send(
                embed=embed(
                    f"Suggestion **#{id}** does not exist or has already been reviewed."
                ),
                ephemeral=True,
            )
            return
        suggestion, recipient_ids = result
        await self._update_suggestion_log(suggestion)
        for user_id in recipient_ids:
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                user_locale = getattr(user, "locale", discord.Locale.american_english)
                await user.send(embed=self._review_card(suggestion, user_locale))
            except discord.HTTPException:
                continue
        await interaction.followup.send(
            embed=embed(f"Suggestion **#{id}** has been **{status}**."),
            ephemeral=True,
        )

    def _review_card(
        self, suggestion: Suggestion, locale: discord.Locale
    ) -> discord.Embed:
        """Render the localized review shared by follower DMs and completed tracking."""
        return embed(
            self.bot.translator.text(
                locale,
                "suggestion-review-dm",
                number=suggestion.id,
                status=self.bot.translator.text(
                    locale, f"suggestion-status-{suggestion.status}"
                ),
                reason=suggestion.reason,
                content=suggestion.content,
            ),
            title=self.bot.translator.text(locale, "suggestion-update-title"),
        )

    async def _update_suggestion_log(self, suggestion: Suggestion) -> None:
        """Edit the original suggestion post with the final status and review reason."""
        if not suggestion.log_channel_id or not suggestion.log_message_id:
            return
        try:
            channel = self.bot.get_channel(
                suggestion.log_channel_id
            ) or await self.bot.fetch_channel(suggestion.log_channel_id)
            if isinstance(channel, discord.abc.Messageable):
                message = await channel.fetch_message(suggestion.log_message_id)
                status = suggestion.status.title()
                await message.edit(
                    embed=embed(
                        f"> {suggestion.content}\n\n"
                        f"**{status} reason:** {suggestion.reason}",
                        title=f"Suggestion #{suggestion.id} — {status}",
                    )
                )
        except discord.HTTPException:
            return


async def setup(bot: BotFraggBot) -> None:
    """Register suggestion commands and review handlers."""
    await bot.add_cog(SuggestionsCog(bot))
