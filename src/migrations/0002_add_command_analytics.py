"""Add persistent command invocation analytics."""

from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    """Add the nullable Discord scope fields used by command statistics."""

    dependencies = [('models', '0001_initial')]

    initial = False

    operations = [
        ops.CreateModel(
            name='CommandInvocation',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('command', fields.CharField(max_length=256)),
                ('user_id', fields.BigIntField()),
                ('guild_id', fields.BigIntField(null=True)),
                ('channel_id', fields.BigIntField(null=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'commandinvocation', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
