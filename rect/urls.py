# -*- coding: UTF-8 -*-

from django.conf import settings
from django.conf.urls import url, include
from django.conf.urls.static import static
from django.contrib import admin
from django.views.generic import TemplateView
from django.views.static import serve #处理静态文件
from rect.views import CreateScheduleView, UploadBatchView

import xadmin
# xadmin.autodiscover()

# version模块自动注册需要版本控制的 Model
from xadmin.plugins import xversion
xversion.register_models()




urlpatterns = [

    url(r'^create_schedule', CreateScheduleView.as_view(), name='create_schedule'),
    url(r'^upload_batch', UploadBatchView.as_view(), name='upload_batch')
]









