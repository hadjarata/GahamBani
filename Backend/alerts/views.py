from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Case, IntegerField, Value, When
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from accounts.models import UserRole
from medical_audit.models import AuditAction, AuditDomain
from medical_audit.services import record_medical_audit_event
from profiles.selectors import active_patient_profiles_for_doctor

from .filters import parse_date_filter, parse_patient_id
from .models import AlertLevel, AlertStatus, MedicalAlert
from .pagination import AlertPagination
from .permissions import AlertPermission
from .serializers import AlertTransitionSerializer, MedicalAlertSerializer
from .services import acknowledge_alert, dismiss_alert, resolve_alert


FILTERS = [
    OpenApiParameter('status', OpenApiTypes.STR, enum=AlertStatus.values),
    OpenApiParameter('severity', OpenApiTypes.STR, enum=AlertLevel.values),
    OpenApiParameter('rule_code', OpenApiTypes.STR),
    OpenApiParameter('patient_id', OpenApiTypes.UUID, description='Médecins uniquement.'),
    OpenApiParameter('date_from', OpenApiTypes.STR),
    OpenApiParameter('date_to', OpenApiTypes.STR),
    OpenApiParameter('ordering', OpenApiTypes.STR, enum=['detected_at', '-detected_at', 'severity', '-severity']),
    OpenApiParameter('page', OpenApiTypes.INT),
    OpenApiParameter('page_size', OpenApiTypes.INT, description='Maximum 100.'),
]
RESPONSES = {
    400: OpenApiResponse(description='Filtre, transition ou motif invalide.'),
    401: OpenApiResponse(description='Authentification JWT requise.'),
    403: OpenApiResponse(description='Rôle ou affectation insuffisante.'),
    404: OpenApiResponse(description='Alerte inexistante ou inaccessible.'),
    405: OpenApiResponse(description='Méthode désactivée.'),
}


def drf_error(exc):
    return ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages)


