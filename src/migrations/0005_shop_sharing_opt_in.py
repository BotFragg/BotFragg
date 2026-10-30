"""Make cross-user shop viewing opt-in and reset existing users to private."""

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


async def _reset_shop_sharing(apps, schema_editor) -> None:
    """Reset stored rows, which kept the old shared-by-default value."""
    user = apps.get_model("models", "User")
    await user.all().using_db(schema_editor.client).update(others_can_view_shop=False)


async def _restore_shop_sharing(apps, schema_editor) -> None:
    """Leave stored choices alone; only the schema default reverts on rollback."""


class Migration(migrations.Migration):
    """Require users to opt in before others can view their shop."""

    dependencies = [("models", "0004_add_shard_status_message")]

    initial = False

    operations = [
        ops.AlterField(
            model_name="User",
            name="others_can_view_shop",
            field=fields.BooleanField(default=False),
        ),
        ops.RunPython(_reset_shop_sharing, _restore_shop_sharing),
    ]
