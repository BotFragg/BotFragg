"""Store rank role panel destinations and per-tier role mappings."""

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    """Create the rank role panel and mapping tables."""

    dependencies = [("models", "0011_add_alert_notifications")]

    initial = False

    operations = [
        ops.CreateModel(
            name="RankRolePanel",
            fields=[
                (
                    "guild_id",
                    fields.BigIntField(
                        generated=True,
                        primary_key=True,
                        unique=True,
                        db_index=True,
                    ),
                ),
                ("channel_id", fields.BigIntField(null=True)),
                ("message_id", fields.BigIntField(null=True)),
                (
                    "updated_at",
                    fields.DatetimeField(auto_now=True, auto_now_add=False),
                ),
            ],
            options={
                "table": "rankrolepanel",
                "app": "models",
                "pk_attr": "guild_id",
                "table_description": (
                    "Record where one guild hosts its rank role panel and which "
                    "message is live."
                ),
            },
            bases=["Model"],
        ),
        ops.CreateModel(
            name="RankRole",
            fields=[
                (
                    "id",
                    fields.IntField(
                        generated=True,
                        primary_key=True,
                        unique=True,
                        db_index=True,
                    ),
                ),
                ("guild_id", fields.BigIntField()),
                ("tier_group", fields.CharField(max_length=12)),
                ("role_id", fields.BigIntField()),
            ],
            options={
                "table": "rankrole",
                "app": "models",
                "unique_together": (("guild_id", "tier_group"),),
                "pk_attr": "id",
                "table_description": (
                    "Map one rank tier group to the role a guild awards for it."
                ),
            },
            bases=["Model"],
        ),
    ]
