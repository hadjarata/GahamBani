from pathlib import Path

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from accounts.models import UserRole
from profiles.selectors import active_patient_profiles_for_doctor
from medical_audit.models import AuditAction, AuditDomain
from medical_audit.services import record_medical_audit_event

from .filters import parse_patient_id, parse_temporal_filter
from .models import Allergy, ChronicDisease, Consultation, MedicalDocument, MedicalNote, MedicalRecord, Treatment
from .pagination import MedicalRecordPagination
from .permissions import MedicalRecordPermission
from .serializers import (
    AllergySerializer, ChronicDiseaseSerializer, ConsultationSerializer,
    MedicalDocumentSerializer, MedicalNoteSerializer, MedicalRecordSerializer,
    TreatmentSerializer,
)
from .services import (
    add_allergy, add_chronic_disease, create_consultation, create_medical_note,
    create_treatment, update_clinical_object, upload_medical_document,
    patient_user_for_object,
)
from .validators import safe_original_filename


COMMON_PARAMETERS = [
    OpenApiParameter('patient_id', OpenApiTypes.UUID, description='Médecin uniquement; limité aux affectations actives.'),
    OpenApiParameter('date_from', OpenApiTypes.STR, description='Borne ISO 8601 inclusive.'),
    OpenApiParameter('date_to', OpenApiTypes.STR, description='Borne ISO 8601 inclusive.'),
    OpenApiParameter('status', OpenApiTypes.STR, description='Statut métier, si applicable.'),
    OpenApiParameter('ordering', OpenApiTypes.STR, description='Champ de date, avec préfixe - pour un tri décroissant.'),
    OpenApiParameter('page', OpenApiTypes.INT),
    OpenApiParameter('page_size', OpenApiTypes.INT, description='Maximum 100.'),
]
COMMON_RESPONSES = {
    400: OpenApiResponse(description='Données ou filtres invalides.'),
    401: OpenApiResponse(description='Authentification JWT requise.'),
    403: OpenApiResponse(description='Rôle, propriété ou affectation active insuffisante.'),
    404: OpenApiResponse(description='Ressource inexistante ou inaccessible.'),
}


def api_validation_error(exc):
    if hasattr(exc, 'message_dict'):
        return ValidationError(exc.message_dict)
    return ValidationError(getattr(exc, 'messages', str(exc)))


class MedicalRecordDetailView(APIView):
    permission_classes = (MedicalRecordPermission,)

    @extend_schema(
        tags=['Medical records'], summary='Consulter le dossier médical accessible',
        parameters=[OpenApiParameter('patient_id', OpenApiTypes.UUID, description='Obligatoire pour un médecin.')],
        responses={200: MedicalRecordSerializer, **COMMON_RESPONSES},
    )
    def get(self, request):
        user = request.user
        queryset = MedicalRecord.objects.select_related('patient__user')
        if user.role == UserRole.PATIENT:
            queryset = queryset.filter(patient__user=user)
        elif user.role == UserRole.DOCTOR:
            patient_id = request.query_params.get('patient_id')
            if not patient_id:
                raise ValidationError({'patient_id': 'Ce filtre est obligatoire pour un médecin.'})
            queryset = queryset.filter(
                patient_id=parse_patient_id(patient_id),
                patient__in=active_patient_profiles_for_doctor(user),
            )
        else:
            queryset = queryset.none()
        record = get_object_or_404(queryset)
        self.check_object_permissions(request, record)
        response = Response(MedicalRecordSerializer(record, context={'request': request}).data)
        record_medical_audit_event(
            action=AuditAction.VIEW,
            domain=AuditDomain.MEDICAL_RECORDS,
            resource_type=MedicalRecord._meta.label_lower,
            resource_id=record.pk,
            actor=request.user,
            patient=record.patient,
            request=request,
        )
        return response


