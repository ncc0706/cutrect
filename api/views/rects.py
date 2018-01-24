from rest_framework import mixins, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import detail_route, list_route
from rest_framework.response import Response
from rect.serializers import  PageSerializer, \
                PageRectSerializer, RectSerializer, \
                ScheduleSerializer, CCTaskSerializer, ClassifyTaskSerializer, \
                PageTaskSerializer
from rect.models import Page, PageRect, Rect, \
                        Schedule, CharClassifyPlan, CCTask, ClassifyTask, PageTask

from api.pagination import StandardPagination
import math



class PageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Page.objects.all()
    serializer_class = PageSerializer


class PageRectViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PageRect.objects.all()
    serializer_class = PageRectSerializer


class RectResultsSetPagination(StandardPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class RectViewSet(viewsets.ModelViewSet, mixins.ListModelMixin):
    queryset = Rect.objects.all()
    serializer_class = RectSerializer
    pagination_class = RectResultsSetPagination

    @list_route(methods=['get'], url_path='ccreview')
    def ccreview(self, request):
        schedule_id = self.request.query_params.get('schedule_id', None)
        cc = self.request.query_params.get('cc', 0.96)
        #page = self.request.query_params.get('page', 1)
        #page_size = self.request.query_params.get('page_size', 20)
        try:
            schedule = Schedule.objects.get(pk=schedule_id)
        except Schedule.DoesNotExist:
            return Response({"status": -1,
                             "msg": "not found schedule instance!"})

        reelRids = [reel.rid for reel in schedule.reels.all()]
        if len(reelRids) <= 0 :
            return Response({"status": -1,
                             "msg": "The schedule does not select reels!"})
        rects = Rect.objects.filter(reel__in=reelRids, cc__lte=cc).order_by("-cc")

        page = self.paginate_queryset(rects)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(rects, many=True)
        return Response(serializer.data)

    @list_route(methods=['get'], url_path='cpreview')
    def cpreview(self, request):
        ccpid = self.request.query_params.get('ccpid', None)
        wcc = self.request.query_params.get('wcc', None)
        #char = self.request.query_params.get('char', None)
        ccp = CharClassifyPlan.objects.get(id=ccpid)
        char = ccp.ch
        schedule_id = ccp.schedule_id

        try:
            schedule = Schedule.objects.get(pk=schedule_id)
        except Schedule.DoesNotExist:
            return Response({"status": -1,
                             "msg": "not found schedule instance!"})

        reelRids = [reel.rid for reel in schedule.reels.all()]
        if len(reelRids) <= 0 :
            return Response({"status": -1,
                             "msg": "The schedule does not select reels!"})
        rects = Rect.objects.filter(reel__in=reelRids, ch=char).order_by("-wcc")

        page = self.paginate_queryset(rects)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(rects, many=True)
        return Response(serializer.data)

    @list_route(methods=['get'], url_path='cp_wcc_count')
    def cp_wcc_count(self, request):
        ccpid = self.request.query_params.get('ccpid', None)
        wcc = self.request.query_params.get('wcc', None)
        if not wcc:
            return Response({"status": -1,
                             "msg": "pls provide param wcc."})

        ccp = CharClassifyPlan.objects.get(id=ccpid)
        char = ccp.ch
        schedule_id = ccp.schedule_id

        try:
            schedule = Schedule.objects.get(pk=schedule_id)
        except Schedule.DoesNotExist:
            return Response({"status": -1,
                             "msg": "not found schedule instance!"})

        reelRids = [reel.rid for reel in schedule.reels.all()]
        if len(reelRids) <= 0:
            return Response({"status": -1,
                             "msg": "The schedule does not select reels!"})
        count = Rect.objects.filter(reel__in=reelRids, ch=char, wcc__gte=wcc).order_by("-wcc").count()

        #page_size = self.paginator.get_page_size(request)
        #actual_page = math.ceil(count / page_size)
        return Response({'status': 0,
                         'msg': 'success',
                         'data': {
                             'count': count
                         }})


class ScheduleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Schedule.objects.all()
    serializer_class = ScheduleSerializer

