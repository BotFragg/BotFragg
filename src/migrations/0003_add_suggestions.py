"""Add the suggestion and suggestion-follower tables."""

from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    """Create suggestion records and their unique follower relationship."""

    dependencies = [('models', '0002_add_command_analytics')]

    initial = False

    operations = [
        ops.CreateModel(
            name='Suggestion',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('author_id', fields.BigIntField()),
                ('content', fields.CharField(max_length=1000)),
                ('status', fields.CharField(default='pending', max_length=16)),
                ('reason', fields.TextField(null=True, unique=False)),
                ('log_channel_id', fields.BigIntField(null=True)),
                ('log_message_id', fields.BigIntField(null=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'suggestion', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='SuggestionFollower',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('suggestion', fields.ForeignKeyField('models.Suggestion', source_field='suggestion_id', db_constraint=True, to_field='id', related_name='followers', on_delete=OnDelete.CASCADE)),
                ('user_id', fields.BigIntField()),
            ],
            options={'table': 'suggestionfollower', 'app': 'models', 'unique_together': (('suggestion', 'user_id'),), 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
