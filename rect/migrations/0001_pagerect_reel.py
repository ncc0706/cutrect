# -*- coding: utf-8 -*-
# Generated by Django 1.11.8 on 2018-01-09 06:44
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rect', 'sequence'),
    ]

    operations = [
        migrations.AddField(
            model_name='pagerect',
            name='reel',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='pagerects', to='rect.Reel'),
        ),
    ]