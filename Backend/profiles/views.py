from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, PolymorphicProxySerializer, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import UserRole
from api_contract.exceptions import ProfileMissing
from medical_audit.models import AuditAction, AuditDomain
from medical_audit.services import record_medical_audit_event

from .models import DoctorProfile, PatientProfile
from .pagination import ProfilePagination
from .permissions import ActiveProfileAPIPermission, DoctorEndpointPermission, PatientEndpointPermission
from .selectors import active_assignments_for_doctor, active_assignments_for_patient, assignment_history_for_user
from .serializers import (
    AssignmentFilterSerializer, AssignmentHistorySerializer, DoctorMeResponseSerializer,
    DoctorProfileReadSerializer, DoctorProfileWriteSerializer, MyDoctorAssignmentSerializer,
    MyPatientAssignmentSerializer, PaginatedAssignmentsSerializer, PaginatedDoctorsSerializer,
    PaginatedPatientsSerializer, PatientMeResponseSerializer, PatientProfileReadSerializer,
    PatientProfileWriteSerializer, ProfileUserSerializer,
)
from .services import get_profile_completion, update_own_profile


RESPONSES = {
    400: OpenApiResponse(description='Paramètres ou champs invalides.'),
    401: OpenApiResponse(description='Authentification JWT requise.'),
    403: OpenApiResponse(description='Compte inactif ou rôle incorrect.'),
    404: OpenApiResponse(description='Profil métier manquant.'),
    405: OpenApiResponse(description='Méthode non autorisée.'),
}
LIST_PARAMETERS = [
    OpenApiParameter('date_from', OpenApiTypes.DATETIME, description='Début d’affectation minimal, ISO 8601.'),
    OpenApiParameter('date_to', OpenApiTypes.DATETIME, description='Début d’affectation maximal, ISO 8601.'),
    OpenApiParameter('ordering', OpenApiTypes.STR, enum=['assigned_at', '-assigned_at']),
    OpenApiParameter('page', OpenApiTypes.INT),
    OpenApiParameter('page_size', OpenApiTypes.INT, description='Maximum 100.'),
]


def profile_for_request(user):
    model = PatientProfile if user.role == UserRole.PATIENT else DoctorProfile
    try:
        return model.objects.select_related('user').get(user=user)
    except model.DoesNotExist as exc:
        raise ProfileMissing() from exc


def filter_assignments(queryset, params, *, allow_status):
    if allow_status and params.get('status'):
        queryset = queryset.filter(status=params['status'])
    if params.get('date_from'):
        queryset = queryset.filter(assigned_at__gte=params['date_from'])
    if params.get('date_to'):
        queryset = queryset.filter(assigned_at__lte=params['date_to'])
    return queryset.order_by(params['ordering'], '-created_at')


def audit(request, *, action, operation, patient=None, metadata=None):
    payload = {'operation': operation}
    payload.update(metadata or {})
    record_medical_audit_event(
        action=action, domain=AuditDomain.PROFILES, resource_type='profiles.api',
        actor=request.user, patient=patient, request=request, metadata=payload,
    )


