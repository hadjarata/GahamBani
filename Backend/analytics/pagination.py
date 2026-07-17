from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class AnalyticsRawPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_series_response(self, *, unit, granularity, results):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'unit': unit,
            'granularity': granularity,
            'results': results,
        })
