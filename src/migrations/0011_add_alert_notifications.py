"""Track alert notifications and the Night Market alert preference."""

from tortoise import fields, migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    """Add per-account notification markers and the Night Market toggle."""

    dependencies = [("models", "0010_index_analytics_created_at")]

    initial = False

    operations = [
        ops.CreateModel(
            name="AlertNotification",
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
                (
                    "account",
                    fields.ForeignKeyField(
                        "models.Account",
                        source_field="account_id",
                        db_constraint=True,
                        to_field="puuid",
                        related_name="alert_notifications",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ("skin_uuid", fields.UUIDField()),
                ("expires", fields.DatetimeField()),
            ],
            options={
                "table": "alertnotification",
                "app": "models",
                "unique_together": (("account", "skin_uuid"),),
                "pk_attr": "id",
                "table_description": (
                    "Record the live offer window an account was already alerted about."
                ),
            },
            bases=["Model"],
        ),
        ops.AddField(
            model_name="User",
            name="night_market_alerts_enabled",
            # SQLite cannot add a NOT NULL column without a database default.
            field=fields.BooleanField(default=True, db_default=True),
        ),
    ]
