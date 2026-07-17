from datetime import datetime, time
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from accounts.models import UserRole
from profiles.models import PatientProfile
from profiles.selectors import active_patient_profiles_for_doctor
from medical_audit.models import AuditAction, AuditDomain
from medical_audit.services import record_medical_audit_event
from alerts.services import evaluate_measurement_for_alerts

from .models import BloodGlucose, BloodPressure
from .pagination import MonitoringPagination
from .permissions import MonitoringMeasurementPermission
from .serializers import BloodGlucoseSerializer, BloodPressureSerializer
from .services import create_measurement, update_measurement


FILTER_PARAMETERS = [
    OpenApiParameter(
        'date_from',
        OpenApiTypes.STR,
        description='Date ou date-heure minimale de mesure (ISO 8601).',
    ),
    OpenApiParameter(
        'date_to',
        OpenApiTypes.STR,
        description='Date ou date-heure maximale de mesure (ISO 8601).',
    ),
    OpenApiParameter(
        'ordering',
        OpenApiTypes.STR,
        enum=['date_mesure', '-date_mesure'],
        description='Tri chronologique. Par défaut : mesures les plus récentes.',
    ),
    OpenApiParameter(
        'patient_id',
        OpenApiTypes.UUID,
        description='Filtre réservé aux médecins et limité à leurs patients actifs.',
    ),
    OpenApiParameter('page', OpenApiTypes.INT, description='Numéro de page.'),
    OpenApiParameter(
        'page_size',
        OpenApiTypes.INT,
        description='Nombre de résultats par page (maximum 100).',
    ),
]


def parse_date_filter(value, *, end_of_day=False):
    parsed = parse_datetime(value)
    if parsed is None:
        parsed_date = parse_date(value)
        if parsed_date is None:
            raise ValidationError('Les filtres de date doivent respecter le format ISO 8601.')
        parsed = datetime.combine(parsed_date, time.max if end_of_day else time.min)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


class MonitoringViewSetMixin:
    permission_classes = (MonitoringMeasurementPermission,)
    pagination_class = MonitoringPagination
    http_method_names = ('get', 'post', 'patch', 'head', 'options')

    def _record_audit(self, *, action, instance=None, metadata=None, changes=None):
        patient = instance.patient if instance is not None else None
        if patient is None and self.request.user.role == UserRole.PATIENT:
            patient = getattr(self.request.user, 'patient_profile', None)
        return record_medical_audit_event(
            action=action,
            domain=AuditDomain.MONITORING,
            resource_type=self.model_class._meta.label_lower,
            resource_id=getattr(instance, 'pk', None),
            actor=self.request.user,
            patient=patient,
            request=self.request,
            metadata=metadata,
            changes=changes,
        )

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        count = response.data.get('count', len(response.data))
        self._record_audit(
            action=AuditAction.LIST,
            metadata={'result_count': count, 'source': 'API'},
        )
        return response

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        response = Response(self.get_serializer(instance).data)
        self._record_audit(action=AuditAction.VIEW, instance=instance)
        return response

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated and user.role == UserRole.PATIENT:
            context['patient_profile'] = PatientProfile.objects.filter(user=user).first()
        return context

    def get_queryset(self):
        user = self.request.user
        queryset = self.model_class.objects.select_related('patient__user')
        if not user.is_authenticated or not user.is_active:
            return queryset.none()
        if user.role == UserRole.PATIENT:
            queryset = queryset.filter(patient__user=user, patient__user__is_active=True)
        elif user.role == UserRole.DOCTOR:
            queryset = queryset.filter(
                patient__in=active_patient_profiles_for_doctor(user),
            )
        else:
            return queryset.none()

        patient_id = self.request.query_params.get('patient_id')
        if patient_id:
            if user.role != UserRole.DOCTOR:
                raise ValidationError({'patient_id': 'Ce filtre est réservé aux médecins.'})
            try:
                patient_id = UUID(patient_id)
            except (TypeError, ValueError) as exc:
                raise ValidationError({'patient_id': 'Identifiant patient invalide.'}) from exc
            queryset = queryset.filter(patient_id=patient_id)

        date_from_value = self.request.query_params.get('date_from')
        date_to_value = self.request.query_params.get('date_to')
        date_from = parse_date_filter(date_from_value) if date_from_value else None
        date_to = (
            parse_date_filter(date_to_value, end_of_day=True)
            if date_to_value
            else None
        )
        if date_from and date_to and date_from > date_to:
            raise ValidationError({'date_to': 'La date de fin doit suivre la date de début.'})
        if date_from:
            queryset = queryset.filter(date_mesure__gte=date_from)
        if date_to:
            queryset = queryset.filter(date_mesure__lte=date_to)

        ordering = self.request.query_params.get('ordering', '-date_mesure')
        if ordering not in ('date_mesure', '-date_mesure'):
            raise ValidationError({'ordering': 'Tri autorisé : date_mesure ou -date_mesure.'})
        return queryset.order_by(ordering, '-created_at')

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                serializer.instance = create_measurement(
                    self.model_class,
                    patient=serializer.context['patient_profile'],
                    validated_data=serializer.validated_data,
                )
                evaluate_measurement_for_alerts(
                    serializer.instance, actor=self.request.user, request=self.request,
                )
                self._record_audit(
                    action=AuditAction.CREATE,
                    instance=serializer.instance,
                    metadata={
                        'changed_fields': sorted(serializer.validated_data),
                        'source': 'API',
                    },
                )
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages) from exc

    def perform_update(self, serializer):
        numeric_fields = {
            BloodPressure: ('systolique', 'diastolique', 'frequence_cardiaque', 'numero_mesure'),
            BloodGlucose: ('valeur', 'hba1c'),
        }[self.model_class]
        before = {
            field: getattr(serializer.instance, field)
            for field in numeric_fields
            if field in serializer.validated_data
        }
        try:
            with transaction.atomic():
                serializer.instance = update_measurement(
                    serializer.instance,
                    patient_user=self.request.user,
                    validated_data=serializer.validated_data,
                )
                relevant_fields = {
                    BloodPressure: {'systolique', 'diastolique', 'frequence_cardiaque'},
                    BloodGlucose: {
                        'valeur', 'unite', 'hba1c', 'type_mesure', 'contexte_repas',
                    },
                }[self.model_class]
                if relevant_fields.intersection(serializer.validated_data):
                    evaluate_measurement_for_alerts(
                        serializer.instance,
                        actor=self.request.user,
                        request=self.request,
                    )
                changes = {
                    field: {
                        'before': before[field],
                        'after': getattr(serializer.instance, field),
                    }
                    for field in before
                }
                self._record_audit(
                    action=AuditAction.UPDATE,
                    instance=serializer.instance,
                    metadata={'changed_fields': sorted(serializer.validated_data)},
                    changes=changes,
                )
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages) from exc


