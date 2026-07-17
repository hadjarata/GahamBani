import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .validators import medical_document_upload_to, validate_medical_document_file


class BloodGroupChoices(models.TextChoices):
    A_POSITIVE = 'A_POSITIVE', _('A+')
    A_NEGATIVE = 'A_NEGATIVE', _('A-')
    B_POSITIVE = 'B_POSITIVE', _('B+')
    B_NEGATIVE = 'B_NEGATIVE', _('B-')
    AB_POSITIVE = 'AB_POSITIVE', _('AB+')
    AB_NEGATIVE = 'AB_NEGATIVE', _('AB-')
    O_POSITIVE = 'O_POSITIVE', _('O+')
    O_NEGATIVE = 'O_NEGATIVE', _('O-')
    UNKNOWN = 'UNKNOWN', _('Unknown')


class SeverityChoices(models.TextChoices):
    LOW = 'LOW', _('Low')
    MEDIUM = 'MEDIUM', _('Medium')
    HIGH = 'HIGH', _('High')
    CRITICAL = 'CRITICAL', _('Critical')


class StatusChoices(models.TextChoices):
    ACTIVE = 'ACTIVE', _('Active')
    INACTIVE = 'INACTIVE', _('Inactive')
    CONTROLLED = 'CONTROLLED', _('Controlled')


class MedicalRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.OneToOneField(
        'profiles.PatientProfile',
        on_delete=models.PROTECT,
        related_name='medical_record',
        verbose_name=_('patient profile'),
    )
    groupe_sanguin = models.CharField(
        _('blood group'),
        max_length=20,
        choices=BloodGroupChoices.choices,
        default=BloodGroupChoices.UNKNOWN,
    )
    legacy_allergies_text = models.TextField(_('legacy allergies'), blank=True, editable=False)
    antecedents_familiaux = models.TextField(_('family medical history'), blank=True)
    legacy_chronic_diseases_text = models.TextField(
        _('legacy chronic diseases'), blank=True, editable=False,
    )
    legacy_current_treatments_text = models.TextField(
        _('legacy current treatments'), blank=True, editable=False,
    )
    legacy_medical_notes_text = models.TextField(
        _('legacy medical notes'), blank=True, editable=False,
    )
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('medical record')
        verbose_name_plural = _('medical records')
        ordering = ['-created_at']

    def __str__(self):
        patient_name = self.patient.user.email if self.patient and self.patient.user else str(self.patient)
        return f'Medical record ({self.groupe_sanguin}) for {patient_name}'

    def clean(self):
        super().clean()
        if self.patient_id:
            from accounts.models import UserRole

            if self.patient.user.role != UserRole.PATIENT:
                raise ValidationError({'patient': _('A medical record requires a patient profile.')})
            if not self.patient.user.is_active:
                raise ValidationError({'patient': _('The patient account must be active.')})


class ChronicDisease(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medical_record = models.ForeignKey(
        MedicalRecord,
        on_delete=models.PROTECT,
        related_name='chronic_diseases',
        verbose_name=_('medical record'),
    )
    nom_maladie = models.CharField(_('disease name'), max_length=255, db_index=True)
    date_diagnostic = models.DateField(_('diagnosis date'), null=True, blank=True)
    date_resolution = models.DateField(_('resolution date'), null=True, blank=True)
    gravite = models.CharField(
        _('severity'),
        max_length=10,
        choices=SeverityChoices.choices,
        default=SeverityChoices.MEDIUM,
    )
    statut = models.CharField(
        _('status'),
        max_length=12,
        choices=StatusChoices.choices,
        default=StatusChoices.ACTIVE,
        db_index=True,
    )
    notes = models.TextField(_('notes'), blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('chronic disease')
        verbose_name_plural = _('chronic diseases')
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(date_resolution__isnull=True)
                    | models.Q(date_diagnostic__isnull=True)
                    | models.Q(date_resolution__gte=models.F('date_diagnostic'))
                ),
                name='chronic_resolution_not_before_diagnosis',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(statut=StatusChoices.ACTIVE, date_resolution__isnull=True)
                    | ~models.Q(statut=StatusChoices.ACTIVE)
                ),
                name='chronic_active_without_resolution',
            ),
            models.UniqueConstraint(
                Lower('nom_maladie'),
                'medical_record',
                condition=models.Q(statut=StatusChoices.ACTIVE),
                name='unique_active_chronic_disease_name',
            ),
        ]

    def __str__(self):
        return f'{self.nom_maladie} ({self.gravite})'

    def clean(self):
        super().clean()
        self.nom_maladie = self.nom_maladie.strip()
        errors = {}
        if not self.nom_maladie:
            errors['nom_maladie'] = _('The disease name cannot be empty.')
        if self.date_resolution and self.date_diagnostic and self.date_resolution < self.date_diagnostic:
            errors['date_resolution'] = _('Resolution cannot precede diagnosis.')
        if self.statut == StatusChoices.ACTIVE and self.date_resolution:
            errors['date_resolution'] = _('An active disease cannot have a resolution date.')
        if errors:
            raise ValidationError(errors)


