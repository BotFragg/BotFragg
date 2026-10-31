"""Index account ownership columns and widen analytics ids."""

from tortoise import fields, migrations
from tortoise.indexes import Index
from tortoise.migrations import operations as ops


async def _widen_sequence(apps, schema_editor) -> None:
    """Widen the analytics id sequence, which ALTER COLUMN does not touch."""
    if schema_editor.DIALECT != "postgres":
        return
    await schema_editor._run_sql('ALTER SEQUENCE "commandinvocation_id_seq" AS bigint')


async def _guard_rollback(_apps, schema_editor) -> None:
    """Refuse a rollback that would put ids or the sequence back over 32 bits."""
    if schema_editor.DIALECT != "postgres":
        return
    _, rows = await schema_editor.client.execute_query(
        'SELECT (SELECT MAX("id") FROM "commandinvocation") AS max_id, '
        '(SELECT last_value FROM "commandinvocation_id_seq") AS sequence_value'
    )
    row = rows[0]
    if (row["max_id"] or 0) > 2**31 - 1 or row["sequence_value"] > 2**31 - 1:
        raise RuntimeError(
            "Cannot roll back 0006: command analytics ids no longer fit in 32 bits."
        )


class Migration(migrations.Migration):
    """Speed up per-owner lookups and stop analytics ids overflowing at 2^31."""

    dependencies = [("models", "0005_shop_sharing_opt_in")]

    initial = False

    operations = [
        ops.AddIndex(model_name="Account", index=Index(fields=["user_id"])),
        ops.AlterField(
            model_name="CommandInvocation",
            name="id",
            field=fields.BigIntField(
                generated=True, primary_key=True, unique=True, db_index=True
            ),
        ),
        ops.RunPython(_widen_sequence, _guard_rollback),
    ]
