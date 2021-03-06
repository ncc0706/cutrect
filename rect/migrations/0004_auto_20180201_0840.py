# Generated by Django 2.0 on 2018-02-01 00:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rect', '0003_auto_20180128_1428'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='page',
            name='s3_uri',
        ),
        migrations.AddField(
            model_name='page',
            name='envelop_no',
            field=models.SmallIntegerField(default=0, verbose_name='函序号（第几）'),
        ),
        migrations.AddField(
            model_name='page',
            name='s3_id',
            field=models.CharField(default='', max_length=128, verbose_name='图片路径'),
        ),
        migrations.AddField(
            model_name='rect',
            name='s3_id',
            field=models.CharField(default='', max_length=128, verbose_name='图片路径'),
        ),
    ]
