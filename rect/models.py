# -*- coding: UTF-8 -*-
from django.db import models

# Create your models here.
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
import uuid
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from jwt_auth.models import Staff
from django.utils.timezone import localtime, now
from functools import wraps, reduce
from django.db.models import Min, Sum
from django.db import connection, transaction
import json
import urllib.request
import collections
from .lib.fields import JSONField
from django.db import connection, transaction
from django.db.models import Sum, Case, When, Value, Count, Avg, F
from django_bulk_update.manager import BulkUpdateManager
from .lib.arrange_rect import ArrangeRect
from django.forms.models import model_to_dict
from django.core.exceptions import ValidationError
from dotmap import DotMap
from PIL import Image, ImageFont, ImageDraw
from io import BytesIO
from celery import shared_task
from cutrect import email_if_fails
import os, sys
import re

try:
    from functools import wraps
except ImportError:
    from django.utils.functional import wraps

import inspect


def disable_for_loaddata(signal_handler):
    @wraps(signal_handler)
    def wrapper(*args, **kwargs):
        for fr in inspect.stack():
            if inspect.getmodulename(fr[1]) == 'loaddata':
                return
        signal_handler(*args, **kwargs)
    return wrapper

def iterable(cls):
    """
    model的迭代器并输出dict，且不包含内部__,_开头的key
    """
    @wraps(cls)
    def iterfn(self):
        iters = dict((k, v) for k, v in self.__dict__.items() if not k.startswith("_"))

        for k, v in iters.items():
            yield k, v

    cls.__iter__ = iterfn
    return cls

"""
格式说明：存储经文内容，换行用\n，每页前有换页标记p\n。读取处理原始数据\r\n为\n。
"""
class SutraTextField(models.TextField):

    description = '存储经文内容，换行用\n，每页前有换页标记p\n'

    def __init__(self, *args, **kwargs):
        kwargs['blank'] = True
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        del kwargs["blank"]
        return name, path, args, kwargs

    def get_prep_value(self, value):
        value = value.replace('\r\n', '\n')
        value = super().get_prep_value(value)
        return self.to_python(value)


class SliceType(object):
    PPAGE = 1
    CC = 2
    CLASSIFY = 3
    CHECK = 4
    VDEL = 5
    REVIEW = 6
    CHOICES = (
        (CC, u'置信度'),
        (PPAGE, u'顺序校对'),
        (CLASSIFY, u'聚类'),
        (CHECK, u'差缺补漏'),
        (VDEL, u'删框'),
        (REVIEW, u'反馈审查'),
    )


class ScheduleStatus:
    NOT_ACTIVE = 0
    ACTIVE = 1
    EXPIRED = 2
    DISCARD = 3
    COMPLETED = 4
    CHOICES = (
        (NOT_ACTIVE, u'未激活'),
        (ACTIVE, u'已激活'),
        (EXPIRED, u'已过期'),
        (DISCARD, u'已作废'),
        (COMPLETED, u'已完成'),
    )

class PageStatus:
    INITIAL = 0
    RECT_NOTFOUND = 1
    PARSE_FAILED = 2
    RECT_NOTREADY = 3
    CUT_PIC_NOTFOUND = 4
    COL_PIC_NOTFOUND = 5
    COL_POS_NOTFOUND = 6
    RECT_COL_NOTREADY = 7
    RECT_COL_NOTFOUND = 8
    READY = 9
    MARKED = 10

    CHOICES = (
        (INITIAL, u'初始化'),
        (RECT_NOTFOUND, u'切分数据未上传'),
        (PARSE_FAILED, u'数据解析失败'),
        (RECT_NOTREADY, u'字块数据未展开'),
        (CUT_PIC_NOTFOUND, u'图片不存在'),
        (COL_PIC_NOTFOUND, u'列图不存在'),
        (COL_POS_NOTFOUND, u'列图坐标不存在'),
        (RECT_COL_NOTREADY, u'字块对应列图未准备'),
        (RECT_COL_NOTFOUND, u'字块对应列图不存在'),
        (READY, u'已准备好'),
        (MARKED, u'已入卷标记'),
    )
class TaskStatus:
    NOT_READY = 0
    NOT_GOT = 1
    EXPIRED = 2
    ABANDON = 3
    EMERGENCY = 4
    HANDLING = 5
    COMPLETED = 7
    DISCARD = 9

    CHOICES = (
        (NOT_READY, u'未就绪'),
        (NOT_GOT, u'未领取'),
        (EXPIRED, u'已过期'),
        (ABANDON, u'已放弃'),
        (EMERGENCY, u'加急'),
        (HANDLING, u'处理中'),
        (COMPLETED, u'已完成'),
        (DISCARD, u'已作废'),
    )
    #未完成状态.
    remain_status = [NOT_READY, NOT_GOT, EXPIRED, ABANDON, HANDLING]

class PriorityLevel:
    LOW = 1
    MIDDLE = 3
    HIGH = 5
    HIGHEST = 7

    CHOICES = (
        (LOW, u'低'),
        (MIDDLE, u'中'),
        (HIGH, u'高'),
        (HIGHEST, u'最高'),
    )

class OpStatus(object):
    NORMAL = 1
    CHANGED = 2
    DELETED = 3
    RECOG = 4
    COLLATE = 5
    CHOICES = (
        (NORMAL, u'正常'),
        (CHANGED, u'被更改'),
        (DELETED, u'被删除'),
        (RECOG, u'文字识别'),
        (COLLATE, u'文字校对')
    )

class ReviewResult(object):
    INITIAL = 0
    AGREE = 1
    DISAGREE = 2
    IGNORED = 3
    CHOICES = (
        (INITIAL, u'未审阅'),
        (AGREE, u'已同意'),
        (DISAGREE, u'未同意'),
        (IGNORED, u'被略过'),
    )

class ModelDiffMixin(object):
    """
    A model mixin that tracks model fields' values and provide some useful api
    to know what fields have been changed.
    """

    def __init__(self, *args, **kwargs):
        super(ModelDiffMixin, self).__init__(*args, **kwargs)
        self.__initial = self._dict

    @property
    def diff(self):
        d1 = self.__initial
        d2 = self._dict
        diffs = [(k, (v, d2[k])) for k, v in d1.items() if v != d2[k]]
        return dict(diffs)

    @property
    def has_changed(self):
        return bool(self.diff)

    @property
    def changed_fields(self):
        return self.diff.keys()

    def get_field_diff(self, field_name):
        """
        Returns a diff for field if it's changed and None otherwise.
        """
        return self.diff.get(field_name, None)

    def save(self, *args, **kwargs):
        """
        Saves model and set initial state.
        """
        super(ModelDiffMixin, self).save(*args, **kwargs)
        self.__initial = self._dict

    @property
    def _dict(self):
        return model_to_dict(self, fields=[field.name for field in
                             self._meta.fields])


class TripiMixin(object):
    def __str__(self):
        return self.name