class Allergy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medical_record = models.ForeignKey(
        MedicalRecord,
        on_delete=models.PROTECT,
        related_name='allergies',
        verbose_name=_('medical record'),
    )
    nom = models.CharField(_('name'), max_length=255)
    gravite = models.CharField(
        _('severity'),
        max_length=10,
        choices=SeverityChoices.choices[:3],
        default=SeverityChoices.MEDIUM,
    )
    reaction = models.TextField(_('reaction'), blank=True)
    is_active = models.BooleanField(_('active'), default=True, db_index=True)
    notes = models.TextField(_('notes'), blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('allergy')
        verbose_name_plural = _('allergies')
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                Lower('nom'),
                'medical_record',
                condition=models.Q(is_active=True),
                name='unique_active_allergy_name',
            ),
        ]

    def __str__(self):
        return f'Allergy {self.nom} ({self.gravite}) for {self.medical_record.patient.user.email}'

    def clean(self):
        super().clean()
        self.nom = self.nom.strip()
        if not self.nom:
            raise ValidationError({'nom': _('The allergen name cannot be empty.')})


class MedicalNote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medical_record = models.ForeignKey(
        MedicalRecord,
        on_delete=models.PROTECT,
        related_name='medical_notes',
        verbose_name=_('medical record'),
    )
    auteur = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='medical_notes',
        verbose_name=_('author'),
    )
    contenu = models.TextField(_('content'))
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('medical note')
        verbose_name_plural = _('medical notes')
        ordering = ['-created_at']

    def __str__(self):
        return f'Note by {self.auteur.email} for {self.medical_record.patient.user.email} on {self.created_at:%Y-%m-%d}'

    def clean(self):
        super().clean()
        from accounts.models import UserRole

        self.contenu = self.contenu.strip()
        errors = {}
        if not self.contenu:
            errors['contenu'] = _('Medical note content cannot be empty.')
        if self.auteur_id and (
            self.auteur.role != UserRole.DOCTOR
            or not hasattr(self.auteur, 'doctor_profile')
        ):
            errors['auteur'] = _('A professional medical note requires a doctor author.')
        if errors:
            raise ValidationError(errors)


class TreatmentStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', _('Active')
    STOPPED = 'STOPPED', _('Stopped')
    COMPLETED = 'COMPLETED', _('Completed')


class Treatment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medical_record = models.ForeignKey(
        MedicalRecord,
        on_delete=models.PROTECT,
        related_name='treatments',
        verbose_name=_('medical record'),
    )
    nom_medicament = models.CharField(_('medication name'), max_length=255)
    description = models.TextField(_('description'), blank=True)
    dosage = models.CharField(_('dosage'), max_length=255)
    frequence = models.CharField(_('frequency'), max_length=255)
    voie_administration = models.CharField(_('administration route'), max_length=255, blank=True)
    date_debut = models.DateField(_('start date'))
    date_fin = models.DateField(_('end date'), null=True, blank=True)
    prescrit_par = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='prescribed_treatments',
        verbose_name=_('prescribed by'),
    )
    statut = models.CharField(
        _('status'),
        max_length=10,
        choices=TreatmentStatus.choices,
        default=TreatmentStatus.ACTIVE,
    )
    notes = models.TextField(_('notes'), blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('treatment')
        verbose_name_plural = _('treatments')
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_fin__isnull=True) | models.Q(date_fin__gte=models.F('date_debut')),
                name='treatment_end_not_before_start',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(statut=TreatmentStatus.ACTIVE, date_fin__isnull=True)
                    | models.Q(
                        statut__in=(TreatmentStatus.STOPPED, TreatmentStatus.COMPLETED),
                        date_fin__isnull=False,
                    )
                ),
                name='treatment_status_matches_end_date',
            ),
        ]

    def __str__(self):
        return f'{self.nom_medicament} ({self.statut}) for {self.medical_record.patient.user.email}'

    def clean(self):
        super().clean()
        from accounts.models import UserRole

        errors = {}
        for field in ('nom_medicament', 'dosage', 'frequence'):
            value = getattr(self, field).strip()
            setattr(self, field, value)
            if not value:
                errors[field] = _('This field cannot be empty.')
        if self.date_fin and self.date_fin < self.date_debut:
            errors['date_fin'] = _('The treatment end cannot precede its start.')
        if self.statut == TreatmentStatus.ACTIVE and self.date_fin:
            errors['date_fin'] = _('An active treatment cannot have an end date.')
        if self.statut != TreatmentStatus.ACTIVE and not self.date_fin:
            errors['date_fin'] = _('A stopped or completed treatment requires an end date.')
        if not self.prescrit_par_id or (
            self.prescrit_par.role != UserRole.DOCTOR
            or not hasattr(self.prescrit_par, 'doctor_profile')
        ):
            errors['prescrit_par'] = _('The prescriber must have a doctor profile.')
        if errors:
            raise ValidationError(errors)


