"""Index command analytics creation time for retention."""

from tortoise import migrations
from tortoise.exceptions import OperationalError
from tortoise.indexes import Index
from tortoise.migrations import operations as ops


async def _create_index(apps, schema_editor) -> None:
    """Create the retention index unless a development schema already made it."""
    model = apps.get_model("models", "CommandInvocation")
    try:
        await schema_editor.add_index(model, Index(fields=["created_at"]))
    except OperationalError as exc:
        if "already exists" not in str(exc).lower():
            raise


async def _drop_index(apps, schema_editor) -> None:
    """Remove the retention index, tolerating a schema that never had it."""
    model = apps.get_model("models", "CommandInvocation")
    try:
        await schema_editor.remove_index(model, Index(fields=["created_at"]))
    except OperationalError as exc:
        message = str(exc).lower()
        if "no such index" not in message and "does not exist" not in message:
            raise


class Migration(migrations.Migration):
    """Speed up deletion of analytics older than the retention window."""

    dependencies = [("models", "0009_remove_suggestions")]

    initial = False

    operations = [ops.RunPython(_create_index, _drop_index)]
