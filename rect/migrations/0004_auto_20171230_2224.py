# -*- coding: utf-8 -*-
# Generated by Django 1.11.8 on 2017-12-30 14:24
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('jwt_auth', '0001_initial'),
        ('rect', '0003_auto_20171230_1431'),
    ]

    operations = [
        migrations.CreateModel(
            name='ActivityLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('log', models.CharField(default='', max_length=128, verbose_name='记录')),
                ('object_type', models.CharField(max_length=32, verbose_name='对象类型')),
                ('object_pk', models.CharField(max_length=64, verbose_name='对象主键')),
                ('action', models.CharField(max_length=16, verbose_name='行为')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
        ),
        migrations.AlterModelOptions(
            name='cctask',
            options={'ordering': ('priority', 'status'), 'verbose_name': '切分任务', 'verbose_name_plural': '切分任务管理'},
        ),
        migrations.AlterModelOptions(
            name='classifytask',
            options={'ordering': ('priority', 'status'), 'verbose_name': '切分任务', 'verbose_name_plural': '切分任务管理'},
        ),
        migrations.AlterModelOptions(
            name='pagetask',
            options={'ordering': ('priority', 'status'), 'verbose_name': '切分任务', 'verbose_name_plural': '切分任务管理'},
        ),
        migrations.AddField(
            model_name='cctask',
            name='priority',
            field=models.PositiveSmallIntegerField(choices=[(1, '低'), (3, '中'), (5, '高'), (7, '最高')], default=3, verbose_name='任务状态'),
        ),
        migrations.AddField(
            model_name='classifytask',
            name='priority',
            field=models.PositiveSmallIntegerField(choices=[(1, '低'), (3, '中'), (5, '高'), (7, '最高')], default=3, verbose_name='任务状态'),
        ),
        migrations.AddField(
            model_name='pagetask',
            name='priority',
            field=models.PositiveSmallIntegerField(choices=[(1, '低'), (3, '中'), (5, '高'), (7, '最高')], default=3, verbose_name='任务状态'),
        ),
        migrations.AlterField(
            model_name='cctask',
            name='status',
            field=models.PositiveSmallIntegerField(choices=[(0, '未领取'), (1, '已过期'), (2, '已放弃'), (4, '处理中'), (5, '已完成'), (6, '已作废')], db_index=True, default=0, verbose_name='任务状态'),
        ),
        migrations.AlterField(
            model_name='classifytask',
            name='owner',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='classify_tasks', to='jwt_auth.Staff'),
        ),
        migrations.AlterField(
            model_name='classifytask',
            name='status',
            field=models.PositiveSmallIntegerField(choices=[(0, '未领取'), (1, '已过期'), (2, '已放弃'), (4, '处理中'), (5, '已完成'), (6, '已作废')], db_index=True, default=0, verbose_name='任务状态'),
        ),
        migrations.AlterField(
            model_name='pagetask',
            name='status',
            field=models.PositiveSmallIntegerField(choices=[(0, '未领取'), (1, '已过期'), (2, '已放弃'), (4, '处理中'), (5, '已完成'), (6, '已作废')], db_index=True, default=0, verbose_name='任务状态'),
        ),
        migrations.AddIndex(
            model_name='pagetask',
            index=models.Index(fields=['priority', 'status'], name='rect_pageta_priorit_7b8c8b_idx'),
        ),
        migrations.AddIndex(
            model_name='classifytask',
            index=models.Index(fields=['priority', 'status'], name='rect_classi_priorit_052a51_idx'),
        ),
        migrations.AddIndex(
            model_name='cctask',
            index=models.Index(fields=['priority', 'status'], name='rect_cctask_priorit_a3febe_idx'),
        ),
        migrations.AddField(
            model_name='activitylog',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='activities', to='jwt_auth.Staff'),
        ),
    ]