class Node(models.Model):
    name = models.CharField(u"名称", max_length=64)
    code = models.CharField(u"节点代码", max_length=27, primary_key=True)
    parent = models.ForeignKey('self', verbose_name=u'父节点', related_name='children', null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        verbose_name=u'节点'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name +":" +self.code

class LQSutra(models.Model, TripiMixin):
    code = models.CharField(verbose_name='龙泉经目编码', max_length=8, primary_key=True) #（为"LQ"+ 经序号 + 别本号）
    name = models.CharField(verbose_name='龙泉经目名称', max_length=64, blank=False)
    total_reels = models.IntegerField(verbose_name='总卷数', blank=True, default=1)

    class Meta:
        verbose_name = u"龙泉经目"
        verbose_name_plural = u"龙泉经目管理"


class Tripitaka(models.Model, TripiMixin):
    MARK_CHOICES = (
        ('v', 'v: 表示册'),
        ('r', 'r: 表示卷')
    )
    code = models.CharField(verbose_name='实体藏经版本编码', primary_key=True, max_length=4, blank=False)
    name = models.CharField(verbose_name='实体藏经名称', max_length=32, blank=False)
    shortname = models.CharField(verbose_name='简称（用于校勘记）', max_length=32, blank=False)
    vol_reel_mark = models.CharField('册/卷标记符号', max_length=1, default='r', choices=MARK_CHOICES)

    class Meta:
        verbose_name = '实体藏经'
        verbose_name_plural = '实体藏经管理'

class Volume(models.Model):
    tripitaka = models.ForeignKey(Tripitaka, on_delete=models.CASCADE)
    vol_no = models.SmallIntegerField(verbose_name='册序号')
    page_count = models.IntegerField(verbose_name='册页数')

    class Meta:
        verbose_name = u"实体册"
        verbose_name_plural = u"实体册"

    def __str__(self):
        return '%s: 第%s册' % (self.tripitaka.name, self.vol_no)


class Sutra(models.Model, TripiMixin):
    sid = models.CharField(verbose_name='实体藏经|唯一经号编码', editable=True, max_length=10, primary_key=True) # 藏经版本编码 + 5位经序号+1位别本号
    tripitaka = models.ForeignKey(Tripitaka, related_name='sutras', on_delete=models.SET_NULL, null=True)
    code = models.CharField(verbose_name='实体经目编码', max_length=5, blank=False)
    variant_code = models.CharField(verbose_name='别本编码', max_length=1, default='0')
    name = models.CharField(verbose_name='实体经目名称', max_length=64, blank=True)
    lqsutra = models.ForeignKey(LQSutra, verbose_name='龙泉经目编码', null=True, blank=True, on_delete=models.SET_NULL) #（为"LQ"+ 经序号 + 别本号）
    total_reels = models.IntegerField(verbose_name='总卷数', blank=True, default=1)

    class Meta:
        verbose_name = '实体经目'
        verbose_name_plural = '实体经目管理'

    @property
    def sutra_sn(self):
        return "%s%s%s" % (self.tripitaka_id, self.code.zfill(5), self.variant_code)

    def __str__(self):
        return self.name

class Reel(models.Model):
    EDITION_TYPE_UNKNOWN = 0 # 未选择
    EDITION_TYPE_BASE = 1 # 底本
    EDITION_TYPE_CHECKED = 2 # 对校本
    EDITION_TYPE_PROOF = 3 # 参校本
    EDITION_TYPE_CHOICES = (
        (EDITION_TYPE_UNKNOWN, '未选择'),
        (EDITION_TYPE_BASE, '底本'),
        (EDITION_TYPE_CHECKED, '对校本'),
        (EDITION_TYPE_PROOF, '参校本'),
    )

    rid = models.CharField(verbose_name='实体藏经卷级总编码', max_length=14, blank=False, primary_key=True)
    sutra = models.ForeignKey(Sutra, related_name='reels', on_delete=models.CASCADE)
    reel_no = models.SmallIntegerField(verbose_name='经卷序号', blank=False)
    ready = models.BooleanField(verbose_name='已准备好', db_index=True, default=False)
    txt_ready = models.BooleanField(verbose_name='文本状态', default=False)
    cut_ready = models.BooleanField(verbose_name='切分数据状态', default=False)
    column_ready = models.BooleanField(verbose_name='切列图状态', default=False)
    start_vol = models.SmallIntegerField('起始册', default=0)
    start_vol_page = models.SmallIntegerField('起始册的页序号', default=0)
    end_vol = models.SmallIntegerField('终止册', default=0)
    end_vol_page = models.SmallIntegerField('终止册的页序号', default=0)
    text = SutraTextField('经文', default='') #按实际行加了换行符，换页标记为p\n


    class Meta:
        verbose_name = '实体藏经卷'
        verbose_name_plural = '实体藏经卷管理'

    @property
    def reel_sn(self):
        return "%sr%03d" % (self.sutra_id, self.reel_no)

    @property
    def name(self):
        return u"第%s卷" %(self.reel_no,)

    def __str__(self):
        return self.sutra.name + self.rid

class Page(models.Model):
    pid = models.CharField(verbose_name='实体藏经页级总编码', max_length=21, blank=False, primary_key=True)
    reel = models.ForeignKey(Reel, related_name='pages', on_delete=models.SET_NULL, null=True)
    bar_no = models.CharField(verbose_name='实体藏经页级栏序号', max_length=1, default='0')
    envelop_no = models.SmallIntegerField(verbose_name='函序号（第几）', default=0, blank=False)
    vol_no = models.SmallIntegerField(verbose_name='册序号（第几）', default=0, blank=False)
    page_no = models.SmallIntegerField(verbose_name='册级页序号', default=0, blank=False)
    reel_no = models.SmallIntegerField(verbose_name='卷序号（第几）', default=0, blank=False)
    reel_page_no = models.SmallIntegerField('卷中页序号', default=0)
    status = models.PositiveSmallIntegerField(db_index=True, verbose_name=u'操作类型',
                                              choices=PageStatus.CHOICES, default=PageStatus.INITIAL)
    json = JSONField(verbose_name='栏信息', default=dict)
    updated_at = models.DateTimeField(verbose_name='更新时间', auto_now=True)
    text = SutraTextField('经文', default='') # 文字校对后的经文
    cut_info = JSONField(verbose_name='切分信息', default=list)
    cut_updated_at = models.DateTimeField('切分同步时间', null=True)
    cut_add_count = models.SmallIntegerField('切分信息增加字数', default=0)
    cut_wrong_count = models.SmallIntegerField('切分信息识别错的字数', default=0)
    cut_confirm_count = models.SmallIntegerField('切分信息需要确认的字数', default=0)
    cut_verify_count = models.SmallIntegerField('切分信息需要确认的字数', default=0)
    s3_id = models.CharField(verbose_name='图片路径', max_length=128, default='', blank=False)

    def _remote_image_stream(self):
        opener = urllib.request.build_opener()
        # AWS S3 Private Resource snippet, someday here should to be.
        # opener.addheaders = [('Authorization', 'AWS AKIAIOSFODNN7EXAMPLE:02236Q3V0RonhpaBX5sCYVf1bNRuU=')]
        reader = opener.open(self.get_real_path())
        return Image.open(BytesIO(reader.read()))

    # https://hk.tower.im/projects/3032432a1c5b4618a668509f25448034/messages/419ecfb3901e4faba2574447ce8cc7f6/
    # 储存格式文档
    @classmethod
    def sid_to_uri(cls, s3_id):
        tr_code = s3_id[0:2]
        trail_code = s3_id[-1]
        ann_code = tr_code + s3_id[8:-1]
        ann_code = ann_code.replace("_", "/")
        ann_code = ann_code.replace('p', '')
        if trail_code != '0':
            ann_code += trail_code

        return "%s/%s" % (os.path.dirname(ann_code), ann_code.replace("/", "_"))

    def get_real_path(self):
        self.s3_id = self.s3_id or Page.convertSN_to_S3ID(self.page_sn)
        return 'https://s3.cn-north-1.amazonaws.com.cn/lqdzj-image/%s.jpg' % Page.sid_to_uri(self.s3_id);

    def down_col_pos(self):
        cut_file = self.get_real_path()[0:-3] + "col"
        opener = urllib.request.build_opener()
        try:
            response = opener.open(cut_file)
        except urllib.error.HTTPError as e:
            # 下载失败
            print(self.pid + ": col download failed")
            return
        try:
            body = response.read().decode('utf8')
            json_data = json.loads(body)
            if type(json_data['col_data']) == list :
                self.status = PageStatus.RECT_COL_NOTREADY
                self.json = json_data['col_data']
                self.save()
        except:
            print(self.pid + ": col parse failed")
            print("CONTENT:" + body)
            self.json = {"content": body}
            self.status = PageStatus.COL_POS_NOTFOUND
            self.save(update_fields=['status', 'json'])
            return

    def down_pagerect(self):
        cut_file = self.get_real_path()[0:-3] + "cut"
        opener = urllib.request.build_opener()
        try:
            response = opener.open(cut_file)
        except urllib.error.HTTPError as e:
            # 下载失败
            print(self.pid + ": rect download failed")
            self.status = PageStatus.RECT_NOTFOUND
            self.save(update_fields=['status'])
            return
        try:
            body = response.read().decode('utf8')
            json_data = json.loads(body)
            K, ext = os.path.splitext(os.path.basename(Page.sid_to_uri(self.s3_id)))
            image_code = "%s.%s" % (K, ext)
            if json_data['img_code'] == image_code and type(json_data['char_data'])==list :
                pass
        except:
            print(self.pid + ": rect parse failed")
            print("CONTENT:" + body)
            self.json = {"content": body}
            self.status = PageStatus.PARSE_FAILED
            self.save(update_fields=['status', 'json'])
            return
        self.pagerects.all().delete()
        PageRect(page=self, reel=self.reel, line_count=0, column_count=0, rect_set=json_data['char_data']).save()
        self.status = PageStatus.RECT_NOTREADY
        self.save(update_fields=['status'])
        print(self.pid + ": pagerect saved")

    # https://hk.tower.im/projects/3032432a1c5b4618a668509f25448034/messages/419ecfb3901e4faba2574447ce8cc7f6/
    # 储存格式文档
    @property
    def page_sn(self):
        if (self.vol_no == 0):
            return "%sr%03dp%05d%s" % (self.reel_id[0:-4], self.reel_no, self.reel_page_no, self.bar_no)
        elif (self.envelop_no == 0):
            return "%sv%03dp%05d%s" % (self.reel_id[0:-4], self.vol_no, self.page_no, self.bar_no)
        else:
            return "%se%3dv%03dp%05d%s" % (self.reel_id[0:-4], self.envelop_no, self.vol_no, self.page_no, self.bar_no)

    def save(self, *args, **kwargs):
        if (self.vol_no == 0 and (self.reel_no == 0 or self.reel_page_no == 0)):
            raise ValidationError('When vol_no is 0, reel_no and reel_page_no need be set.')
        if (self.reel_no == 0 and (self.vol_no == 0 or self.page_no == 0)):
            raise ValidationError('When reel_no is 0, vol_no and page_no need be set.')
        super(Page, self).save(*args, **kwargs)

    @classmethod
    def convertSN_to_S3ID(cls, page_sn):
        COL_VOLUME_RE = r'(?P<tp_no>[A-Z]{2})(?P<sutra_no>[\da-z]{6})v(?P<vol_no>\d{3})p(?P<page_no>\d{5})(?P<bar_no>[0a-z]?)'
        COL_REEL_RE = r'(?P<tp_no>[A-Z]{2})(?P<sutra_no>[\da-z]{6})r(?P<reel_no>\d{3})p(?P<reel_page_no>\d{5})(?P<bar_no>[0a-z]?)'
        COL_ENVELOP_RE = r'(?P<tp_no>[A-Z]{2})(?P<sutra_no>[\da-z]{6})e(?P<envelop_no>\d{3})v(?P<vol_no>\d{3})p(?P<page_no>\d{5})(?P<bar_no>[0a-z]?)'
        ret = re.compile(COL_VOLUME_RE).match(page_sn)
        if (ret):
            result = ret.groupdict()
            return '%s%s_%d_p%d%s' % (result['tp_no'], result['sutra_no'], int(result['vol_no']), int(result['page_no']), result['bar_no'])
        ret = re.compile(COL_REEL_RE).match(page_sn)
        if (ret):
            result = ret.groupdict()
            sutra_no = result['sutra_no']
            sutra_code = result['sutra_no'].lstrip("0")
            if sutra_code[-1] == '0':
                sutra_code = sutra_code[0:-1]
            return '%s%s_%s_%d_p%d%s' % (result['tp_no'], sutra_no, sutra_code, int(result['reel_no']), int(result['reel_page_no']), result['bar_no'])
        ret = re.compile(COL_ENVELOP_RE).match(page_sn)
        if (ret):
            result = ret.groupdict()
            return '%s%s_%d_%d_p%d%s' % (result['tp_no'], result['sutra_no'], int(result['envelop_no']), int(result['vol_no']), int(result['page_no']), result['bar_no'])


    class Meta:
        verbose_name = '实体藏经页'
        verbose_name_plural = '实体藏经页管理'


@receiver(pre_save, sender=Page)
def rebuild_page_s3_id(sender, instance, **kwargs):
    instance.s3_id = Page.convertSN_to_S3ID(instance.page_sn)

class PageRect(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    page = models.ForeignKey(Page, null=True, blank=True, related_name='pagerects', on_delete=models.SET_NULL,
                             verbose_name=u'关联源页信息')
    reel = models.ForeignKey(Reel, null=True, blank=True, related_name='reels', on_delete=models.SET_NULL)
    op = models.PositiveSmallIntegerField(db_index=True, verbose_name=u'操作类型', default=OpStatus.NORMAL)
    line_count = models.IntegerField(null=True, blank=True, verbose_name=u'最大行数') # 最大文本行号
    column_count = models.IntegerField(null=True, blank=True, verbose_name=u'最大列数') # 最大文本长度
    rect_set = JSONField(default=list, verbose_name=u'切字块JSON切分数据集')
    created_at = models.DateTimeField(null=True, blank=True, verbose_name=u'创建时间', auto_now_add=True)
    primary = models.BooleanField(verbose_name="主切分方案", default=True)

    def __str__(self):
        return str(self.id)

    class Meta:
        verbose_name = u"源页切分集"
        verbose_name_plural = u"源页切分集管理"
        ordering = ('id',)

    @property
    def serialize_set(self):
        return dict((k, v) for k, v in self.__dict__.items() if not k.startswith("_"))


    def rebuild_rect(self):
        if len(self.rect_set) == 0:
            return
        Rect.objects.filter(page_code=self.page_id).all().delete()
        return PageRect.align_rects_bypage(self, self.rect_set)

    @classmethod
    def reformat_rects(cls, page_id):
        ret = True
        rects = Rect.objects.filter(page_code=page_id).all()
        pagerect = PageRect.objects.filter(page_id=page_id).first()
        if rects.count() == 0:
            return ret
        return PageRect.align_rects_bypage(pagerect, rects)

    @classmethod
    def align_rects_bypage(cls, pagerect, rects):
        ret = True
        columns, column_len = ArrangeRect.resort_rects_from_qs(rects)
        page = pagerect.page
        rect_list = list()
        for lin_n, line in columns.items():
            for col_n, _r in enumerate(line, start=1):
                _rect = DotMap(_r)
                _rect['line_no'] = lin_n
                _rect['char_no'] = col_n
                _rect['page_code'] = pagerect.page_id
                _rect['reel_id'] = pagerect.reel_id
                _rect = Rect.normalize(_rect)
                try :
                    # 这里以左上角坐标，落在哪个列数据为准
                    column_dict = (item for item in page.json if item["x"] <= _rect['x'] and _rect['x'] <= item["x1"] and
                                                item["y"] <= _rect['y'] and _rect['y'] <= item["y1"] ).__next__()
                    _rect['column_set'] = column_dict
                except:
                    ret = False
                rect_list.append(_rect)
        Rect.bulk_insert_or_replace(rect_list)
        pagerect.line_count = max(map(lambda Y: Y['line_no'], rect_list))
        pagerect.column_count = max(map(lambda Y: Y['char_no'], rect_list))
        pagerect.save()
        return ret





    def make_annotate(self):
        source_img = self.page._remote_image_stream().convert("RGBA")
        work_dir = "/tmp/annotations"
        try:
            os.stat(work_dir)
        except:
            os.makedirs(work_dir)
        out_file = "%s/%s.jpg" % (work_dir, self.page_id)
        # make a blank image for the rectangle, initialized to a completely transparent color
        tmp = Image.new('RGBA', source_img.size, (0, 0, 0, 0))
        # get a drawing context for it
        draw = ImageDraw.Draw(tmp)
        if sys.platform in ('linux2', 'linux'):
            myfont = ImageFont.truetype(settings.BASE_DIR + "/static/fonts/SourceHanSerifTC-Bold.otf", 11)
        elif sys.platform == 'darwin':
            myfont = ImageFont.truetype("/Library/Fonts/Songti.ttc", 12)

        columns, column_len = ArrangeRect.resort_rects_from_qs(self.rect_set)
        for lin_n, line in columns.items():
            for col_n, _r in enumerate(line, start=1):
                rect = DotMap(_r)
                # draw a semi-transparent rect on the temporary image
                draw.rectangle(((rect.x, rect.y), (rect.x + int(rect.w), rect.y + int(rect.h))),
                                 fill=(0, 0, 0, 120))
                anno_str = u"%s-%s" % (lin_n, col_n)
                draw.text((rect.x, rect.y), anno_str, font=myfont, fill=(200, 255, 255))
        source_img = Image.alpha_composite(source_img, tmp)
        source_img.save(out_file, "JPEG")


@iterable
class Rect(models.Model):
    # https://github.com/aykut/django-bulk-update
    objects = BulkUpdateManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    cid = models.CharField(verbose_name=u'经字号', max_length=28, db_index=True)
    reel = models.ForeignKey(Reel, null=True, blank=True, related_name='rects', on_delete=models.SET_NULL)
    page_code = models.CharField(max_length=23, blank=False, verbose_name=u'关联源页CODE', db_index = True)
    column_set = JSONField(default=list, verbose_name=u'切字块所在切列JSON数据集')
    char_no = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name=u'字号', default=0)
    line_no = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name=u'行号', default=0)  # 对应图片的一列

    op = models.PositiveSmallIntegerField(verbose_name=u'操作类型', default=OpStatus.NORMAL)
    x = models.PositiveSmallIntegerField(verbose_name=u'X坐标', default=0)
    y = models.PositiveSmallIntegerField(verbose_name=u'Y坐标', default=0)
    w = models.IntegerField(verbose_name=u'宽度', default=1)
    h = models.IntegerField(verbose_name=u'高度', default=1)

    cc = models.FloatField(null=True, blank=True, verbose_name=u'切分置信度', db_index=True, default=1)
    ch = models.CharField(null=True, blank=True, verbose_name=u'文字', max_length=2, default='', db_index=True)
    wcc = models.FloatField(null=True, blank=True, verbose_name=u'识别置信度', default=1, db_index=True)
    ts = models.CharField(null=True, blank=True, verbose_name=u'标字', max_length=2, default='')
    s3_inset = models.FileField(max_length=256, blank=True, null=True, verbose_name=u's3地址', upload_to='tripitaka/hans',
                                  storage='storages.backends.s3boto.S3BotoStorage')
    updated_at = models.DateTimeField(verbose_name='更新时间1', auto_now=True)
    s3_id = models.CharField(verbose_name='图片路径', max_length=128, default='', blank=False)

    class DefaultDict(dict):

        def __missing__(self, key):
            return None

    @property
    def rect_sn(self):
        return "%s%02dn%02d" % (self.page_code, self.line_no, self.char_no)

    def __str__(self):
        return self.ch

    def column_uri(self):
        return Rect.column_uri_path(self.column_set['col_id'])

    @staticmethod
    def column_uri_path(col_s3_id):
        col_id = str(col_s3_id)
        col_path = col_id.replace('_', '/')
        return 'https://s3.cn-north-1.amazonaws.com.cn/lqdzj-col/%s/%s.jpg' % (os.path.dirname(col_path), col_id)

    @staticmethod
    def canonicalise_uuid(uuid):
        import re
        uuid = str(uuid)
        _uuid_re = re.compile(r'^[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}$')
        _hex_re = re.compile(r'^[0-9A-Fa-f]{32}$')
        if _uuid_re.match(uuid):
            return uuid.upper()
        if _hex_re.match(uuid):
            return '-'.join([uuid[0:8], uuid[8:12], uuid[12:16],
                            uuid[16:20], uuid[20:]]).upper()
        return None

    @property
    def serialize_set(self):
        return dict((k, v) for k, v in self.__dict__.items() if not k.startswith("_"))

    @staticmethod
    def generate(rect_dict={}, exist_rects=[]):
        _dict = Rect.DefaultDict()
        for k, v in rect_dict.items():
            _dict[k] = v
        if type(_dict['id']).__name__ == "UUID":
            _dict['id'] = _dict['id'].hex
        try:
            el = list(filter(lambda x: x.id.hex == _dict['id'].replace('-', ''), exist_rects))
            rect = el[0]
        except:
            rect = Rect()
        valid_keys = rect.serialize_set.keys()-['id']
        key_set = set(valid_keys).intersection(_dict.keys())
        for key in key_set:
            if key in valid_keys:
                setattr(rect, key, _dict[key])
        rect.updated_at = localtime(now())
        rect.cid = rect.rect_sn
        ### 这里由于外部数据格式不规范，对char作为汉字的情况追加的。
        if _dict['char']:
            rect.ch = _dict['char']

        rect = Rect.normalize(rect)
        return rect

    @staticmethod
    def bulk_insert_or_replace(rects):
        updates = []
        news = []
        ids = [r['id'] for r in filter(lambda x: Rect.canonicalise_uuid(DotMap(x).id), rects)]
        exists = Rect.objects.filter(id__in=ids)
        for r in rects:
            rect = Rect.generate(r, exists)
            if (rect._state.adding):
                news.append(rect)
            else:
                updates.append(rect)
        Rect.objects.bulk_create(news)
        Rect.objects.bulk_update(updates)

    @staticmethod
    def normalize(r):
        if (r.w < 0):
            r.x = r.x + r.w
            r.w = abs(r.w)
        if (r.h < 0):
            r.y = r.y + r.h
            r.h = abs(r.h)

        if (r.w == 0):
            r.w = 1
        if (r.h == 0):
            r.h = 1
        return r

    class Meta:
        verbose_name = u"源-切字块"
        verbose_name_plural = u"源-切字块管理"
        ordering = ('-cc',)


