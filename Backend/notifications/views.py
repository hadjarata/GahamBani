from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from medical_audit.models import AuditAction, AuditDomain
from medical_audit.services import record_medical_audit_event

from .filters import parse_date_filter
from .models import Notification, NotificationPriority, NotificationType
from .pagination import NotificationPagination
from .permissions import NotificationPermission
from .serializers import NotificationSerializer, ReadAllResultSerializer, UnreadCountSerializer
from .services import mark_all_notifications_as_read, mark_notification_as_read


FILTERS = [
    OpenApiParameter('is_read', OpenApiTypes.BOOL),
    OpenApiParameter('type', OpenApiTypes.STR, enum=NotificationType.values),
    OpenApiParameter('priority', OpenApiTypes.STR, enum=NotificationPriority.values),
    OpenApiParameter('date_from', OpenApiTypes.STR),
    OpenApiParameter('date_to', OpenApiTypes.STR),
    OpenApiParameter('ordering', OpenApiTypes.STR, enum=['created_at', '-created_at']),
    OpenApiParameter('page', OpenApiTypes.INT),
    OpenApiParameter('page_size', OpenApiTypes.INT, description='Maximum 100.'),
]
RESPONSES = {
    400: OpenApiResponse(description='Filtre invalide.'),
    401: OpenApiResponse(description='Authentification JWT requise.'),
    403: OpenApiResponse(description='Compte ou propriété insuffisante.'),
    404: OpenApiResponse(description='Notification inexistante ou inaccessible.'),
    405: OpenApiResponse(description='Méthode désactivée.'),
}


@extend_schema_view(
    list=extend_schema(tags=['Notifications'], parameters=FILTERS, responses={200: NotificationSerializer(many=True), **RESPONSES}),
    retrieve=extend_schema(tags=['Notifications'], responses={200: NotificationSerializer, **RESPONSES}),
)
class NotificationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    serializer_class = NotificationSerializer
    permission_classes = (NotificationPermission,)
    pagination_class = NotificationPagination
    queryset = Notification.objects.none()
    http_method_names = ('get', 'patch', 'head', 'options')

    def get_queryset(self):
        queryset = Notification.objects.select_related('recipient', 'patient')
        user = self.request.user
        if not user.is_authenticated or not user.is_active:
            return queryset.none()
        queryset = queryset.filter(recipient=user)
        is_read = self.request.query_params.get('is_read')
        if is_read is not None:
            normalized = is_read.lower()
            if normalized not in ('true', 'false'):
                raise ValidationError({'is_read': 'Valeur attendue : true ou false.'})
            queryset = queryset.filter(is_read=normalized == 'true')
        type_value = self.request.query_params.get('type')
        if type_value:
            if type_value not in NotificationType.values:
                raise ValidationError({'type': 'Type invalide.'})
            queryset = queryset.filter(type=type_value)
        priority = self.request.query_params.get('priority')
        if priority:
            if priority not in NotificationPriority.values:
                raise ValidationError({'priority': 'Priorité invalide.'})
            queryset = queryset.filter(priority=priority)
        date_from_value = self.request.query_params.get('date_from')
        date_to_value = self.request.query_params.get('date_to')
        date_from = parse_date_filter(date_from_value) if date_from_value else None
        date_to = parse_date_filter(date_to_value, end=True) if date_to_value else None
        if date_from and date_to and date_from > date_to:
            raise ValidationError({'date_to': 'La date finale doit suivre la date initiale.'})
        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)
        ordering = self.request.query_params.get('ordering', '-created_at')
        if ordering not in ('created_at', '-created_at'):
            raise ValidationError({'ordering': 'Tri invalide.'})
        return queryset.order_by(ordering, '-id')

    def retrieve(self, request, *args, **kwargs):
        notification = self.get_object()
        response = Response(self.get_serializer(notification).data)
        record_medical_audit_event(
            action=AuditAction.VIEW, domain=AuditDomain.NOTIFICATIONS,
            resource_type=Notification._meta.label_lower,
            resource_id=notification.pk, actor=request.user,
            patient=notification.patient, request=request,
            metadata={'event_code': notification.event_code},
        )
        return response

    @extend_schema(tags=['Notifications'], request=None, responses={200: NotificationSerializer, **RESPONSES})
    @action(detail=True, methods=['patch'], url_path='read')
    def read(self, request, pk=None):
        notification = self.get_object()
        notification = mark_notification_as_read(
            notification, recipient=request.user, request=request,
        )
        return Response(self.get_serializer(notification).data)

    @extend_schema(tags=['Notifications'], request=None, responses={200: ReadAllResultSerializer, **RESPONSES})
    @action(detail=False, methods=['patch'], url_path='read-all')
    def read_all(self, request):
        updated = mark_all_notifications_as_read(recipient=request.user, request=request)
        return Response({'updated_count': updated})

    @extend_schema(tags=['Notifications'], responses={200: UnreadCountSerializer, **RESPONSES})
    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({'unread_count': count})
