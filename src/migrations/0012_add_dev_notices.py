"""Create persistent development maintenance and announcement notices."""

from tortoise import fields, migrations
from tortoise.indexes import Index
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    """Create the maintenance and announcement notice tables."""

    dependencies = [("models", "0011_add_alert_notifications")]

    initial = False

    operations = [
        ops.CreateModel(
            name="DevAnnouncement",
            fields=[
                (
                    "id",
                    fields.IntField(
                        generated=True, primary_key=True, unique=True, db_index=True
                    ),
                ),
                ("message", fields.TextField(unique=False)),
                ("created_by", fields.BigIntField()),
                ("created_at", fields.DatetimeField(auto_now_add=True)),
            ],
            options={
                "table": "devannouncement",
                "app": "models",
                "pk_attr": "id",
                "table_description": (
                    "Retain an operator-published announcement for private delivery."
                ),
            },
            bases=["Model"],
        ),
        ops.CreateModel(
            name="DevAnnouncementRead",
            fields=[
                (
                    "id",
                    fields.IntField(
                        generated=True, primary_key=True, unique=True, db_index=True
                    ),
                ),
                ("user_id", fields.BigIntField()),
                ("announcement_id", fields.BigIntField()),
                ("read_at", fields.DatetimeField(auto_now_add=True)),
            ],
            options={
                "table": "devannouncementread",
                "app": "models",
                "unique_together": (("user_id", "announcement_id"),),
                "indexes": [Index(fields=["user_id"])],
                "pk_attr": "id",
                "table_description": (
                    "Record that a Discord user has read a specific announcement."
                ),
            },
            bases=["Model"],
        ),
        ops.CreateModel(
            name="DevMaintenance",
            fields=[
                (
                    "id",
                    fields.BigIntField(
                        generated=True,
                        primary_key=True,
                        default=1,
                        unique=True,
                        db_index=True,
                    ),
                ),
                ("enabled", fields.BooleanField(default=False)),
                ("reason", fields.CharField(null=True, max_length=500)),
                ("updated_by", fields.BigIntField(null=True)),
                ("updated_at", fields.DatetimeField(auto_now=True)),
            ],
            options={
                "table": "devmaintenance",
                "app": "models",
                "pk_attr": "id",
                "table_description": (
                    "Store the singleton maintenance mode and its operator audit details."
                ),
            },
            bases=["Model"],
        ),
    ]