class ClinicalViewSetMixin:
    permission_classes = (MedicalRecordPermission,)
    pagination_class = MedicalRecordPagination
    http_method_names = ('get', 'post', 'patch', 'head', 'options')
    status_field = None
    allowed_statuses = ()

    audit_value_fields = ()

    def _record_audit(self, *, action, instance=None, metadata=None, changes=None):
        patient = None
        if instance is not None:
            patient = patient_user_for_object(instance).patient_profile
        elif self.request.user.role == UserRole.PATIENT:
            patient = getattr(self.request.user, 'patient_profile', None)
        return record_medical_audit_event(
            action=action,
            domain=AuditDomain.MEDICAL_RECORDS,
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
        self._record_audit(
            action=AuditAction.LIST,
            metadata={
                'result_count': response.data.get('count', len(response.data)),
                'source': 'API',
            },
        )
        return response

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        response = Response(self.get_serializer(instance).data)
        metadata = {}
        if isinstance(instance, MedicalDocument):
            metadata = {
                'document_type': instance.type_document,
                'file_size': instance.file_size,
                'extension': Path(instance.original_filename).suffix.lower(),
            }
        self._record_audit(
            action=AuditAction.VIEW,
            instance=instance,
            metadata=metadata,
        )
        return response

    def get_queryset(self):
        user = self.request.user
        queryset = self.model_class.objects.select_related(*self.select_related)
        if not user.is_authenticated or not user.is_active:
            return queryset.none()
        if user.role == UserRole.PATIENT:
            queryset = queryset.filter(**{self.patient_user_lookup: user})
        elif user.role == UserRole.DOCTOR:
            queryset = queryset.filter(**{
                f'{self.patient_profile_lookup}__in': active_patient_profiles_for_doctor(user),
            })
        else:
            return queryset.none()

        patient_id = self.request.query_params.get('patient_id')
        if patient_id:
            if user.role != UserRole.DOCTOR:
                raise ValidationError({'patient_id': 'Ce filtre est réservé aux médecins.'})
            queryset = queryset.filter(**{self.patient_id_lookup: parse_patient_id(patient_id)})

        date_from_value = self.request.query_params.get('date_from')
        date_to_value = self.request.query_params.get('date_to')
        date_from = parse_temporal_filter(date_from_value) if date_from_value else None
        date_to = parse_temporal_filter(date_to_value, end_of_day=True) if date_to_value else None
        if date_from and date_to and date_from > date_to:
            raise ValidationError({'date_to': 'La borne finale doit suivre la borne initiale.'})
        if date_from:
            queryset = queryset.filter(**{f'{self.date_field}__gte': date_from})
        if date_to:
            queryset = queryset.filter(**{f'{self.date_field}__lte': date_to})

        status_value = self.request.query_params.get('status')
        if status_value:
            if not self.status_field or status_value not in self.allowed_statuses:
                raise ValidationError({'status': 'Statut non pris en charge pour cette ressource.'})
            queryset = queryset.filter(**{self.status_field: status_value})
        ordering = self.request.query_params.get('ordering', f'-{self.date_field}')
        if ordering not in (self.date_field, f'-{self.date_field}'):
            raise ValidationError({'ordering': f'Tri autorisé : {self.date_field} ou -{self.date_field}.'})
        return queryset.order_by(ordering, '-created_at')

    def perform_create(self, serializer):
        data = dict(serializer.validated_data)
        patient_id = data.pop('patient_id', None)
        try:
            with transaction.atomic():
                serializer.instance = self.create_service(
                    doctor=self.request.user, patient_id=patient_id, data=data,
                )
                metadata = {
                    'changed_fields': sorted(data),
                    'source': 'API',
                }
                if isinstance(serializer.instance, MedicalNote):
                    metadata['text_length'] = len(serializer.instance.contenu)
                self._record_audit(
                    action=AuditAction.CREATE,
                    instance=serializer.instance,
                    metadata=metadata,
                )
        except DjangoValidationError as exc:
            raise api_validation_error(exc) from exc

    def perform_update(self, serializer):
        data = dict(serializer.validated_data)
        data.pop('patient_id', None)
        before = {
            field: getattr(serializer.instance, field)
            for field in self.audit_value_fields
            if field in data
        }
        try:
            with transaction.atomic():
                serializer.instance = update_clinical_object(
                    serializer.instance, doctor=self.request.user, data=data,
                )
                changes = {
                    field: {
                        'before': before[field],
                        'after': getattr(serializer.instance, field),
                    }
                    for field in before
                }
                metadata = {'changed_fields': sorted(data)}
                if isinstance(serializer.instance, MedicalNote) and 'contenu' in data:
                    metadata['text_length'] = len(serializer.instance.contenu)
                self._record_audit(
                    action=AuditAction.UPDATE,
                    instance=serializer.instance,
                    metadata=metadata,
                    changes=changes,
                )
        except DjangoValidationError as exc:
            raise api_validation_error(exc) from exc


def clinical_schema(serializer, label):
    return extend_schema_view(
        list=extend_schema(tags=['Medical records'], summary=f'Lister les {label} accessibles', parameters=COMMON_PARAMETERS, responses={200: serializer(many=True), **COMMON_RESPONSES}),
        create=extend_schema(tags=['Medical records'], summary=f'Créer {label}', description='Médecin actuellement affecté uniquement.', responses={201: serializer, **COMMON_RESPONSES}),
        retrieve=extend_schema(tags=['Medical records'], responses={200: serializer, **COMMON_RESPONSES}),
        partial_update=extend_schema(tags=['Medical records'], description='Médecin actuellement affecté uniquement; propriétaire et auteur immuables.', responses={200: serializer, **COMMON_RESPONSES}),
    )


@clinical_schema(ChronicDiseaseSerializer, 'une maladie chronique')
class ChronicDiseaseViewSet(ClinicalViewSetMixin, mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, GenericViewSet):
    model_class = ChronicDisease; serializer_class = ChronicDiseaseSerializer
    queryset = ChronicDisease.objects.none(); create_service = staticmethod(add_chronic_disease)
    select_related = ('medical_record__patient__user',); patient_user_lookup = 'medical_record__patient__user'
    patient_profile_lookup = 'medical_record__patient'; patient_id_lookup = 'medical_record__patient_id'
    date_field = 'created_at'; status_field = 'statut'; allowed_statuses = ('ACTIVE', 'INACTIVE', 'CONTROLLED')
    audit_value_fields = ('date_diagnostic', 'date_resolution', 'gravite', 'statut')


@clinical_schema(AllergySerializer, 'une allergie')
class AllergyViewSet(ClinicalViewSetMixin, mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, GenericViewSet):
    model_class = Allergy; serializer_class = AllergySerializer; queryset = Allergy.objects.none()
    create_service = staticmethod(add_allergy); select_related = ('medical_record__patient__user',)
    patient_user_lookup = 'medical_record__patient__user'; patient_profile_lookup = 'medical_record__patient'
    patient_id_lookup = 'medical_record__patient_id'; date_field = 'created_at'; status_field = 'is_active'
    allowed_statuses = ('true', 'false')
    audit_value_fields = ('gravite', 'is_active')

    def get_queryset(self):
        queryset = super().get_queryset()
        value = self.request.query_params.get('status')
        return queryset.filter(is_active=value == 'true') if value else queryset


@clinical_schema(TreatmentSerializer, 'un traitement')
class TreatmentViewSet(ClinicalViewSetMixin, mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, GenericViewSet):
    model_class = Treatment; serializer_class = TreatmentSerializer; queryset = Treatment.objects.none()
    create_service = staticmethod(create_treatment); select_related = ('medical_record__patient__user', 'prescrit_par')
    patient_user_lookup = 'medical_record__patient__user'; patient_profile_lookup = 'medical_record__patient'
    patient_id_lookup = 'medical_record__patient_id'; date_field = 'date_debut'; status_field = 'statut'
    allowed_statuses = ('ACTIVE', 'STOPPED', 'COMPLETED')
    audit_value_fields = ('date_debut', 'date_fin', 'statut')


@clinical_schema(ConsultationSerializer, 'une consultation')
class ConsultationViewSet(ClinicalViewSetMixin, mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, GenericViewSet):
    model_class = Consultation; serializer_class = ConsultationSerializer; queryset = Consultation.objects.none()
    create_service = staticmethod(create_consultation); select_related = ('patient__user', 'medecin__user')
    patient_user_lookup = 'patient__user'; patient_profile_lookup = 'patient'; patient_id_lookup = 'patient_id'
    date_field = 'date_consultation'
    audit_value_fields = ('date_consultation',)


@clinical_schema(MedicalNoteSerializer, 'une note médicale')
class MedicalNoteViewSet(ClinicalViewSetMixin, mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, GenericViewSet):
    model_class = MedicalNote; serializer_class = MedicalNoteSerializer; queryset = MedicalNote.objects.none()
    create_service = staticmethod(create_medical_note); select_related = ('medical_record__patient__user', 'auteur')
    patient_user_lookup = 'medical_record__patient__user'; patient_profile_lookup = 'medical_record__patient'
    patient_id_lookup = 'medical_record__patient_id'; date_field = 'created_at'


@extend_schema_view(
    list=extend_schema(tags=['Medical records'], parameters=COMMON_PARAMETERS, responses={200: MedicalDocumentSerializer(many=True), **COMMON_RESPONSES}),
    create=extend_schema(tags=['Medical records'], summary='Téléverser un document médical', request={'multipart/form-data': MedicalDocumentSerializer}, responses={201: MedicalDocumentSerializer, **COMMON_RESPONSES}),
    retrieve=extend_schema(tags=['Medical records'], responses={200: MedicalDocumentSerializer, **COMMON_RESPONSES}),
)
class MedicalDocumentViewSet(ClinicalViewSetMixin, mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    model_class = MedicalDocument; serializer_class = MedicalDocumentSerializer; queryset = MedicalDocument.objects.none()
    patient_upload_allowed = True; select_related = ('medical_record__patient__user', 'uploaded_by')
    patient_user_lookup = 'medical_record__patient__user'; patient_profile_lookup = 'medical_record__patient'
    patient_id_lookup = 'medical_record__patient_id'; date_field = 'date_document'; status_field = 'type_document'
    allowed_statuses = ('ORDONNANCE', 'ANALYSE', 'RADIO', 'COMPTE_RENDU', 'CERTIFICAT', 'AUTRE')

    def perform_create(self, serializer):
        data = dict(serializer.validated_data)
        patient_id = data.pop('patient_id', None)
        try:
            with transaction.atomic():
                serializer.instance = upload_medical_document(
                    actor=self.request.user, patient_id=patient_id, data=data,
                )
                document = serializer.instance
                self._record_audit(
                    action=AuditAction.CREATE,
                    instance=document,
                    metadata={
                        'changed_fields': sorted(key for key in data if key != 'fichier'),
                        'document_type': document.type_document,
                        'file_size': document.file_size,
                        'extension': Path(document.original_filename).suffix.lower(),
                        'download_filename': safe_original_filename(document.original_filename),
                        'source': 'API',
                    },
                )
        except DjangoValidationError as exc:
            raise api_validation_error(exc) from exc

    @extend_schema(
        tags=['Medical records'], summary='Télécharger une pièce jointe protégée',
        responses={(200, 'application/octet-stream'): OpenApiTypes.BINARY, **COMMON_RESPONSES},
    )
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        document = self.get_object()
        response = FileResponse(
            document.fichier.open('rb'), as_attachment=True,
            filename=safe_original_filename(document.original_filename),
            content_type=document.mime_type or 'application/octet-stream',
        )
        response['X-Content-Type-Options'] = 'nosniff'
        self._record_audit(
            action=AuditAction.DOWNLOAD,
            instance=document,
            metadata={
                'document_type': document.type_document,
                'file_size': document.file_size,
                'extension': Path(document.original_filename).suffix.lower(),
                'download_filename': safe_original_filename(document.original_filename),
            },
        )
        return response
