from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, PolymorphicProxySerializer, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from medical_audit.models import AuditAction, AuditDomain
from medical_audit.services import record_medical_audit_event

from .pagination import AnalyticsRawPagination
from .permissions import AnalyticsPermission
from .selectors import blood_glucose_queryset, blood_pressure_queryset, resolve_authorized_patient
from .serializers import (
    AggregateBloodPressureSeriesSerializer, AggregateGlucoseSeriesSerializer,
    AlertsAnalyticsSerializer, AnalyticsQuerySerializer, BloodPressureAggregateSerializer,
    BloodPressurePointSerializer, GlucoseAggregateSerializer, GlucosePointSerializer,
    GlucoseSeriesQuerySerializer, Hba1cPointSerializer, Hba1cQuerySerializer, Hba1cSeriesSerializer,
    RawBloodPressureSeriesSerializer, RawGlucoseSeriesSerializer, SeriesQuerySerializer,
    SummarySerializer, TrendsSerializer,
)
from .services import (
    CANONICAL_GLUCOSE_UNIT, blood_glucose_series, blood_pressure_series,
    calculate_alert_analytics, calculate_summary, calculate_trends, hba1c_points,
)


COMMON_RESPONSES = {
    400: OpenApiResponse(description='Paramètres temporels ou analytiques invalides.'),
    401: OpenApiResponse(description='Authentification JWT requise.'),
    403: OpenApiResponse(description='Compte, rôle ou profil insuffisant.'),
    404: OpenApiResponse(description='Patient inexistant ou inaccessible.'),
    405: OpenApiResponse(description='API strictement en lecture seule.'),
}
BASE_PARAMETERS = [
    OpenApiParameter('patient_id', OpenApiTypes.UUID, description='Obligatoire pour un médecin; interdit au patient.'),
    OpenApiParameter('period', OpenApiTypes.STR, enum=['7d', '30d', '90d', '6m', '1y', 'custom'], description='30d par défaut. custom exige les deux dates.'),
    OpenApiParameter('date_from', OpenApiTypes.STR, description='Borne UTC inclusive ISO 8601.'),
    OpenApiParameter('date_to', OpenApiTypes.STR, description='Borne UTC inclusive ISO 8601.'),
]
SERIES_PARAMETERS = BASE_PARAMETERS + [
    OpenApiParameter('granularity', OpenApiTypes.STR, enum=['raw', 'day', 'week', 'month']),
    OpenApiParameter('ordering', OpenApiTypes.STR, enum=['asc', 'desc']),
    OpenApiParameter('page', OpenApiTypes.INT, description='Séries raw uniquement.'),
    OpenApiParameter('page_size', OpenApiTypes.INT, description='Séries raw uniquement, maximum 100.'),
]


class AnalyticsAPIView(APIView):
    permission_classes = (AnalyticsPermission,)
    query_serializer_class = AnalyticsQuerySerializer
    statistic_type = ''

    def context(self, request):
        serializer = self.query_serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data
        patient = resolve_authorized_patient(user=request.user, patient_id=params.get('patient_id'))
        return params, patient

    def audit(self, request, patient, params):
        record_medical_audit_event(
            action=AuditAction.VIEW, domain=AuditDomain.ANALYTICS,
            resource_type='analytics.request', actor=request.user, patient=patient,
            request=request, metadata={
                'statistic_type': self.statistic_type,
                'period': params['period'], 'date_from': params['date_from'],
                'date_to': params['date_to'], 'granularity': params.get('granularity'),
            },
        )


class SummaryView(AnalyticsAPIView):
    statistic_type = 'SUMMARY'

    @extend_schema(tags=['Analytics'], summary='Résumé analytique patient', description='Calculs descriptifs, non diagnostiques. Patient : son propre dossier. Médecin : patient actuellement affecté.', parameters=BASE_PARAMETERS, responses={200: SummarySerializer, **COMMON_RESPONSES})
    def get(self, request):
        params, patient = self.context(request)
        result = calculate_summary(patient=patient, date_from=params['date_from'], date_to=params['date_to'])
        self.audit(request, patient, params)
        return Response(SummarySerializer(result).data)


class BloodPressureView(AnalyticsAPIView):
    statistic_type = 'BLOOD_PRESSURE'
    query_serializer_class = SeriesQuerySerializer

    @extend_schema(tags=['Analytics'], summary='Série de tension', description='mmHg; les intervalles sans mesure sont omis. Les séries raw sont paginées.', parameters=SERIES_PARAMETERS, responses={200: PolymorphicProxySerializer(component_name='BloodPressureSeriesResponse', serializers=[RawBloodPressureSeriesSerializer, AggregateBloodPressureSeriesSerializer], resource_type_field_name=None), **COMMON_RESPONSES})
    def get(self, request):
        params, patient = self.context(request)
        queryset = blood_pressure_queryset(patient=patient, date_from=params['date_from'], date_to=params['date_to'])
        series = blood_pressure_series(queryset, params['granularity']).order_by(('-' if params['ordering'] == 'desc' else '') + 'date')
        if params['granularity'] == 'raw':
            paginator = AnalyticsRawPagination()
            page = paginator.paginate_queryset(series, request, view=self)
            response = paginator.get_series_response(unit='mmHg', granularity='raw', results=BloodPressurePointSerializer(page, many=True).data)
        else:
            response = Response({'unit': 'mmHg', 'granularity': params['granularity'], 'results': BloodPressureAggregateSerializer(series, many=True).data})
        self.audit(request, patient, params)
        return response