@receiver(pre_save, sender=Rect)
def positive_w_h_fields(sender, instance, **kwargs):
    instance = Rect.normalize(instance)
    instance.sid = "%s%02dn%02d" % (Page.convertSN_to_S3ID(instance.page_code), instance.line_no, instance.char_no)

@receiver(post_save)
@disable_for_loaddata
def create_new_node(sender, instance, created, **kwargs):
    if sender==LQSutra:
        Node(code=instance.code, name=instance.name).save()

    if sender==Sutra:
        if created:
            Node(code=instance.sutra_sn, name=instance.name, parent_id=instance.lqsutra_id).save()
        else:
            Node.objects.filter(pk=instance.sutra_sn).update(parent_id=instance.lqsutra_id)
    if sender==Reel:
        if created:
            Node(code=instance.reel_sn, name=instance.name, parent_id=instance.sutra_id).save()
        else:
            Node.objects.filter(pk=instance.reel_sn).update(parent_id=instance.sutra_id)


class Patch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reel = models.ForeignKey(Reel, null=True, blank=True, related_name='patches', on_delete=models.CASCADE) # 注意：卷编码这里没有考虑余量
    op = models.PositiveSmallIntegerField(verbose_name=u'操作类型', default=OpStatus.NORMAL)
    x = models.PositiveSmallIntegerField(verbose_name=u'X坐标', default=0)
    y = models.PositiveSmallIntegerField(verbose_name=u'Y坐标', default=0)
    w = models.PositiveSmallIntegerField(verbose_name=u'宽度', default=1)
    h = models.PositiveSmallIntegerField(verbose_name=u'高度', default=1)
    ocolumn_uri = models.CharField(verbose_name='行图片路径', max_length=128, blank=False)
    ocolumn_x = models.PositiveSmallIntegerField(verbose_name=u'行图X坐标', default=0)
    ocolumn_y = models.PositiveSmallIntegerField(verbose_name=u'行图Y坐标', default=0)
    char_no = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name=u'字号', default=0)
    line_no = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name=u'行号', default=0)  # 对应图片的一列
    ch = models.CharField(null=True, blank=True, verbose_name=u'文字', max_length=2, default='')
    rect_id = models.CharField(verbose_name='字块CID', max_length=128, blank=False)
    rect_x = models.PositiveSmallIntegerField(verbose_name=u'原字块X坐标', default=0)
    rect_y = models.PositiveSmallIntegerField(verbose_name=u'原字块Y坐标', default=0)
    rect_w = models.PositiveSmallIntegerField(verbose_name=u'原字块宽度', default=1)
    rect_h = models.PositiveSmallIntegerField(verbose_name=u'原字块高度', default=1)
    ts = models.CharField(null=True, blank=True, verbose_name=u'修订文字', max_length=2, default='')
    result = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name=u'审定意见', default=ReviewResult.INITIAL)  # 1 同意 2 不同意
    modifier = models.ForeignKey(Staff, null=True, blank=True, related_name='modify_patches', verbose_name=u'修改人', on_delete=models.SET_NULL)
    verifier = models.ForeignKey(Staff, null=True, blank=True, related_name='verify_patches', verbose_name=u'审定人', on_delete=models.SET_NULL)

    submitted_at = models.DateTimeField(verbose_name='修订时间', auto_now_add=True)
    updated_at = models.DateTimeField(null=True, blank=True, verbose_name=u'更新时间', auto_now=True)

    def __str__(self):
        return self.ch

    class Meta:
        verbose_name = u"Patch"
        verbose_name_plural = u"Patch管理"
        ordering = ("ch",)