class MedicalDocumentTypeChoices(models.TextChoices):
    ORDONNANCE = 'ORDONNANCE', _('Ordonnance')
    ANALYSE = 'ANALYSE', _('Analyse')
    RADIO = 'RADIO', _('Radio')
    COMPTE_RENDU = 'COMPTE_RENDU', _('Compte rendu')
    CERTIFICAT = 'CERTIFICAT', _('Certificat')
    AUTRE = 'AUTRE', _('Autre')


class DocumentUploadSource(models.TextChoices):
    PATIENT = 'PATIENT', _('Patient')
    DOCTOR = 'DOCTOR', _('Doctor')
    LEGACY = 'LEGACY', _('Legacy')


class MedicalDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medical_record = models.ForeignKey(
        MedicalRecord,
        on_delete=models.PROTECT,
        related_name='documents',
        verbose_name=_('medical record'),
    )
    titre = models.CharField(_('title'), max_length=255)
    type_document = models.CharField(
        _('document type'),
        max_length=20,
        choices=MedicalDocumentTypeChoices.choices,
        default=MedicalDocumentTypeChoices.AUTRE,
    )
    fichier = models.FileField(
        _('file'),
        upload_to=medical_document_upload_to,
        validators=[validate_medical_document_file],
    )
    original_filename = models.CharField(_('original filename'), max_length=255, blank=True)
    mime_type = models.CharField(_('MIME type'), max_length=100, blank=True)
    file_size = models.PositiveBigIntegerField(_('file size'), null=True, blank=True)
    upload_source = models.CharField(
        _('upload source'),
        max_length=10,
        choices=DocumentUploadSource.choices,
        default=DocumentUploadSource.LEGACY,
    )
    description = models.TextField(_('description'), blank=True)
    date_document = models.DateField(_('document date'))
    uploaded_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='medical_documents',
        verbose_name=_('uploaded by'),
    )
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('medical document')
        verbose_name_plural = _('medical documents')
        ordering = ['-date_document']
        indexes = [
            models.Index(
                fields=['medical_record', '-date_document'],
                name='med_doc_record_date_idx',
            ),
        ]

    def __str__(self):
        return f'{self.titre} ({self.get_type_document_display()}) for {self.medical_record.patient.user.email} on {self.date_document:%Y-%m-%d}'

    def clean(self):
        super().clean()
        self.titre = self.titre.strip()
        errors = {}
        if not self.titre:
            errors['titre'] = _('The document title cannot be empty.')
        if not self.fichier:
            errors['fichier'] = _('A document file is required.')
        if not self.uploaded_by_id:
            errors['uploaded_by'] = _('The uploader must be identified.')
        if errors:
            raise ValidationError(errors)


class Consultation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        'profiles.PatientProfile',
        on_delete=models.PROTECT,
        related_name='consultations',
        verbose_name=_('patient profile'),
    )
    medecin = models.ForeignKey(
        'profiles.DoctorProfile',
        on_delete=models.PROTECT,
        related_name='consultations_medecin',
        verbose_name=_('doctor profile'),
    )
    date_consultation = models.DateTimeField(_('consultation date'))
    motif = models.TextField(_('reason'))
    diagnostic = models.TextField(_('diagnosis'), blank=True)
    symptomes = models.TextField(_('symptoms'), blank=True)
    observations = models.TextField(_('observations'), blank=True)
    notes = models.TextField(_('notes'), blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('consultation')
        verbose_name_plural = _('consultations')
        ordering = ['-date_consultation']
        indexes = [
            models.Index(
                fields=['patient', '-date_consultation'],
                name='med_cons_patient_date_idx',
            ),
        ]

    def __str__(self):
        return f'Consultation on {self.date_consultation:%Y-%m-%d %H:%M} - {self.patient.user.email} - Dr {self.medecin.user.email}'

    def clean(self):
        super().clean()
        from accounts.models import UserRole

        self.motif = self.motif.strip()
        errors = {}
        if not self.motif:
            errors['motif'] = _('The consultation reason cannot be empty.')
        if self.date_consultation and self.date_consultation > timezone.now():
            errors['date_consultation'] = _('A completed consultation cannot be in the future.')
        if self.patient_id and (
            self.patient.user.role != UserRole.PATIENT
            or not self.patient.user.is_active
        ):
            errors['patient'] = _('An active patient profile is required.')
        if self.medecin_id and (
            self.medecin.user.role != UserRole.DOCTOR
            or not self.medecin.user.is_active
        ):
            errors['medecin'] = _('An active doctor profile is required.')
        if errors:
            raise ValidationError(errors)
