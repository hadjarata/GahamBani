import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q


def validate_existing_assignments(apps, schema_editor):
    assignment = apps.get_model('profiles', 'PatientDoctorAssignment')
    if assignment.objects.filter(
        ended_at__isnull=False,
        ended_at__lt=F('assigned_at'),
    ).exists():
        raise RuntimeError(
            'Cannot add assignment date constraint: an assignment ends before it starts.',
        )
    duplicate_active_pair = (
        assignment.objects.filter(status='ACTIVE')
        .values('patient_id', 'doctor_id')
        .annotate(row_count=models.Count('id'))
        .filter(row_count__gt=1)
        .exists()
    )
    if duplicate_active_pair:
        raise RuntimeError(
            'Cannot add active assignment uniqueness: duplicate active pairs exist.',
        )


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0002_patientdoctorassignment_doctorprofile_patients'),
    ]

    operations = [
        migrations.RunPython(validate_existing_assignments, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='patientprofile',
            name='unique_patient_profile_user',
        ),
        migrations.RemoveConstraint(
            model_name='doctorprofile',
            name='unique_doctor_profile_user',
        ),
        migrations.RemoveConstraint(
            model_name='patientdoctorassignment',
            name='unique_patient_doctor_assignment',
        ),
        migrations.AlterField(
            model_name='patientprofile',
            name='user',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='patient_profile',
                to=settings.AUTH_USER_MODEL,
                verbose_name='user',
            ),
        ),
        migrations.AlterField(
            model_name='doctorprofile',
            name='user',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='doctor_profile',
                to=settings.AUTH_USER_MODEL,
                verbose_name='user',
            ),
        ),
        migrations.AlterField(
            model_name='patientdoctorassignment',
            name='patient',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='doctor_assignments',
                to='profiles.patientprofile',
                verbose_name='patient profile',
            ),
        ),
        migrations.AlterField(
            model_name='patientdoctorassignment',
            name='doctor',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='patient_assignments',
                to='profiles.doctorprofile',
                verbose_name='doctor profile',
            ),
        ),
        migrations.AddConstraint(
            model_name='patientdoctorassignment',
            constraint=models.UniqueConstraint(
                condition=Q(status='ACTIVE'),
                fields=('patient', 'doctor'),
                name='unique_active_patient_doctor_assignment',
            ),
        ),
        migrations.AddConstraint(
            model_name='patientdoctorassignment',
            constraint=models.CheckConstraint(
                condition=Q(ended_at__isnull=True) | Q(ended_at__gte=F('assigned_at')),
                name='assignment_end_not_before_start',
            ),
        ),
        migrations.AddIndex(
            model_name='patientdoctorassignment',
            index=models.Index(
                fields=['patient', 'doctor', '-assigned_at'],
                name='prof_assign_pair_hist_idx',
            ),
        ),
    ]