class Schedule(models.Model, ModelDiffMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reels = models.ManyToManyField(Reel, limit_choices_to={'ready': True}, blank=True )
    name = models.CharField(verbose_name='计划名称', max_length=64)

    cc_threshold = models.FloatField("切分置信度阈值", default=0.65, blank=True)

    # todo 设置总任务的优先级时, 子任务包的优先级凡是小于总任务优先级的都提升优先级, 高于或等于的不处理. 保持原优先级.
    priority = models.PositiveSmallIntegerField(
        choices=PriorityLevel.CHOICES,
        default=PriorityLevel.MIDDLE,
        verbose_name=u'任务计划优先级',
    )
    status = models.PositiveSmallIntegerField(
        db_index=True,
        null=True,
        blank=True,
        choices=ScheduleStatus.CHOICES,
        default=ScheduleStatus.NOT_ACTIVE,
        verbose_name=u'计划状态',
    )
    due_at = models.DateField(null=True, blank=True, verbose_name=u'截止日期')
    created_at = models.DateTimeField(null=True, blank=True, verbose_name=u'创建日期', auto_now_add=True)
    remark = models.TextField(max_length=256, null=True, blank=True, verbose_name=u'备注')
    schedule_no = models.CharField(max_length=64, verbose_name=u'切分计划批次', default='', help_text=u'自动生成', blank=True)

    def __str__(self):
        return self.name

    def create_reels_task(self):
        pass
        # NOTICE: 实际这里不必执行，多重关联这时并未创建成功。
        # 在数据库层用存储过程在关联表记录创建后，创建卷任务。
        # 为逻辑必要，留此函数
        # tasks = []
        # for reel in self.reels.all():
        #     tasks.append(Reel_Task_Statistical(schedule=self, reel=reel))
        # Reel_Task_Statistical.objects.bulk_create(tasks)

    class Meta:
        verbose_name = u"切分计划"
        verbose_name_plural = u"切分计划管理"
        ordering = ('due_at', "status")


def activity_log(func):
    @wraps(func)
    def tmp(*args, **kwargs):
        result = func(*args, **kwargs)
        self = args[0]
        # 暂无任务跟踪记录需求
        # ActivityLog(user=self.owner, object_pk=self.pk,
        #                                 object_type=type(self).__name__,
        #                                 action=func.__name__).save()
        return result
    return tmp


class Schedule_Task_Statistical(models.Model):
    schedule = models.ForeignKey(Schedule, null=True, blank=True, related_name='schedule_task_statis', on_delete=models.SET_NULL,
                                 verbose_name=u'切分计划')
    amount_of_cctasks = models.IntegerField(verbose_name=u'置信任务总数', default=-1)
    completed_cctasks = models.IntegerField(verbose_name=u'置信任务完成数', default=0)
    amount_of_classifytasks = models.IntegerField(verbose_name=u'聚类任务总数', default=-1)
    completed_classifytasks = models.IntegerField(verbose_name=u'聚类任务完成数', default=0)
    amount_of_absenttasks = models.IntegerField(verbose_name=u'查漏任务总数', default=-1)
    completed_absenttasks = models.IntegerField(verbose_name=u'查漏任务完成数', default=0)
    amount_of_pptasks = models.IntegerField(verbose_name=u'逐字任务总数', default=-1)
    completed_pptasks = models.IntegerField(verbose_name=u'逐字任务完成数', default=0)
    amount_of_vdeltasks = models.IntegerField(verbose_name=u'删框任务总数', default=-1)
    completed_vdeltasks = models.IntegerField(verbose_name=u'删框任务完成数', default=0)
    amount_of_reviewtasks = models.IntegerField(verbose_name=u'审定任务总数', default=-1)
    completed_reviewtasks = models.IntegerField(verbose_name=u'审定任务完成数', default=0)
    remark = models.TextField(max_length=256, null=True, blank=True, verbose_name=u'备注', default= '')
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = u"切分计划任务统计"
        verbose_name_plural = u"切分计划任务统计管理"
        ordering = ('schedule', )

class Reel_Task_Statistical(models.Model):
    schedule = models.ForeignKey(Schedule, null=True, blank=True, related_name='schedule_reel_task_statis',
                                 on_delete=models.SET_NULL, verbose_name=u'切分计划')
    reel = models.ForeignKey(Reel, related_name='reel_tasks_statis', on_delete=models.SET_NULL, null=True)
    amount_of_cctasks = models.IntegerField(verbose_name=u'置信任务总数', default=-1)
    completed_cctasks = models.IntegerField(verbose_name=u'置信任务完成数', default=0)
    amount_of_absenttasks = models.IntegerField(verbose_name=u'查漏任务总数', default=-1)
    completed_absenttasks = models.IntegerField(verbose_name=u'查漏任务完成数', default=0)
    amount_of_pptasks = models.IntegerField(verbose_name=u'逐字任务总数', default=-1)
    completed_pptasks = models.IntegerField(verbose_name=u'逐字任务完成数', default=0)

    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = u"实体卷任务统计"
        verbose_name_plural = u"实体卷任务统计管理"
        ordering = ('schedule', '-updated_at')

    @shared_task
    @email_if_fails
    def gen_pptask_by_plan():
        with transaction.atomic():
            for stask in Schedule_Task_Statistical.objects.filter(amount_of_pptasks=-1):
                # 逐卷创建任务
                for rtask in Reel_Task_Statistical.objects.filter(schedule=stask.schedule).prefetch_related('reel'):
                    if rtask.amount_of_pptasks != -1:
                        continue
                    count = allocateTasks(stask.schedule, rtask.reel, SliceType.PPAGE)
                    rtask.amount_of_pptasks = count
                    rtask.save(update_fields=['amount_of_pptasks'])
                # 检查每卷大于-1，开启总计划，更新任务数。
                quertset = Reel_Task_Statistical.objects.filter(schedule=stask.schedule)
                result = quertset.aggregate(Min('amount_of_pptasks'))
                # 只有所有卷都开启任务，计划表的总任务数才更新。
                if result['amount_of_pptasks__min'] != -1:
                    count = quertset.aggregate(Sum('amount_of_pptasks'))['amount_of_pptasks__sum']
                    stask.amount_of_pptasks = count
                    stask.save(update_fields=['amount_of_pptasks'])


    @shared_task
    @email_if_fails
    def gen_cctask_by_plan():
        with transaction.atomic():
            for stask in Schedule_Task_Statistical.objects.filter(amount_of_cctasks=-1):
                # 未激活说明，第一步的CC阈值没有填写
                if stask.schedule.status == ScheduleStatus.NOT_ACTIVE:
                    continue
                # 逐卷创建任务
                for rtask in Reel_Task_Statistical.objects.filter(schedule=stask.schedule).prefetch_related('reel'):
                    if rtask.amount_of_cctasks != -1:
                        continue
                    count = allocateTasks(stask.schedule, rtask.reel, SliceType.CC)
                    rtask.amount_of_cctasks = count
                    rtask.save(update_fields=['amount_of_cctasks'])
                # 检查每卷大于-1，开启总计划，更新任务数。
                quertset = Reel_Task_Statistical.objects.filter(schedule=stask.schedule)
                result = quertset.aggregate(Min('amount_of_cctasks'))
                # 只有所有卷都开启任务，计划表的总任务数才更新。
                if result['amount_of_cctasks__min'] != -1:
                    count = quertset.aggregate(Sum('amount_of_cctasks'))['amount_of_cctasks__sum']
                    stask.amount_of_cctasks = count
                    stask.save(update_fields=['amount_of_cctasks'])

class Task(models.Model):
    '''
    切分校对计划的任务实例
    估计划激活后, 即后台自动据校对类型分配任务列表.
    '''
    number = models.CharField(primary_key=True, max_length=64, verbose_name='任务编号')
    ttype = models.PositiveSmallIntegerField(
        db_index=True,
        choices=SliceType.CHOICES,
        default=SliceType.PPAGE,
        verbose_name=u'切分方式',
    )
    desc = models.TextField(null=True, blank=True, verbose_name=u'任务格式化描述')
    status = models.PositiveSmallIntegerField(
        db_index=True,
        choices=TaskStatus.CHOICES,
        default=TaskStatus.NOT_GOT,
        verbose_name=u'任务状态',
    )
    priority = models.PositiveSmallIntegerField(
        choices=PriorityLevel.CHOICES,
        default=PriorityLevel.MIDDLE,
        verbose_name=u'任务优先级',
        db_index=True,
    )
    update_date = models.DateField(null=True, verbose_name=u'最近处理时间')
    obtain_date = models.DateField(null=True, verbose_name=u'领取时间')
    def __str__(self):
        return self.number

    @classmethod
    def serialize_set(cls, dataset):
        return ";".join(dataset)

    # 六种不同任务有不同的统计模式
    def tasks_increment(self):
        stask = Schedule_Task_Statistical.objects.filter(schedule=self.schedule)
        if self.ttype == SliceType.CC:
            stask.update(completed_cctasks = F('completed_cctasks')+1)
            reel_id = self.rect_set[0]['reel_id']
            rtask = Reel_Task_Statistical.objects.filter(schedule=self.schedule, reel_id=reel_id)
            rtask.update(completed_cctasks = F('completed_cctasks')+1)
        elif self.ttype == SliceType.CLASSIFY:
            stask.update(completed_classifytasks = F('completed_classifytasks')+1)
        elif self.ttype == SliceType.PPAGE:
            stask.update(completed_pptasks = F('completed_pptasks')+1)
            reel_id = self.page_set[0]['reel_id']
            rtask = Reel_Task_Statistical.objects.filter(schedule=self.schedule, reel_id=reel_id)
            rtask.update(completed_cctasks = F('completed_pptasks')+1)
        elif self.ttype == SliceType.CHECK:
            stask.update(completed_absenttasks = F('completed_absenttasks')+1)
            reel_id = self.page_set[0]['reel_id']
            rtask = Reel_Task_Statistical.objects.filter(schedule=self.schedule, reel_id=reel_id)
            rtask.update(completed_cctasks = F('completed_absenttasks')+1)
        elif self.ttype == SliceType.VDEL:
            stask.update(completed_absenttasks = F('completed_vdeltasks')+1)
        elif self.ttype == SliceType.REVIEW:
            stask.update(completed_absenttasks = F('completed_reviewtasks')+1)

    @activity_log
    def done(self):
        self.update_date = localtime(now()).date()
        self.tasks_increment()
        self.status = TaskStatus.COMPLETED
        return self.save(update_fields=["status"])

    @activity_log
    def emergen(self):
        self.status = TaskStatus.EMERGENCY
        return self.save(update_fields=["status"])

    @activity_log
    def expire(self):
        self.status = TaskStatus.EXPIRED
        return self.save(update_fields=["status"])

    @activity_log
    def obtain(self, user):
        self.obtain_date = localtime(now()).date()
        self.status = TaskStatus.HANDLING
        self.owner = user
        self.save()

    class Meta:
        abstract = True
        verbose_name = u"切分任务"
        verbose_name_plural = u"切分任务管理"
        ordering = ("priority", "status")
        indexes = [
            models.Index(fields=['priority', 'status']),
        ]

class CCTask(Task):
    schedule = models.ForeignKey(Schedule, null=True, blank=True, related_name='cc_tasks', on_delete=models.SET_NULL,
                                 verbose_name=u'切分计划')
    count = models.IntegerField("任务字块数", default=20)
    cc_threshold = models.FloatField("最高置信度")
    owner = models.ForeignKey(Staff, null=True, blank=True, related_name='cc_tasks', on_delete=models.SET_NULL)
    rect_set = JSONField(default=list, verbose_name=u'字块集') # [rect_json]

    class Meta:
        verbose_name = u"置信校对任务"
        verbose_name_plural = u"置信校对任务管理"


class ClassifyTask(Task):
    schedule = models.ForeignKey(Schedule, null=True, blank=True, related_name='classify_tasks', on_delete=models.SET_NULL,
                                 verbose_name=u'切分计划')
    count = models.IntegerField("任务字块数", default=10)
    char_set = models.TextField(null=True, blank=True, verbose_name=u'字符集')
    owner = models.ForeignKey(Staff, null=True, blank=True, related_name='classify_tasks', on_delete=models.SET_NULL)
    rect_set = JSONField(default=list, verbose_name=u'字块集') # [rect_json]

    class Meta:
        verbose_name = u"聚类校对任务"
        verbose_name_plural = u"聚类校对任务管理"


class PageTask(Task):
    schedule = models.ForeignKey(Schedule, null=True, blank=True, related_name='page_tasks', on_delete=models.SET_NULL,
                                 verbose_name=u'切分计划')
    count = models.IntegerField("任务页的数量", default=1)
    owner = models.ForeignKey(Staff, null=True, blank=True, related_name='page_tasks', on_delete=models.SET_NULL)
    page_set = JSONField(default=list, verbose_name=u'页的集合') # [page_json]

    class Meta:
        verbose_name = u"逐字校对任务"
        verbose_name_plural = u"逐字校对任务管理"


class AbsentTask(Task):
    schedule = models.ForeignKey(Schedule, null=True, blank=True, related_name='absent_tasks', on_delete=models.SET_NULL,
                                 verbose_name=u'切分计划')
    count = models.IntegerField("任务页的数量", default=1)
    owner = models.ForeignKey(Staff, null=True, blank=True, related_name='absent_tasks', on_delete=models.SET_NULL)
    page_set = JSONField(default=list, verbose_name=u'页的集合') # [page_id, page_id]

    class Meta:
        verbose_name = u"查漏补缺任务"
        verbose_name_plural = u"查漏补缺任务管理"


class DelTask(Task):
    schedule = models.ForeignKey(Schedule, null=True, blank=True, related_name='del_tasks', on_delete=models.SET_NULL,
                                 verbose_name=u'切分计划')
    count = models.IntegerField("任务字块数", default=10)
    owner = models.ForeignKey(Staff, null=True, blank=True, related_name='del_tasks', on_delete=models.SET_NULL)
    rect_set = JSONField(default=list, verbose_name=u'字块集') # [deletion_item_id, deletion_item_id]

    class Meta:
        verbose_name = u"删框任务"
        verbose_name_plural = u"删框任务管理"

    def execute(self):
        for item in self.del_task_items.all():
            if item.result == ReviewResult.AGREE:
                item.confirm()
            else:
                item.undo()


class ReviewTask(Task):
    schedule = models.ForeignKey(Schedule, null=True, blank=True, related_name='review_tasks', on_delete=models.SET_NULL,
                                 verbose_name=u'切分计划')
    count = models.IntegerField("任务字块数", default=10)
    owner = models.ForeignKey(Staff, null=True, blank=True, related_name='review_tasks', on_delete=models.SET_NULL)
    rect_set = JSONField(default=list, verbose_name=u'字块补丁集') # [patch_id, patch_id]

    class Meta:
        verbose_name = u"审定任务"
        verbose_name_plural = u"审定任务管理"


class DeletionCheckItem(models.Model):
    objects = BulkUpdateManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    op = models.PositiveSmallIntegerField(verbose_name=u'操作类型', default=OpStatus.DELETED)
    x = models.PositiveSmallIntegerField(verbose_name=u'X坐标', default=0)
    y = models.PositiveSmallIntegerField(verbose_name=u'Y坐标', default=0)
    w = models.PositiveSmallIntegerField(verbose_name=u'宽度', default=1)
    h = models.PositiveSmallIntegerField(verbose_name=u'高度', default=1)
    ocolumn_uri = models.CharField(verbose_name='行图片路径', max_length=128, blank=False)
    ocolumn_x = models.PositiveSmallIntegerField(verbose_name=u'行图X坐标', default=0)
    ocolumn_y = models.PositiveSmallIntegerField(verbose_name=u'行图Y坐标', default=0)
    ch = models.CharField(null=True, blank=True, verbose_name=u'文字', max_length=2, default='')

    rect_id = models.CharField(verbose_name='字块CID', max_length=128, blank=False)
    modifier = models.ForeignKey(Staff, null=True, blank=True, related_name='modify_deletions', verbose_name=u'修改人', on_delete=models.SET_NULL)
    verifier = models.ForeignKey(Staff, null=True, blank=True, related_name='verify_deletions', verbose_name=u'审定人', on_delete=models.SET_NULL)
    result = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name=u'审定意见', default=ReviewResult.INITIAL)  # 1 同意 2 不同意
    del_task = models.ForeignKey(DelTask, null=True, blank=True, related_name='del_task_items', on_delete=models.SET_NULL,
                                 verbose_name=u'删框任务')
    created_at = models.DateTimeField(verbose_name='删框时间', auto_now_add=True)
    updated_at = models.DateTimeField(null=True, blank=True, verbose_name=u'更新时间', auto_now=True)

    @classmethod
    def create_from_rect(cls, rects, t):
        rect_ids = [rect ['id'] for rect in filter(lambda x: x['op'] == 3, rects)]
        for r in Rect.objects.filter(id__in=rect_ids):
            DeletionCheckItem(x=r.x, y=r.y, w=r.w, h=r.h, ocolumn_uri=r.column_uri(),
                            ocolumn_x=r.column_set['x'], ocolumn_y=r.column_set['y'], ch=r.ch,
                            rect_id=r.id, modifier=t.owner).save()

    def undo(self):
        Rect.objects.filter(pk=self.rect_id).update(op=2)

    def confirm(self):
        Rect.objects.filter(pk=self.rect_id).all().delete()


    class Meta:
        verbose_name = u"删框记录"
        verbose_name_plural = u"删框记录管理"


