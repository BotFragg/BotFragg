"""Add storage for reusing the shard-status message in each channel."""

from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    """Create the channel-to-status-message mapping table."""

    dependencies = [('models', '0003_add_suggestions')]

    initial = False

    operations = [
        ops.CreateModel(
            name='ShardStatusMessage',
            fields=[
                ('channel_id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('message_id', fields.BigIntField()),
            ],
            options={'table': 'shardstatusmessage', 'app': 'models', 'pk_attr': 'channel_id'},
            bases=['Model'],
        ),
    ]