@extend_schema_view(
    list=extend_schema(tags=['Alerts'], summary='Lister les alertes accessibles', parameters=FILTERS, responses={200: MedicalAlertSerializer(many=True), **RESPONSES}),
    retrieve=extend_schema(tags=['Alerts'], summary='Consulter une alerte', responses={200: MedicalAlertSerializer, **RESPONSES}),
)
class MedicalAlertViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    serializer_class = MedicalAlertSerializer
    permission_classes = (AlertPermission,)
    pagination_class = AlertPagination
    queryset = MedicalAlert.objects.none()
    http_method_names = ('get', 'patch', 'head', 'options')

    def get_queryset(self):
        user = self.request.user
        queryset = MedicalAlert.objects.select_related('patient__user', 'handled_by')
        if not user.is_authenticated or not user.is_active:
            return queryset.none()
        if user.role == UserRole.PATIENT:
            queryset = queryset.filter(patient__user=user, patient__user__is_active=True)
        elif user.role == UserRole.DOCTOR:
            queryset = queryset.filter(patient__in=active_patient_profiles_for_doctor(user))
        else:
            return queryset.none()

        patient_id = self.request.query_params.get('patient_id')
        if patient_id:
            if user.role != UserRole.DOCTOR:
                raise ValidationError({'patient_id': 'Ce filtre est réservé aux médecins.'})
            queryset = queryset.filter(patient_id=parse_patient_id(patient_id))
        status_value = self.request.query_params.get('status')
        if status_value:
            if status_value not in AlertStatus.values:
                raise ValidationError({'status': 'Statut invalide.'})
            queryset = queryset.filter(status=status_value)
        severity = self.request.query_params.get('severity')
        if severity:
            if severity not in AlertLevel.values:
                raise ValidationError({'severity': 'Gravité invalide.'})
            queryset = queryset.filter(niveau=severity)
        rule_code = self.request.query_params.get('rule_code')
        if rule_code:
            queryset = queryset.filter(rule_code=rule_code[:100])
        date_from_value = self.request.query_params.get('date_from')
        date_to_value = self.request.query_params.get('date_to')
        date_from = parse_date_filter(date_from_value) if date_from_value else None
        date_to = parse_date_filter(date_to_value, end_of_day=True) if date_to_value else None
        if date_from and date_to and date_from > date_to:
            raise ValidationError({'date_to': 'La date finale doit suivre la date initiale.'})
        if date_from:
            queryset = queryset.filter(detected_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(detected_at__lte=date_to)

        queryset = queryset.annotate(
            severity_rank=Case(
                When(niveau=AlertLevel.CRITICAL, then=Value(5)),
                When(niveau=AlertLevel.HIGH, then=Value(4)),
                When(niveau=AlertLevel.MEDIUM, then=Value(3)),
                When(niveau=AlertLevel.LOW, then=Value(2)),
                default=Value(1), output_field=IntegerField(),
            ),
            status_rank=Case(
                When(status=AlertStatus.OPEN, then=Value(1)),
                When(status=AlertStatus.ACKNOWLEDGED, then=Value(2)),
                default=Value(3), output_field=IntegerField(),
            ),
        )
        ordering = self.request.query_params.get('ordering')
        ordering_map = {
            'detected_at': ('detected_at', 'created_at'),
            '-detected_at': ('-detected_at', '-created_at'),
            'severity': ('severity_rank', '-detected_at'),
            '-severity': ('-severity_rank', '-detected_at'),
        }
        if ordering and ordering not in ordering_map:
            raise ValidationError({'ordering': 'Tri invalide.'})
        return queryset.order_by(*(ordering_map[ordering] if ordering else ('status_rank', '-severity_rank', '-detected_at', '-created_at')))

    def _audit_read(self, action, alert=None, result_count=None):
        patient = alert.patient if alert else (
            getattr(self.request.user, 'patient_profile', None)
            if self.request.user.role == UserRole.PATIENT else None
        )
        metadata = {'result_count': result_count} if result_count is not None else {}
        record_medical_audit_event(
            action=action, domain=AuditDomain.ALERTS,
            resource_type=MedicalAlert._meta.label_lower,
            resource_id=getattr(alert, 'pk', None), actor=self.request.user,
            patient=patient, request=self.request, metadata=metadata,
        )

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        self._audit_read(AuditAction.LIST, result_count=response.data['count'])
        return response

    def retrieve(self, request, *args, **kwargs):
        alert = self.get_object()
        response = Response(self.get_serializer(alert).data)
        self._audit_read(AuditAction.VIEW, alert=alert)
        return response

    def _transition(self, request, service, *, require_reason=False):
        alert = self.get_object()
        serializer = AlertTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get('reason', '')
        if require_reason and not reason.strip():
            raise ValidationError({'reason': 'Un motif est obligatoire.'})
        try:
            kwargs = {'doctor': request.user, 'request': request}
            if service is not acknowledge_alert:
                kwargs['reason'] = reason
            alert = service(alert, **kwargs)
        except DjangoValidationError as exc:
            raise drf_error(exc) from exc
        return Response(self.get_serializer(alert).data)

    @extend_schema(tags=['Alerts'], request=AlertTransitionSerializer, responses={200: MedicalAlertSerializer, **RESPONSES})
    @action(detail=True, methods=['patch'])
    def acknowledge(self, request, pk=None):
        return self._transition(request, acknowledge_alert)

    @extend_schema(tags=['Alerts'], request=AlertTransitionSerializer, responses={200: MedicalAlertSerializer, **RESPONSES})
    @action(detail=True, methods=['patch'])
    def resolve(self, request, pk=None):
        return self._transition(request, resolve_alert)

    @extend_schema(tags=['Alerts'], request=AlertTransitionSerializer, responses={200: MedicalAlertSerializer, **RESPONSES})
    @action(detail=True, methods=['patch'])
    def dismiss(self, request, pk=None):
        return self._transition(request, dismiss_alert, require_reason=True)