class ActivityLog(models.Model):
    user = models.ForeignKey(Staff, related_name='activities', on_delete=models.SET_NULL, null=True)
    log = models.CharField(verbose_name=u'记录', max_length=128, default='')
    object_type = models.CharField(verbose_name=u'对象类型', max_length=32)
    object_pk = models.CharField(verbose_name=u'对象主键', max_length=64)
    action = models.CharField(verbose_name=u'行为', max_length=16)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    def log_message(self):
        return "User:%s %s to %s(%s) at %s" % (self.user.id,
                                               self.action, self.object_type,
                                               self.object_pk, self.created_at)


class CharClassifyPlan(models.Model):
    schedule = models.ForeignKey(Schedule, null=True, blank=True, related_name='char_clsfy_plan',
                                 on_delete=models.SET_NULL, verbose_name=u'切分计划')
    ch = models.CharField(null=True, blank=True, verbose_name=u'文字', max_length=2, default='', db_index=True)
    total_cnt = models.IntegerField(verbose_name=u'总数', default=0, db_index=True)
    needcheck_cnt = models.IntegerField(verbose_name=u'待检查数', default=0)
    done_cnt = models.IntegerField(verbose_name=u'已完成数', default=0)
    wcc_threshold = models.DecimalField(verbose_name=u'识别置信阈值',max_digits=4, decimal_places=3, default=0)


    class Meta:
        verbose_name = u"聚类准备表"
        verbose_name_plural = u"聚类准备表管理"

    @shared_task
    @email_if_fails
    def create_charplan(schedule_id):
        schedule = Schedule.objects.get(pk=schedule_id)
        CharClassifyPlan.objects.filter(schedule=schedule).all().delete()
        cursor = connection.cursor()
        raw_sql = '''
        SET SEARCH_PATH TO public;
        INSERT INTO public.rect_charclassifyplan (ch, total_cnt, needcheck_cnt, done_cnt, wcc_threshold, schedule_id)
        SELECT
        ch,
        count(rect_rect."ch") as total_cnt,
        0,0,0,
        '%s'
        FROM public.rect_rect
        where reel_id IN ('%s')
        group by ch
        ''' % (schedule.id, '\',\''.join(schedule.reels.values_list('rid', flat=True)))
        cursor.execute(raw_sql)
        CharClassifyPlan.objects.filter(schedule=schedule, total_cnt__lt=10).all().delete()


    def measure_charplan(self, wcc_threshold):
        result = Rect.objects.filter(ch=self.ch, reel_id__in=self.schedule.reels.values_list('rid', flat=True)).aggregate(
            needcheck_cnt=Sum(Case(When(wcc__lte=wcc_threshold, then=Value(1)),
            default=Value(0),
            output_field=models.    IntegerField())),
            total_cnt=Count('id'))
        self.total_cnt=result['total_cnt']
        self.needcheck_cnt=result['needcheck_cnt']
        self.wcc_threshold=wcc_threshold
        self.save()


