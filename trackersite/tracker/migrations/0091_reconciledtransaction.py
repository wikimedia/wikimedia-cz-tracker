# -*- coding: utf-8 -*-
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0090_deprecate_trackerprofile_bank_account'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReconciledTransaction',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, null=True, verbose_name='created')),
                ('transaction_id', models.CharField(max_length=64, unique=True, verbose_name='Fio transaction ID')),
                ('account', models.CharField(blank=True, max_length=50, verbose_name='account')),
                ('date', models.DateField(blank=True, null=True, verbose_name='date')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='amount')),
                ('reference', models.CharField(blank=True, max_length=255, verbose_name='payment reference')),
                ('reconciled_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='reconciled at')),
                ('expediture', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reconciled_transactions', to='tracker.Expediture', verbose_name='expediture')),
            ],
            options={
                'verbose_name': 'Reconciled transaction',
                'verbose_name_plural': 'Reconciled transactions',
            },
        ),
    ]
