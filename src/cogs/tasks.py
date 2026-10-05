"""Background loops for daily alerts, catalog refresh, and Discord log delivery."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import UTC, time

import discord
from discord.ext import commands, tasks

from ..bot import BotFraggBot
from ..models import Account, Alert, User
from ..monitoring import StructuredFormatter, transaction
from ..services.accounts import run_daily_alerts
from ..services.shop import Offer, ShopData
from ..views import OwnedActionButton, timestamp
from .valorant._ui import embed, view
from .valorant.shop import add_skin_selector, offer_cards

log = logging.getLogger(__name__)


class DiscordLogHandler(logging.Handler):
    """Buffer privacy-filtered structured log lines for periodic Discord delivery."""

    def __init__(self) -> None:
        """Create a bounded log buffer using BotFragg's privacy-aware formatter."""
        super().__init__()
        self.messages: deque[str] = deque(maxlen=1000)
        self.setFormatter(StructuredFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        """Format a log record into the buffer or delegate failures to logging."""
        try:
            self.messages.append(self.format(record))
        except Exception:
            self.handleError(record)


class TasksCog(commands.Cog):
    """Own periodic application jobs and stop them cleanly when unloaded."""

    def __init__(self, bot: BotFraggBot) -> None:
        """Set job intervals from settings and prepare the optional log handler."""
        self.bot = bot
        self.version_refresh.change_interval(
            minutes=bot.config.user_agent_interval_minutes
        )
        self.catalog_refresh.change_interval(
            minutes=bot.config.game_version_interval_minutes
        )
        self.daily_alerts.change_interval(time=bot.config.alert_time_utc)
        self.discord_log_handler = DiscordLogHandler()
        self.log_flush.change_interval(seconds=bot.config.log_flush_interval_seconds)

    async def cog_load(self) -> None:
        """Start background loops and attach the log handler when configured."""
        self.daily_alerts.start()
        self.version_refresh.start()
        self.catalog_refresh.start()
        if self.bot.config.log_channel_id:
            logging.getLogger().addHandler(self.discord_log_handler)
            self.log_flush.start()

    async def cog_unload(self) -> None:
        """Cancel and await all active loops, then detach the root log handler."""
        loops = (
            self.daily_alerts,
            self.version_refresh,
            self.catalog_refresh,
            self.log_flush,
        )
        loop_tasks = [loop.get_task() for loop in loops]
        for loop in loops:
            loop.cancel()
        running = [
            task
            for task in loop_tasks
            if task is not None and task is not asyncio.current_task()
        ]
        if running:
            await asyncio.gather(*running, return_exceptions=True)
        logging.getLogger().removeHandler(self.discord_log_handler)

    @tasks.loop(time=time(0, 0, 10, tzinfo=UTC))
    async def daily_alerts(self) -> None:
        """Run the daily shop and skin-alert job inside a monitoring transaction."""
        with transaction("botfragg.job.daily_alerts", "botfragg.job"):
            await self.run_alerts()

    @daily_alerts.before_loop
    async def configure_daily_alerts(self) -> None:
        """Wait for Discord readiness before starting daily alert delivery."""
        await self.bot.wait_until_ready()

    async def run_alerts(self) -> dict[str, int]:
        """Process eligible users' shops and return counts for the completed run."""
        summary = await run_daily_alerts(
            self.bot.shop,
            alert_concurrency=self.bot.config.alert_concurrency,
            delay_between_alerts_seconds=self.bot.config.delay_between_alerts_seconds,
            dry_run=False,
            on_shop=self._deliver_daily_alert_result,
            on_credentials_expired=self._credentials_expired,
        )
        log.info("Daily alert run completed", extra=summary)
        return summary

    async def _deliver_daily_alert_result(
        self,
        user_id: int,
        user: User | None,
        account: Account,
        shop: ShopData,
        matches: list[tuple[Alert, Offer]],
        send_daily_shop: bool,
    ) -> None:
        """Deliver each matching skin alert and the user's optional daily shop."""
        for alert, offer in matches:
            await self._send_alert(user_id, alert, offer)
        if send_daily_shop and user:
            await self._send_daily_shop(user, account, shop)

    async def _send_alert(self, user_id: int, alert: Alert, offer: Offer) -> None:
        """DM a matching skin alert with a control owned by the recipient."""
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            locale = discord.Locale.american_english
            skin_name = self.bot.emoji_service.skin_name(
                offer.skin.name_for(locale)
                or self.bot.translator.text(locale, "alert-unknown-skin"),
                offer.skin.tier_uuid,
            )
            card = embed(
                self.bot.translator.text(
                    locale,
                    "alert-notification",
                    skin=skin_name,
                    username=alert.account.username,
                    timestamp=timestamp(offer.expires),
                )
            )
            if offer.skin.icon:
                card.set_thumbnail(url=offer.skin.icon)
            controls = view(
                OwnedActionButton(
                    "remove_alert",
                    user_id,
                    str(alert.id),
                    label=self.bot.translator.text(locale, "alerts-remove-button"),
                    style=discord.ButtonStyle.danger,
                )
            )
            await user.send(embed=card, view=controls)
        except discord.HTTPException:
            log.warning("Could not deliver alert notification")

    async def _send_daily_shop(
        self, user: User, account: Account, shop: ShopData
    ) -> None:
        """DM the selected account's daily shop as a set of offer embeds."""
        try:
            target = self.bot.get_user(user.id) or await self.bot.fetch_user(user.id)
            locale = discord.Locale.american_english
            vp = await self.bot.emoji_service.currency("vp") or "VP"
            cards = offer_cards(
                self.bot.translator.text(
                    locale,
                    "shop-daily-header",
                    username=account.username,
                    timestamp=timestamp(shop.expires),
                ),
                shop.offers,
                vp,
                link_item_image=self.bot.config.link_item_image,
                unknown_skin_name=self.bot.translator.text(locale, "common-unknown"),
                emoji_service=self.bot.emoji_service,
                locale=locale,
            )
            controls = discord.ui.View(timeout=None)
            add_skin_selector(
                controls,
                user.id,
                shop.offers,
                shop.expires,
                self.bot.emoji_service,
                self.bot.translator,
                locale,
            )
            await target.send(
                embeds=cards, view=controls if controls.children else None
            )
        except discord.HTTPException:
            log.warning("Could not deliver daily shop notification")

    async def _credentials_expired(self, user_id: int) -> None:
        """Tell a user privately when their Riot login must be renewed."""
        try:
            target = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            locale = discord.Locale.american_english
            await target.send(
                embed=embed(
                    self.bot.translator.text(locale, "alerts-credentials-expired")
                )
            )
        except discord.HTTPException:
            log.warning("Could not notify user about expired Riot credentials")

    @tasks.loop(minutes=15)
    async def version_refresh(self) -> None:
        """Refresh the Riot client version used in authenticated API requests."""
        with transaction("botfragg.job.version_refresh", "botfragg.job"):
            await self.bot.auth.refresh_version()

    @version_refresh.before_loop
    async def before_version_refresh(self) -> None:
        """Wait for Discord readiness before the first version refresh."""
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=15)
    async def catalog_refresh(self) -> None:
        """Refresh the VALORANT catalog when its upstream version changes."""
        with transaction("botfragg.job.catalog_refresh", "botfragg.job"):
            await self.bot.catalog.refresh(check_version=True)

    @catalog_refresh.before_loop
    async def before_catalog_refresh(self) -> None:
        """Wait for Discord readiness before the first catalog refresh."""
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=10)
    async def log_flush(self) -> None:
        """Send buffered log lines to Discord and requeue them after HTTP failures."""
        if not self.discord_log_handler.messages or not self.bot.config.log_channel_id:
            return
        lines: list[str] = []
        length = 0
        while self.discord_log_handler.messages:
            line = self.discord_log_handler.messages[0]
            if lines and length + len(line) + 1 > 3500:
                break
            lines.append(self.discord_log_handler.messages.popleft())
            length += len(line) + 1
        try:
            channel = self.bot.get_channel(
                self.bot.config.log_channel_id
            ) or await self.bot.fetch_channel(self.bot.config.log_channel_id)
            await channel.send(
                embed=embed(
                    "```\n" + "\n".join(lines) + "\n```",
                    title="Bot log",
                    colour=0x202225,
                )
            )
        except discord.HTTPException:
            for line in reversed(lines):
                self.discord_log_handler.messages.appendleft(line)

    @log_flush.before_loop
    async def before_log_flush(self) -> None:
        """Wait for Discord readiness before sending buffered logs."""
        await self.bot.wait_until_ready()


async def setup(bot: BotFraggBot) -> None:
    """Register the background-task cog with the bot."""
    await bot.add_cog(TasksCog(bot))