class AllocateTask(object):
    class Config:
        CCTASK_COUNT = 20
        DEFAULT_COUNT = 20
        BULK_TASK_COUNT = 30
        PAGETASK_COUNT = 1

    def __init__(self, schedule, reel = None):
        self.schedule = schedule
        self.reel = reel

    def allocate(self):
        pass

    def task_id(self):
        cursor = connection.cursor()
        cursor.execute("select nextval('task_seq')")
        result = cursor.fetchone()
        return result[0]

class CCAllocateTask(AllocateTask):
    def allocate(self):
        reel = self.reel
        query_set = reel.rects.filter(cc__lte=self.schedule.cc_threshold)
        count = AllocateTask.Config.CCTASK_COUNT
        rect_set = []
        task_set = []
        total_tasks = 0
        for no, rect in enumerate(query_set, start=1):
            # rect_set.append(rect.id.hex)
            rect_set.append(rect.serialize_set)
            if len(rect_set) == count:
                # 268,435,455可容纳一部大藏经17，280，000个字
                task_no = "%s_%s%05X" % (self.schedule.schedule_no, reel.rid, self.task_id())
                task = CCTask(number=task_no, schedule=self.schedule, ttype=SliceType.CC, count=count, status=TaskStatus.NOT_GOT,
                              rect_set=list(rect_set), cc_threshold=rect.cc)
                rect_set.clear()
                task_set.append(task)
                if len(task_set) == AllocateTask.Config.BULK_TASK_COUNT:
                    CCTask.objects.bulk_create(task_set)
                    total_tasks += len(task_set)
                    task_set.clear()
        if len(rect_set) > 0:
            task_no = "%s_%s%05X" % (self.schedule.schedule_no, reel.rid, self.task_id())
            task = CCTask(number=task_no, schedule=self.schedule, ttype=SliceType.CC, count=count, status=TaskStatus.NOT_GOT,
                            rect_set=list(rect_set), cc_threshold=rect.cc)
            rect_set.clear()
            task_set.append(task)
        CCTask.objects.bulk_create(task_set)
        total_tasks += len(task_set)
        return total_tasks

