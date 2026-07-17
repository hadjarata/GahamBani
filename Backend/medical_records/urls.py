from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AllergyViewSet, ChronicDiseaseViewSet, ConsultationViewSet,
    MedicalDocumentViewSet, MedicalNoteViewSet, MedicalRecordDetailView,
    TreatmentViewSet,
)

app_name = 'medical-records'
router = DefaultRouter()
router.register('chronic-diseases', ChronicDiseaseViewSet, basename='chronic-disease')
router.register('allergies', AllergyViewSet, basename='allergy')
router.register('treatments', TreatmentViewSet, basename='treatment')
router.register('consultations', ConsultationViewSet, basename='consultation')
router.register('notes', MedicalNoteViewSet, basename='note')
router.register('documents', MedicalDocumentViewSet, basename='document')

urlpatterns = [path('record/', MedicalRecordDetailView.as_view(), name='record'), *router.urls]
