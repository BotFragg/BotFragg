"""Record model options that earlier migrations never wrote to migration state."""

from tortoise import migrations
from tortoise.indexes import Index
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    """Keep future makemigrations diffs limited to real schema changes."""

    dependencies = [("models", "0006_index_owners_and_widen_analytics")]

    initial = False

    operations = [
        ops.AlterModelOptions(
            name="Account",
            options={
                "table": "account",
                "app": "models",
                "indexes": [Index(fields=["user_id"])],
                "pk_attr": "puuid",
                "table_description": "Store a user's Riot identity and encrypted authentication payload.",
            },
        ),
        ops.AlterModelOptions(
            name="Alert",
            options={
                "table": "alert",
                "app": "models",
                "unique_together": (("account", "skin_uuid"),),
                "pk_attr": "id",
                "table_description": "Store a skin alert belonging to one linked Riot account.",
            },
        ),
        ops.AlterModelOptions(
            name="CommandInvocation",
            options={
                "table": "commandinvocation",
                "app": "models",
                "pk_attr": "id",
                "table_description": "Store a completed command and its optional guild and channel context.",
            },
        ),
        ops.AlterModelOptions(
            name="ShardStatusMessage",
            options={
                "table": "shardstatusmessage",
                "app": "models",
                "pk_attr": "channel_id",
                "table_description": "Map each configured Discord channel to its persistent status message.",
            },
        ),
        ops.AlterModelOptions(
            name="Suggestion",
            options={
                "table": "suggestion",
                "app": "models",
                "pk_attr": "id",
                "table_description": "Store a user's submitted idea and its review and delivery state.",
            },
        ),
        ops.AlterModelOptions(
            name="SuggestionFollower",
            options={
                "table": "suggestionfollower",
                "app": "models",
                "unique_together": (("suggestion", "user_id"),),
                "pk_attr": "id",
                "table_description": "Link a Discord user to a suggestion whose review they want to follow.",
            },
        ),
        ops.AlterModelOptions(
            name="User",
            options={
                "table": "user",
                "app": "models",
                "pk_attr": "id",
                "table_description": "Store Discord preferences and the selected linked VALORANT account.",
            },
        ),
    ]