def batch(iterable, n = 1):
    current_batch = []
    for item in iterable:
        current_batch.append(item)
        if len(current_batch) == n:
            yield current_batch
            current_batch = []
    if current_batch:
        yield current_batch


class ClassifyAllocateTask(AllocateTask):

    def allocate(self):
        rect_set = []
        word_set = {}
        task_set = []
        count = AllocateTask.Config.DEFAULT_COUNT
        reel_ids = self.schedule.reels.values_list('rid', flat=True)
        base_queryset = Rect.objects.filter(reel_id__in=reel_ids)
        total_tasks = 0
        # 首先找出这些计划准备表
        for plans in batch(CharClassifyPlan.objects.filter(schedule=self.schedule), 3):
            # 然后把分组的计划变成，不同分片的queryset组拼接
            questsets = [base_queryset.filter(ch=_plan.ch, wcc__lte=_plan.wcc_threshold) for _plan in plans]
            if len(questsets) > 1:
                queryset = questsets[0].union(*questsets[1:])
            else:
                queryset = questsets[0]
            # 每组去递归补足每queryset下不足20单位的情况
            for no, rect in enumerate(queryset, start=1):
                rect_set.append(rect.serialize_set)
                word_set[rect.ch] = 1

                if len(rect_set) == count:
                    task_no = "%s_%07X" % (self.schedule.schedule_no, self.task_id())
                    task = ClassifyTask(number=task_no, schedule=self.schedule, ttype=SliceType.CLASSIFY, count=count,
                                        status=TaskStatus.NOT_GOT,
                                        rect_set=list(rect_set),
                                        char_set=ClassifyTask.serialize_set(word_set.keys()))
                    rect_set.clear()
                    word_set = {}
                    task_set.append(task)
                    if len(task_set) == AllocateTask.Config.BULK_TASK_COUNT:
                        ClassifyTask.objects.bulk_create(task_set)
                        total_tasks += len(task_set)
                        task_set.clear()
        if len(rect_set) > 0:
            task_no = "%s_%07X" % (self.schedule.schedule_no, self.task_id())
            task = ClassifyTask(number=task_no, schedule=self.schedule, ttype=SliceType.CLASSIFY, count=count,
                                status=TaskStatus.NOT_GOT,
                                rect_set=list(rect_set),
                                char_set=ClassifyTask.serialize_set(word_set.keys()))
            rect_set.clear()
            task_set.append(task)
        ClassifyTask.objects.bulk_create(task_set)
        total_tasks += len(task_set)
        return total_tasks


