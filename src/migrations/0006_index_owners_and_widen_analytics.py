"""Index account ownership columns and widen analytics ids."""

from tortoise import fields, migrations
from tortoise.indexes import Index
from tortoise.migrations import operations as ops


async def _widen_sequence(apps, schema_editor) -> None:
    """Widen the analytics id sequence, which ALTER COLUMN does not touch."""
    if schema_editor.DIALECT != "postgres":
        return
    await schema_editor._run_sql('ALTER SEQUENCE "commandinvocation_id_seq" AS bigint')


class Migration(migrations.Migration):
    """Speed up per-owner lookups and stop analytics ids overflowing at 2^31."""

    dependencies = [("models", "0005_shop_sharing_opt_in")]

    initial = False

    operations = [
        ops.AddIndex(model_name="Account", index=Index(fields=["user_id"])),
        ops.AddIndex(model_name="Alert", index=Index(fields=["account_id"])),
        ops.AlterField(
            model_name="CommandInvocation",
            name="id",
            field=fields.BigIntField(
                generated=True, primary_key=True, unique=True, db_index=True
            ),
        ),
        ops.RunPython(_widen_sequence, ops.RunPython.noop),
    ]
