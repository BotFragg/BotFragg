"""Tortoise ORM entities and database constraints for BotFragg data."""

from __future__ import annotations

from tortoise import fields
from tortoise.models import Model
from tortoise.queryset import QuerySet


class User(Model):
    """Store Discord preferences and the selected linked VALORANT account."""

    id = fields.BigIntField(primary_key=True)
    current_account_id = fields.CharField(max_length=64, null=True)
    daily_shop_enabled = fields.BooleanField(default=False)
    hide_ign = fields.BooleanField(default=False)
    others_can_view_shop = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    accounts: fields.ReverseRelation[Account]


class Account(Model):
    """Store a user's Riot identity and encrypted authentication payload."""

    def persisted_row(self) -> QuerySet[Account]:
        """Scope access to this account's original owner and creation time."""
        return Account.filter(
            puuid=self.puuid, user_id=self.user_id, created_at=self.created_at
        )

    puuid = fields.CharField(max_length=64, primary_key=True)
    user_id: int  # Tortoise creates the FK scalar alongside the relation at runtime.
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="accounts", on_delete=fields.CASCADE
    )
    username = fields.CharField(max_length=128)
    region = fields.CharField(max_length=16, null=True)
    auth_blob = fields.TextField(null=True)
    auth_version = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    alerts: fields.ReverseRelation[Alert]


class Alert(Model):
    """Store a skin alert belonging to one linked Riot account."""

    def persisted_row(self) -> QuerySet[Alert]:
        """Scope access to this alert and its account's original identity."""
        return Alert.filter(
            id=self.id,
            created_at=self.created_at,
            account_id=self.account.puuid,
            account__user_id=self.account.user_id,
            account__created_at=self.account.created_at,
        )

    id = fields.IntField(primary_key=True)
    account: fields.ForeignKeyRelation[Account] = fields.ForeignKeyField(
        "models.Account", related_name="alerts", on_delete=fields.CASCADE
    )
    skin_uuid = fields.UUIDField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        """Prevent duplicate alerts for the same account and skin."""

        unique_together = (("account", "skin_uuid"),)


class CommandInvocation(Model):
    """Store a completed command and its optional guild and channel context."""

    id = fields.IntField(primary_key=True)
    command = fields.CharField(max_length=256)
    user_id = fields.BigIntField()
    guild_id = fields.BigIntField(null=True)
    channel_id = fields.BigIntField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)


class Suggestion(Model):
    """Store a user's submitted idea and its review and delivery state."""

    id = fields.IntField(primary_key=True)
    author_id = fields.BigIntField()
    content = fields.CharField(max_length=1000)
    status = fields.CharField(max_length=16, default="pending")
    reason = fields.TextField(null=True)
    log_channel_id = fields.BigIntField(null=True)
    log_message_id = fields.BigIntField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    followers: fields.ReverseRelation[SuggestionFollower]


class SuggestionFollower(Model):
    """Link a Discord user to a suggestion whose review they want to follow."""

    id = fields.IntField(primary_key=True)
    suggestion: fields.ForeignKeyRelation[Suggestion] = fields.ForeignKeyField(
        "models.Suggestion", related_name="followers", on_delete=fields.CASCADE
    )
    user_id = fields.BigIntField()

    class Meta:
        """Allow each user to follow a suggestion at most once."""

        unique_together = (("suggestion", "user_id"),)


class ShardStatusMessage(Model):
    """Map each configured Discord channel to its persistent status message."""

    channel_id = fields.BigIntField(primary_key=True)
    message_id = fields.BigIntField()