class PerpageAllocateTask(AllocateTask):

    def allocate(self):
        reel = self.reel
        query_set = filter(lambda x: x.primary, PageRect.objects.filter(reel=reel))

        page_set = []
        task_set = []
        count = AllocateTask.Config.PAGETASK_COUNT
        total_tasks = 0
        for no, pagerect in enumerate(query_set, start=1):
            page_set.append(pagerect.serialize_set)
            if len(page_set) == count:
                task_no = "%s_%s%05X" % (self.schedule.schedule_no, reel.rid, self.task_id())
                task = PageTask(number=task_no, schedule=self.schedule, ttype=SliceType.PPAGE, count=1,
                                  status=TaskStatus.NOT_READY,
                                  page_set=list(page_set))
                page_set.clear()
                task_set.append(task)
                if len(task_set) == AllocateTask.Config.BULK_TASK_COUNT:
                    PageTask.objects.bulk_create(task_set)
                    total_tasks += len(task_set)
                    task_set.clear()

        PageTask.objects.bulk_create(task_set)
        total_tasks += len(task_set)
        return total_tasks


class AbsentpageAllocateTask(AllocateTask):

    def allocate(self):
        reel = self.reel
        # TODO: 缺少缺页查找页面
        queryset = PageRect.objects.filter(reel=reel)
        query_set = filter(lambda x: x.primary, queryset)

        page_set = []
        task_set = []
        count = AllocateTask.Config.PAGETASK_COUNT
        total_tasks = 0
        for no, pagerect in enumerate(query_set, start=1):
            page_set.append(pagerect.serialize_set)
            if len(page_set) == count:
                task_no = "%s_%s%05X" % (self.schedule.schedule_no, reel.rid, self.task_id())
                task = AbsentTask(number=task_no, schedule=self.schedule, ttype=SliceType.CHECK, count=1,
                                page_set=list(page_set))
                page_set.clear()
                task_set.append(task)
                if len(task_set) == AllocateTask.Config.BULK_TASK_COUNT:
                    PageTask.objects.bulk_create(task_set)
                    total_tasks += len(task_set)
                    task_set.clear()

        PageTask.objects.bulk_create(task_set)
        total_tasks += len(task_set)
        return total_tasks


class DelAllocateTask(AllocateTask):

    def allocate(self):
        rect_set = []
        task_set = []
        count = AllocateTask.Config.PAGETASK_COUNT
        total_tasks = 0
        for items in batch(DeletionCheckItem.objects.filter(del_task_id=None), 10):
            if len(items) == 10:
                rect_set = list(map(lambda x:x.pk.hex, items))
                task_no = "%s_%07X" % ('DelTask', self.task_id())
                task = DelTask(number=task_no,  ttype=SliceType.VDEL,
                                rect_set=rect_set)
                rect_set.clear()
                ids = [_item.pk for _item in items]
                DeletionCheckItem.objects.filter(id__in=ids).update(del_task_id=task_no)
                task_set.append(task)
                if len(task_set) == AllocateTask.Config.BULK_TASK_COUNT:
                    DelTask.objects.bulk_create(task_set)
                    total_tasks += len(task_set)
                    task_set.clear()
        DelTask.objects.bulk_create(task_set)
        total_tasks += len(task_set)
        task_set.clear()
        return total_tasks

def allocateTasks(schedule, reel, type):
    allocator = None
    count = -1
    if type == SliceType.CC: # 置信度
        allocator = CCAllocateTask(schedule, reel)
    elif type == SliceType.CLASSIFY: # 聚类
        allocator = ClassifyAllocateTask(schedule)
    elif type == SliceType.PPAGE: # 逐字
        allocator = PerpageAllocateTask(schedule, reel)
    elif type == SliceType.CHECK: # 查漏
        allocator = PerpageAllocateTask(schedule, reel)
    elif type == SliceType.VDEL: # 删框
        allocator = DelAllocateTask(schedule, reel)
    if allocator:
        count = allocator.allocate()
    return count



@receiver(post_save, sender=Schedule)
@disable_for_loaddata
def post_schedule_create_pretables(sender, instance, created, **kwargs):
    if created:
        Schedule_Task_Statistical(schedule=instance).save()
        # Schedule刚被创建，就建立聚类字符准备表，创建逐字校对的任务，任务为未就绪状态
        CharClassifyPlan.create_charplan.s(instance.pk.hex).apply_async(countdown=20)
        Reel_Task_Statistical.gen_pptask_by_plan.apply_async(countdown=60)
    else:
        # update
        if (instance.has_changed) and ( 'status' in instance.changed_fields):
            before, now = instance.get_field_diff('status')
            if now == ScheduleStatus.ACTIVE and before == ScheduleStatus.NOT_ACTIVE:
                # Schedule被激活，创建置信校对的任务
                Reel_Task_Statistical.gen_cctask_by_plan.delay()

# class AccessRecord(models.Model):
#     date = models.DateField()
#     user_count = models.IntegerField()
#     view_count = models.IntegerField()
#
#     class Meta:
#         verbose_name = u"访问记录"
#         verbose_name_plural = verbose_name
#
#     def __str__(self):
#         return "%s Access Record" % self.date.strftime('%Y-%m-%d')