class BloodGlucoseView(AnalyticsAPIView):
    statistic_type = 'BLOOD_GLUCOSE'
    query_serializer_class = GlucoseSeriesQuerySerializer

    @extend_schema(tags=['Analytics'], summary='Série de glycémie normalisée', description='Toutes les valeurs analytiques sont en MG_PER_DL (1 g/L = 100 mg/dL).', parameters=SERIES_PARAMETERS + [OpenApiParameter('context', OpenApiTypes.STR, enum=['BEFORE_MEAL', 'AFTER_MEAL', 'NO_MEAL'])], responses={200: PolymorphicProxySerializer(component_name='BloodGlucoseSeriesResponse', serializers=[RawGlucoseSeriesSerializer, AggregateGlucoseSeriesSerializer], resource_type_field_name=None), **COMMON_RESPONSES})
    def get(self, request):
        params, patient = self.context(request)
        queryset = blood_glucose_queryset(patient=patient, date_from=params['date_from'], date_to=params['date_to'], context=params.get('context'))
        series = blood_glucose_series(queryset, params['granularity']).order_by(('-' if params['ordering'] == 'desc' else '') + 'date')
        if params['granularity'] == 'raw':
            paginator = AnalyticsRawPagination()
            page = paginator.paginate_queryset(series, request, view=self)
            rows = [dict(row, unit=CANONICAL_GLUCOSE_UNIT) for row in page]
            response = paginator.get_series_response(unit=CANONICAL_GLUCOSE_UNIT, granularity='raw', results=GlucosePointSerializer(rows, many=True).data)
        else:
            response = Response({'unit': CANONICAL_GLUCOSE_UNIT, 'granularity': params['granularity'], 'results': GlucoseAggregateSerializer(series, many=True).data})
        self.audit(request, patient, params)
        return response


class Hba1cView(AnalyticsAPIView):
    statistic_type = 'HBA1C'
    query_serializer_class = Hba1cQuerySerializer

    @extend_schema(tags=['Analytics'], summary='Série HbA1c', description='Valeurs en %. Série brute paginée; la tendance compare chaque point au précédent dans la page.', parameters=BASE_PARAMETERS + [OpenApiParameter('ordering', OpenApiTypes.STR, enum=['asc', 'desc']), OpenApiParameter('page', OpenApiTypes.INT), OpenApiParameter('page_size', OpenApiTypes.INT, description='Maximum 100.')], responses={200: Hba1cSeriesSerializer, **COMMON_RESPONSES})
    def get(self, request):
        params, patient = self.context(request)
        queryset = blood_glucose_queryset(patient=patient, date_from=params['date_from'], date_to=params['date_to']).filter(hba1c__isnull=False)
        queryset = queryset.order_by(('-' if params['ordering'] == 'desc' else '') + 'date_mesure')
        paginator = AnalyticsRawPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        self.audit(request, patient, params)
        return paginator.get_series_response(unit='%', granularity='raw', results=Hba1cPointSerializer(hba1c_points(page), many=True).data)


class AlertsView(AnalyticsAPIView):
    statistic_type = 'ALERTS'

    @extend_schema(tags=['Analytics'], summary='Résumé analytique des alertes', description='Aucun message médical complet n’est renvoyé.', parameters=BASE_PARAMETERS, responses={200: AlertsAnalyticsSerializer, **COMMON_RESPONSES})
    def get(self, request):
        params, patient = self.context(request)
        result = calculate_alert_analytics(patient=patient, date_from=params['date_from'], date_to=params['date_to'])
        self.audit(request, patient, params)
        return Response(AlertsAnalyticsSerializer(result).data)


class TrendsView(AnalyticsAPIView):
    statistic_type = 'TRENDS'

    @extend_schema(tags=['Analytics'], summary='Tendances descriptives', description='Compare deux fenêtres consécutives de sept jours. INSufficient data sous le minimum configurable. Ne qualifie jamais médicalement la variation.', parameters=BASE_PARAMETERS, responses={200: TrendsSerializer, **COMMON_RESPONSES})
    def get(self, request):
        params, patient = self.context(request)
        result = calculate_trends(patient=patient, date_to=params['date_to'])
        self.audit(request, patient, params)
        return Response(TrendsSerializer(result).data)
