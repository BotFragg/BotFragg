"""Add opt-in profile sharing for /profile."""

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    """Let users opt in before others can view their profile."""

    dependencies = [("models", "0007_record_model_options")]

    initial = False

    operations = [
        ops.AddField(
            model_name="User",
            name="others_can_view_profile",
            # SQLite cannot add a NOT NULL column without a database default.
            field=fields.BooleanField(default=False, db_default=False),
        ),
    ]
