"""Remove the suggestion and suggestion-follower tables."""

from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    """Drop suggestion records now that suggestions are handled in Discord forums."""

    dependencies = [("models", "0008_add_profile_sharing")]

    initial = False

    operations = [
        ops.DeleteModel("SuggestionFollower"),
        ops.DeleteModel("Suggestion"),
    ]