class MeView(APIView):
    permission_classes = (ActiveProfileAPIPermission,)
    http_method_names = ('get', 'patch', 'head', 'options')

    def response_data(self, user, profile):
        profile_serializer = PatientProfileReadSerializer if user.role == UserRole.PATIENT else DoctorProfileReadSerializer
        return {
            'user': ProfileUserSerializer(user).data,
            'profile_type': user.role,
            'profile': profile_serializer(profile).data,
            'onboarding': get_profile_completion(user, profile),
        }

    @extend_schema(
        tags=['Profiles'], summary='Consulter son profil métier',
        description='Réponse patient ou médecin déterminée exclusivement depuis le JWT.',
        responses={200: PolymorphicProxySerializer(component_name='CurrentProfileResponse', serializers={'PATIENT': PatientMeResponseSerializer, 'DOCTOR': DoctorMeResponseSerializer}, resource_type_field_name='profile_type'), **RESPONSES},
    )
    def get(self, request):
        profile = profile_for_request(request.user)
        patient = profile if request.user.role == UserRole.PATIENT else None
        audit(request, action=AuditAction.VIEW, operation='VIEW_OWN_PROFILE', patient=patient)
        return Response(self.response_data(request.user, profile))

    @extend_schema(
        tags=['Profiles'], summary='Modifier son profil métier',
        description='Patient : date_naissance, sexe, poids, taille. Médecin : specialite, hopital, annees_experience. Propriétaire, rôle, numéro d’ordre et dates sont immuables.',
        request=PolymorphicProxySerializer(component_name='CurrentProfileUpdate', serializers=[PatientProfileWriteSerializer, DoctorProfileWriteSerializer], resource_type_field_name=None),
        responses={200: PolymorphicProxySerializer(component_name='UpdatedCurrentProfileResponse', serializers={'PATIENT': PatientMeResponseSerializer, 'DOCTOR': DoctorMeResponseSerializer}, resource_type_field_name='profile_type'), **RESPONSES},
    )
    def patch(self, request):
        profile = profile_for_request(request.user)
        serializer_class = PatientProfileWriteSerializer if request.user.role == UserRole.PATIENT else DoctorProfileWriteSerializer
        serializer = serializer_class(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        profile = update_own_profile(user=request.user, profile=profile, validated_data=serializer.validated_data)
        patient = profile if request.user.role == UserRole.PATIENT else None
        audit(
            request, action=AuditAction.UPDATE, operation='UPDATE_OWN_PROFILE', patient=patient,
            metadata={'changed_fields': sorted(serializer.validated_data)},
        )
        return Response(self.response_data(request.user, profile))


class AssignmentListView(APIView):
    permission_classes = (ActiveProfileAPIPermission,)
    serializer_class = AssignmentHistorySerializer
    allow_status = False
    operation = ''

    def get_queryset(self, user):
        raise NotImplementedError

    def parse(self, request):
        serializer = AssignmentFilterSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def get(self, request):
        profile = profile_for_request(request.user)
        params = self.parse(request)
        queryset = filter_assignments(self.get_queryset(request.user), params, allow_status=self.allow_status)
        paginator = ProfilePagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serialized = self.serializer_class(page, many=True, context={'request': request})
        patient = profile if request.user.role == UserRole.PATIENT else None
        audit(
            request, action=AuditAction.LIST, operation=self.operation, patient=patient,
            metadata={'result_count': paginator.page.paginator.count, 'status': params.get('status'), 'ordering': params['ordering']},
        )
        return paginator.get_paginated_response(serialized.data)


class MyPatientsView(AssignmentListView):
    permission_classes = (DoctorEndpointPermission,)
    serializer_class = MyPatientAssignmentSerializer
    operation = 'LIST_MY_PATIENTS'

    def get_queryset(self, user):
        return active_assignments_for_doctor(user)

    @extend_schema(tags=['Profiles'], summary='Lister mes patients actuellement affectés', parameters=LIST_PARAMETERS, responses={200: PaginatedPatientsSerializer, **RESPONSES})
    def get(self, request):
        return super().get(request)


class MyDoctorsView(AssignmentListView):
    permission_classes = (PatientEndpointPermission,)
    serializer_class = MyDoctorAssignmentSerializer
    operation = 'LIST_MY_DOCTORS'

    def get_queryset(self, user):
        return active_assignments_for_patient(user)

    @extend_schema(tags=['Profiles'], summary='Lister mes médecins actuellement affectés', parameters=LIST_PARAMETERS, responses={200: PaginatedDoctorsSerializer, **RESPONSES})
    def get(self, request):
        return super().get(request)


class AssignmentsView(AssignmentListView):
    serializer_class = AssignmentHistorySerializer
    allow_status = True
    operation = 'LIST_ASSIGNMENT_HISTORY'

    def get_queryset(self, user):
        return assignment_history_for_user(user)

    @extend_schema(tags=['Profiles'], summary='Consulter mon historique d’affectations', description='Une affectation terminée reste visible mais ne donne aucun accès médical.', parameters=LIST_PARAMETERS + [OpenApiParameter('status', OpenApiTypes.STR, enum=['ACTIVE', 'ENDED'])], responses={200: PaginatedAssignmentsSerializer, **RESPONSES})
    def get(self, request):
        return super().get(request)
