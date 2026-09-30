"""Create the initial user, account, alert, and suggestion tables."""

from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    """Define the initial persisted Botfragg schema and ownership relations."""

    initial = True

    operations = [
        ops.CreateModel(
            name='User',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('current_account_id', fields.CharField(null=True, max_length=64)),
                ('daily_shop_enabled', fields.BooleanField(default=False)),
                ('hide_ign', fields.BooleanField(default=False)),
                ('others_can_view_shop', fields.BooleanField(default=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('updated_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
            ],
            options={'table': 'user', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='Account',
            fields=[
                ('puuid', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=64)),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', db_constraint=True, to_field='id', related_name='accounts', on_delete=OnDelete.CASCADE)),
                ('username', fields.CharField(max_length=128)),
                ('region', fields.CharField(null=True, max_length=16)),
                ('auth_blob', fields.TextField(null=True, unique=False)),
                ('auth_version', fields.IntField(default=0)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('updated_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
            ],
            options={'table': 'account', 'app': 'models', 'pk_attr': 'puuid'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='Alert',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('account', fields.ForeignKeyField('models.Account', source_field='account_id', db_constraint=True, to_field='puuid', related_name='alerts', on_delete=OnDelete.CASCADE)),
                ('skin_uuid', fields.UUIDField()),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'alert', 'app': 'models', 'unique_together': (('account', 'skin_uuid'),), 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