COMMON_RESPONSES = {
    400: OpenApiResponse(description='Filtres ou données de mesure invalides.'),
    401: OpenApiResponse(description='Authentification JWT requise ou invalide.'),
    403: OpenApiResponse(description='Rôle, propriété ou affectation insuffisante.'),
    404: OpenApiResponse(description='Mesure inexistante ou inaccessible.'),
}


@extend_schema_view(
    list=extend_schema(
        tags=['Monitoring'],
        summary='Lister les mesures de tension accessibles',
        parameters=FILTER_PARAMETERS,
        responses={200: BloodPressureSerializer(many=True), **COMMON_RESPONSES},
    ),
    create=extend_schema(
        tags=['Monitoring'],
        summary='Enregistrer sa propre tension',
        description='Réservé au patient propriétaire. La source est forcée à MANUAL.',
        responses={201: BloodPressureSerializer, **COMMON_RESPONSES},
    ),
    retrieve=extend_schema(tags=['Monitoring'], responses={200: BloodPressureSerializer, **COMMON_RESPONSES}),
    partial_update=extend_schema(
        tags=['Monitoring'],
        summary='Corriger sa propre mesure de tension',
        description='Médecins en lecture seule. Le propriétaire et la source sont immuables.',
        responses={200: BloodPressureSerializer, **COMMON_RESPONSES},
    ),
)
class BloodPressureViewSet(
    MonitoringViewSetMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    model_class = BloodPressure
    serializer_class = BloodPressureSerializer
    queryset = BloodPressure.objects.none()


@extend_schema_view(
    list=extend_schema(
        tags=['Monitoring'],
        summary='Lister les mesures de glycémie accessibles',
        parameters=FILTER_PARAMETERS,
        responses={200: BloodGlucoseSerializer(many=True), **COMMON_RESPONSES},
    ),
    create=extend_schema(
        tags=['Monitoring'],
        summary='Enregistrer sa propre glycémie',
        description=(
            'Réservé au patient propriétaire. Unité obligatoire, sans conversion silencieuse. '
            'La source est forcée à MANUAL.'
        ),
        responses={201: BloodGlucoseSerializer, **COMMON_RESPONSES},
    ),
    retrieve=extend_schema(tags=['Monitoring'], responses={200: BloodGlucoseSerializer, **COMMON_RESPONSES}),
    partial_update=extend_schema(
        tags=['Monitoring'],
        summary='Corriger sa propre mesure de glycémie',
        description='Médecins en lecture seule. Le propriétaire et la source sont immuables.',
        responses={200: BloodGlucoseSerializer, **COMMON_RESPONSES},
    ),
)
class BloodGlucoseViewSet(
    MonitoringViewSetMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    model_class = BloodGlucose
    serializer_class = BloodGlucoseSerializer
    queryset = BloodGlucose.objects.none()
