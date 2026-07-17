import mimetypes
from pathlib import Path

import django.db.models.deletion
import django.db.models.functions.text
import medical_records.validators
from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q


def validate_existing_data_and_populate_documents(apps, schema_editor):
    chronic_disease = apps.get_model('medical_records', 'ChronicDisease')
    allergy = apps.get_model('medical_records', 'Allergy')
    treatment = apps.get_model('medical_records', 'Treatment')
    medical_note = apps.get_model('medical_records', 'MedicalNote')
    medical_document = apps.get_model('medical_records', 'MedicalDocument')

    seen_diseases = set()
    for disease in chronic_disease.objects.filter(statut='ACTIVE').iterator():
        key = (disease.medical_record_id, disease.nom_maladie.strip().casefold())
        if not key[1] or key in seen_diseases:
            raise RuntimeError('Invalid or duplicate active chronic diseases must be reviewed.')
        seen_diseases.add(key)

    seen_allergies = set()
    for item in allergy.objects.filter(is_active=True).iterator():
        key = (item.medical_record_id, item.nom.strip().casefold())
        if not key[1] or key in seen_allergies:
            raise RuntimeError('Invalid or duplicate active allergies must be reviewed.')
        seen_allergies.add(key)

    invalid_treatment = treatment.objects.filter(
        Q(date_fin__lt=F('date_debut'))
        | Q(statut='ACTIVE', date_fin__isnull=False)
        | Q(statut__in=('STOPPED', 'COMPLETED'), date_fin__isnull=True)
    ).exists()
    invalid_note = any(
        not note.contenu.strip()
        for note in medical_note.objects.only('contenu').iterator()
    )
    if invalid_treatment or invalid_note:
        raise RuntimeError('Invalid legacy treatments or medical notes must be reviewed.')

    for document in medical_document.objects.select_related('uploaded_by').iterator():
        original_name = Path(document.fichier.name).name
        mime_type = mimetypes.guess_type(original_name)[0] or ''
        if document.uploaded_by_id and document.uploaded_by.role in ('PATIENT', 'DOCTOR'):
            upload_source = document.uploaded_by.role
        else:
            upload_source = 'LEGACY'
        medical_document.objects.filter(pk=document.pk).update(
            original_filename=original_name[:255],
            mime_type=mime_type[:100],
            upload_source=upload_source,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('medical_records', '0006_medicaldocument'),
        ('profiles', '0003_assignment_history_and_integrity'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='medicalrecord',
            name='unique_medical_record_patient',
        ),
        migrations.RemoveIndex(
            model_name='consultation',
            name='medical_rec_patient_59dda0_idx',
        ),
        migrations.RemoveIndex(
            model_name='medicaldocument',
            name='medical_rec_medical_a5c8b0_idx',
        ),
        migrations.RenameField(
            model_name='medicalrecord',
            old_name='allergies_text',
            new_name='legacy_allergies_text',
        ),
        migrations.RenameField(
            model_name='medicalrecord',
            old_name='maladies_chroniques',
            new_name='legacy_chronic_diseases_text',
        ),
        migrations.RenameField(
            model_name='medicalrecord',
            old_name='traitements_actuels',
            new_name='legacy_current_treatments_text',
        ),
        migrations.RenameField(
            model_name='medicalrecord',
            old_name='notes_medicales',
            new_name='legacy_medical_notes_text',
        ),
        migrations.AlterField(
            model_name='medicalrecord',
            name='legacy_allergies_text',
            field=models.TextField(blank=True, editable=False, verbose_name='legacy allergies'),
        ),
        migrations.AlterField(
            model_name='medicalrecord',
            name='legacy_chronic_diseases_text',
            field=models.TextField(
                blank=True,
                editable=False,
                verbose_name='legacy chronic diseases',
            ),
        ),
        migrations.AlterField(
            model_name='medicalrecord',
            name='legacy_current_treatments_text',
            field=models.TextField(
                blank=True,
                editable=False,
                verbose_name='legacy current treatments',
            ),
        ),
        migrations.AlterField(
            model_name='medicalrecord',
            name='legacy_medical_notes_text',
            field=models.TextField(
                blank=True,
                editable=False,
                verbose_name='legacy medical notes',
            ),
        ),
        migrations.AddField(
            model_name='allergy',
            name='is_active',
            field=models.BooleanField(db_index=True, default=True, verbose_name='active'),
        ),
        migrations.AddField(
            model_name='chronicdisease',
            name='date_resolution',
            field=models.DateField(blank=True, null=True, verbose_name='resolution date'),
        ),
        migrations.AddField(
            model_name='medicaldocument',
            name='file_size',
            field=models.PositiveBigIntegerField(blank=True, null=True, verbose_name='file size'),
        ),
        migrations.AddField(
            model_name='medicaldocument',
            name='mime_type',
            field=models.CharField(blank=True, max_length=100, verbose_name='MIME type'),
        ),
        migrations.AddField(
            model_name='medicaldocument',
            name='original_filename',
            field=models.CharField(blank=True, max_length=255, verbose_name='original filename'),
        ),
        migrations.AddField(
            model_name='medicaldocument',
            name='upload_source',
            field=models.CharField(
                choices=[('PATIENT', 'Patient'), ('DOCTOR', 'Doctor'), ('LEGACY', 'Legacy')],
                default='LEGACY',
                max_length=10,
                verbose_name='upload source',
            ),
        ),
        migrations.AddField(
            model_name='medicalnote',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, verbose_name='updated at'),
        ),
        migrations.AlterField(
            model_name='allergy',
            name='medical_record',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='allergies',
                to='medical_records.medicalrecord',
                verbose_name='medical record',
            ),
        ),
        migrations.AlterField(
            model_name='allergy',
            name='reaction',
            field=models.TextField(blank=True, verbose_name='reaction'),
        ),
        migrations.AlterField(
            model_name='chronicdisease',
            name='medical_record',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='chronic_diseases',
                to='medical_records.medicalrecord',
                verbose_name='medical record',
            ),
        ),
        migrations.AlterField(
            model_name='medicalnote',
            name='medical_record',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='medical_notes',
                to='medical_records.medicalrecord',
                verbose_name='medical record',
            ),
        ),
        migrations.AlterField(
            model_name='treatment',
            name='medical_record',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='treatments',
                to='medical_records.medicalrecord',
                verbose_name='medical record',
            ),
        ),
        migrations.AlterField(
            model_name='medicaldocument',
            name='medical_record',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='documents',
                to='medical_records.medicalrecord',
                verbose_name='medical record',
            ),
        ),
        migrations.AlterField(
            model_name='medicalrecord',
            name='patient',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='medical_record',
                to='profiles.patientprofile',
                verbose_name='patient profile',
            ),
        ),
        migrations.AlterField(
            model_name='treatment',
            name='prescrit_par',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='prescribed_treatments',
                to=settings.AUTH_USER_MODEL,
                verbose_name='prescribed by',
            ),
        ),
        migrations.AlterField(
            model_name='medicaldocument',
            name='uploaded_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='medical_documents',
                to=settings.AUTH_USER_MODEL,
                verbose_name='uploaded by',
            ),
        ),
        migrations.AlterField(
            model_name='medicaldocument',
            name='fichier',
            field=models.FileField(
                upload_to=medical_records.validators.medical_document_upload_to,
                validators=[medical_records.validators.validate_medical_document_file],
                verbose_name='file',
            ),
        ),
        migrations.AlterField(
            model_name='consultation',
            name='patient',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='consultations',
                to='profiles.patientprofile',
                verbose_name='patient profile',
            ),
        ),
        migrations.AlterField(
            model_name='consultation',
            name='medecin',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='consultations_medecin',
                to='profiles.doctorprofile',
                verbose_name='doctor profile',
            ),
        ),
        migrations.RunPython(
            validate_existing_data_and_populate_documents,
            migrations.RunPython.noop,
        ),
        migrations.AddIndex(
            model_name='consultation',
            index=models.Index(
                fields=['patient', '-date_consultation'],
                name='med_cons_patient_date_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='medicaldocument',
            index=models.Index(
                fields=['medical_record', '-date_document'],
                name='med_doc_record_date_idx',
            ),
        ),
        migrations.AddConstraint(
            model_name='allergy',
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower('nom'),
                models.F('medical_record'),
                condition=Q(is_active=True),
                name='unique_active_allergy_name',
            ),
        ),
        migrations.AddConstraint(
            model_name='chronicdisease',
            constraint=models.CheckConstraint(
                condition=(
                    Q(date_resolution__isnull=True)
                    | Q(date_diagnostic__isnull=True)
                    | Q(date_resolution__gte=F('date_diagnostic'))
                ),
                name='chronic_resolution_not_before_diagnosis',
            ),
        ),
        migrations.AddConstraint(
            model_name='chronicdisease',
            constraint=models.CheckConstraint(
                condition=(
                    Q(statut='ACTIVE', date_resolution__isnull=True)
                    | ~Q(statut='ACTIVE')
                ),
                name='chronic_active_without_resolution',
            ),
        ),
        migrations.AddConstraint(
            model_name='chronicdisease',
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower('nom_maladie'),
                models.F('medical_record'),
                condition=Q(statut='ACTIVE'),
                name='unique_active_chronic_disease_name',
            ),
        ),
        migrations.AddConstraint(
            model_name='treatment',
            constraint=models.CheckConstraint(
                condition=Q(date_fin__isnull=True) | Q(date_fin__gte=F('date_debut')),
                name='treatment_end_not_before_start',
            ),
        ),
        migrations.AddConstraint(
            model_name='treatment',
            constraint=models.CheckConstraint(
                condition=(
                    Q(statut='ACTIVE', date_fin__isnull=True)
                    | Q(statut__in=('STOPPED', 'COMPLETED'), date_fin__isnull=False)
                ),
                name='treatment_status_matches_end_date',
            ),
        ),
    ]
