"""Background loops for daily alerts, upstream refresh, and Discord log delivery."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import UTC, datetime, time, timedelta
from time import time as unix_time

import discord
from discord.ext import commands, tasks

from ..bot import BotFraggBot
from ..database import TRANSIENT_DATABASE_ERRORS, ping_database
from ..health import HEALTH_PATH, JobHealth, write_health
from ..models import Account, Alert, User
from ..monitoring import StructuredFormatter, transaction
from ..services.alerts import retry_lookup, run_daily_alerts
from ..services.http import DISCORD_HTTP_ERRORS, HTTPFailure
from ..services.shop import Offer, ShopData
from ..views import OwnedActionButton, timestamp
from ..views.shop import add_skin_selector, offer_cards
from ..views.ui import embed, view
from .extra import ExtraCog

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
        self.version_refresh.add_exception_type(HTTPFailure)
        self.daily_alerts.change_interval(time=bot.config.alert_time_utc)
        self.discord_log_handler = DiscordLogHandler()
        self.log_flush.change_interval(seconds=bot.config.log_flush_interval_seconds)
        now = datetime.now(UTC)
        first_alert = datetime.combine(now.date(), bot.config.alert_time_utc, UTC)
        if first_alert <= now:
            first_alert += timedelta(days=1)
        alert_grace = getattr(bot.config, "daily_alert_health_grace_seconds", 7200)
        self.job_health = {
            "daily_alerts": JobHealth(
                86400 + alert_grace, first_alert.timestamp() + alert_grace
            ),
            "version_refresh": JobHealth(
                bot.config.user_agent_interval_minutes * 60 + 300
            ),
            "log_flush": JobHealth(bot.config.log_flush_interval_seconds + 300),
        }
        self._health_problems: list[str] | None = None

    async def cog_load(self) -> None:
        """Start background loops and attach the log handler when configured."""
        HEALTH_PATH.unlink(missing_ok=True)
        self.daily_alerts.start()
        self.version_refresh.start()
        if self.bot.config.log_channel_id:
            logging.getLogger().addHandler(self.discord_log_handler)
            self.log_flush.start()
        self.health_watch.start()

    async def cog_unload(self) -> None:
        """Cancel and await all active loops, then detach the root log handler."""
        loops = (
            self.daily_alerts,
            self.version_refresh,
            self.log_flush,
            self.health_watch,
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
        HEALTH_PATH.unlink(missing_ok=True)

    @tasks.loop(time=time(0, 0, 10, tzinfo=UTC))
    async def daily_alerts(self) -> None:
        """Run the daily shop and skin-alert job inside a monitoring transaction."""
        with (
            self.job_health["daily_alerts"].track("daily_alerts"),
            transaction("botfragg.job.daily_alerts", "botfragg.job"),
        ):
            try:
                summary = await self.run_alerts()
                if summary["shop_failures"] or summary["delivery_failures"]:
                    self.job_health["daily_alerts"].failure("daily_alerts")
            except* TRANSIENT_DATABASE_ERRORS as group:
                # Clock-loop retries can execute the next scheduled day's run twice.
                self.job_health["daily_alerts"].failure("daily_alerts")
                log.warning("Daily alert run failed", exc_info=group)

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
    ) -> int:
        """Deliver matching alerts and the optional daily shop; count failed DMs."""
        try:
            # Resolve once: fetch_user is an API call per alert otherwise.
            target = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
        except DISCORD_HTTP_ERRORS:
            log.warning("Could not resolve alert recipient", exc_info=True)
            return len(matches) + bool(send_daily_shop and user)
        # One ownership recheck per account instead of one per alert.
        surviving: dict[int, Alert] = {}
        if matches:
            alert_ids = [alert.id for alert, _ in matches]
            surviving = {
                alert.id: alert
                for alert in await retry_lookup(
                    lambda: Alert.filter(
                        id__in=alert_ids,
                        account_id=account.puuid,
                        account__user_id=user_id,
                        account__created_at=account.created_at,
                    ).select_related("account")
                )
            }
        failures = 0
        for alert, offer in matches:
            current = surviving.get(alert.id)
            if current is None:
                continue
            failures += not await self._send_alert(target, current, offer)
        if send_daily_shop and user:
            failures += not await self._send_daily_shop(target, user, account, shop)
        return failures

    async def _send_alert(
        self,
        target: discord.User | discord.Member,
        alert: Alert,
        offer: Offer,
    ) -> bool:
        """DM an owner-scoped skin alert and report whether delivery succeeded."""
        try:
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
                    alert.account.user_id,
                    str(alert.id),
                    label=self.bot.translator.text(locale, "alerts-remove-button"),
                    style=discord.ButtonStyle.danger,
                )
            )
            await target.send(embed=card, view=controls)
        except DISCORD_HTTP_ERRORS:
            log.warning("Could not deliver alert notification", exc_info=True)
            return False
        return True

    async def _send_daily_shop(
        self,
        target: discord.User | discord.Member,
        user: User,
        account: Account,
        shop: ShopData,
    ) -> bool:
        """DM the selected account's daily shop and report delivery success."""
        try:
            locale = discord.Locale.american_english
            vp = await self.bot.emoji_service.currency("vp") or "VP"
        except DISCORD_HTTP_ERRORS:
            log.warning("Could not deliver daily shop notification", exc_info=True)
            return False
        current = await retry_lookup(
            account.persisted_row().select_related("user").get_or_none
        )
        if (
            current is None
            or current.user_id != user.id
            or not current.user.daily_shop_enabled
            or current.user.current_account_id != current.puuid
        ):
            return True
        account = current
        try:
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
                translator=self.bot.translator,
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
                # Discord accepts None here; its Messageable annotation omits it.
                embeds=cards,
                view=controls if controls.children else None,  # type: ignore[arg-type]
            )
        except DISCORD_HTTP_ERRORS:
            log.warning("Could not deliver daily shop notification", exc_info=True)
            return False
        return True

    async def _credentials_expired(self, user_id: int) -> int:
        """Notify a user that credentials expired and return the delivery failure count."""
        try:
            target = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            locale = discord.Locale.american_english
            await target.send(
                embed=embed(
                    self.bot.translator.text(locale, "alerts-credentials-expired")
                )
            )
        except DISCORD_HTTP_ERRORS:
            log.warning(
                "Could not notify user about expired Riot credentials", exc_info=True
            )
            return 1
        return 0

    @tasks.loop(minutes=15)
    async def version_refresh(self) -> None:
        """Refresh the Riot client version, the catalog, and the game metadata."""
        with (
            self.job_health["version_refresh"].track("version_refresh"),
            transaction("botfragg.job.version_refresh", "botfragg.job"),
        ):
            # One upstream fetch feeds both the request headers and the catalog check.
            failure: HTTPFailure | None = None
            try:
                version = await self.bot.auth.refresh_version()
            except HTTPFailure as exc:
                # The catalog has its own, looser parser; let it still run.
                failure = exc
                version = None
            self.bot.shop.prune_expired()
            await self.bot.catalog.refresh(check_version=True, version=version)
            # Warm the maps, ranks, and seasons so a profile never fetches them.
            await self.bot.catalog.refresh_game_metadata()
            if failure is not None:
                # Re-raise so the loop retries and the job is marked failed.
                raise failure

    @tasks.loop(seconds=10)
    async def log_flush(self) -> None:
        """Measure log delivery, preserving the queue after Discord failures."""
        with self.job_health["log_flush"].track("log_flush"):
            await self._flush_logs()

    async def _flush_logs(self) -> None:
        """Send buffered log lines to Discord and requeue them after delivery failures."""
        if not self.discord_log_handler.messages or not self.bot.config.log_channel_id:
            return
        lines: list[str] = []
        length = 0
        while self.discord_log_handler.messages:
            line = self.discord_log_handler.messages[0]
            if lines and length + len(line) + 1 > 3500:
                break
            self.discord_log_handler.messages.popleft()
            if len(line) > 3500:
                self.discord_log_handler.messages.appendleft(line[3500:])
                line = line[:3500]
            lines.append(line)
            length += len(line) + 1
        try:
            channel = self.bot.get_channel(
                self.bot.config.log_channel_id
            ) or await self.bot.fetch_channel(self.bot.config.log_channel_id)
            send = getattr(channel, "send", None)
            if not callable(send):
                raise TypeError("LOG_CHANNEL_ID must reference a messageable channel")
            await send(
                embed=embed(
                    "```\n" + "\n".join(lines) + "\n```",
                    title="Bot log",
                    colour=0x202225,
                )
            )
        except (*DISCORD_HTTP_ERRORS, TypeError):
            self.job_health["log_flush"].failure("log_flush")
            log.warning(
                "Could not deliver buffered logs to the log channel", exc_info=True
            )
            messages = self.discord_log_handler.messages
            room = (
                len(lines)
                if messages.maxlen is None
                else max(0, messages.maxlen - len(messages))
            )
            # Keep the newest lines when the buffer filled during the failed send.
            # Clamp the slice: room can exceed the batch and a negative start
            # would silently restore only the last line.
            for line in reversed(lines[max(0, len(lines) - room) :]):
                messages.appendleft(line)

    @tasks.loop(seconds=30)
    async def health_watch(self) -> None:
        """Publish Discord, database, and scheduled-job health for Docker and operators."""
        now = unix_time()
        jobs = {
            name: state.snapshot(
                running=loop.is_running(), failed=loop.failed(), now=now
            )
            for name, state in self.job_health.items()
            if name != "log_flush" or self.bot.config.log_channel_id
            for loop in (getattr(self, name),)
        }
        extra = self.bot.get_cog("ExtraCog")
        missing_shard_job = False
        if self.bot.config.shard_status_channel_id:
            missing_shard_job = not isinstance(extra, ExtraCog)
        if isinstance(extra, ExtraCog) and self.bot.config.shard_status_channel_id:
            jobs["shard_status"] = extra.job_health.snapshot(
                running=extra.shard_status.is_running(),
                failed=extra.shard_status.failed(),
                now=now,
            )
        problems = [name for name, state in jobs.items() if not state["healthy"]]
        if missing_shard_job:
            problems.append("shard_status")
        if (
            not self.bot.is_ready()
            or self.bot.is_closed()
            or any(shard.is_closed() for shard in self.bot.shards.values())
        ):
            problems.append("discord")
        try:
            await asyncio.wait_for(ping_database(), timeout=5)
        except Exception:
            log.warning("Database health probe failed", exc_info=True)
            problems.append("database")
        if problems != self._health_problems:
            log.log(
                logging.ERROR if problems else logging.INFO,
                "Bot health changed",
                extra={"problems": problems},
            )
            self._health_problems = problems
        write_health(
            {
                "healthy": not problems,
                "checked_at": unix_time(),
                "jobs": jobs,
                "problems": problems,
            }
        )

    @daily_alerts.before_loop
    @version_refresh.before_loop
    @log_flush.before_loop
    @health_watch.before_loop
    async def before_jobs(self) -> None:
        """Wait for Discord readiness before starting any background job."""
        await self.bot.wait_until_ready()


async def setup(bot: BotFraggBot) -> None:
    """Register the background-task cog with the bot."""
    await bot.add_cog(TasksCog(bot))
