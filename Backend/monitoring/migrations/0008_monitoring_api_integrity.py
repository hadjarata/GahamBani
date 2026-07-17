from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models
from django.db.models import F, Q


def merge_comment_and_notes(comment, notes):
    """Preserve both legacy fields while keeping notes as the single destination."""
    if not comment or comment == notes:
        return notes
    if not notes:
        return comment
    return f'{notes}\n\n{comment}'


def preserve_pressure_comments_and_validate(apps, schema_editor):
    blood_pressure = apps.get_model('monitoring', 'BloodPressure')
    blood_glucose = apps.get_model('monitoring', 'BloodGlucose')

    for measurement in blood_pressure.objects.exclude(commentaire='').iterator():
        merged_notes = merge_comment_and_notes(measurement.commentaire, measurement.notes)
        if merged_notes != measurement.notes:
            measurement.notes = merged_notes
            measurement.save(update_fields=['notes'])

    invalid_pressure = blood_pressure.objects.filter(
        Q(systolique__lt=40)
        | Q(systolique__gt=300)
        | Q(diastolique__lt=20)
        | Q(diastolique__gt=200)
        | Q(systolique__lte=F('diastolique'))
        | Q(frequence_cardiaque__lt=20)
        | Q(frequence_cardiaque__gt=250)
    ).exists()
    invalid_glucose = blood_glucose.objects.exclude(
        Q(unite='G_PER_L', valeur__gte=Decimal('0.1'), valeur__lte=Decimal('15'))
        | Q(unite='MG_PER_DL', valeur__gte=Decimal('10'), valeur__lte=Decimal('1500'))
    ).exists()
    invalid_hba1c = blood_glucose.objects.filter(
        Q(hba1c__lt=Decimal('1')) | Q(hba1c__gt=Decimal('25')),
    ).exists()
    if invalid_pressure or invalid_glucose or invalid_hba1c:
        raise RuntimeError(
            'Cannot add monitoring constraints: technically invalid legacy measurements exist.',
        )


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0007_alter_bloodglucose_hba1c_and_more'),
    ]

    operations = [
        migrations.RunPython(
            preserve_pressure_comments_and_validate,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name='bloodpressure',
            name='commentaire',
        ),
        migrations.AlterField(
            model_name='bloodpressure',
            name='frequence_cardiaque',
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(20),
                    django.core.validators.MaxValueValidator(250),
                ],
                verbose_name='heart rate',
            ),
        ),
        migrations.AlterField(
            model_name='bloodpressure',
            name='patient',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='blood_pressures',
                to='profiles.patientprofile',
                verbose_name='patient profile',
            ),
        ),
        migrations.AlterField(
            model_name='bloodglucose',
            name='patient',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='blood_glucoses',
                to='profiles.patientprofile',
                verbose_name='patient profile',
            ),
        ),
        migrations.RemoveIndex(
            model_name='bloodpressure',
            name='monitoring__patient_10354f_idx',
        ),
        migrations.RemoveIndex(
            model_name='bloodglucose',
            name='monitoring__patient_28000f_idx',
        ),
        migrations.AddIndex(
            model_name='bloodpressure',
            index=models.Index(
                fields=['patient', '-date_mesure'],
                name='mon_bp_patient_date_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='bloodglucose',
            index=models.Index(
                fields=['patient', '-date_mesure'],
                name='mon_bg_patient_date_idx',
            ),
        ),
        migrations.AddConstraint(
            model_name='bloodpressure',
            constraint=models.CheckConstraint(
                condition=Q(systolique__gte=40, systolique__lte=300),
                name='bp_systolic_technical_range',
            ),
        ),
        migrations.AddConstraint(
            model_name='bloodpressure',
            constraint=models.CheckConstraint(
                condition=Q(diastolique__gte=20, diastolique__lte=200),
                name='bp_diastolic_technical_range',
            ),
        ),
        migrations.AddConstraint(
            model_name='bloodpressure',
            constraint=models.CheckConstraint(
                condition=Q(systolique__gt=F('diastolique')),
                name='bp_systolic_above_diastolic',
            ),
        ),
        migrations.AddConstraint(
            model_name='bloodpressure',
            constraint=models.CheckConstraint(
                condition=(
                    Q(frequence_cardiaque__isnull=True)
                    | Q(frequence_cardiaque__gte=20, frequence_cardiaque__lte=250)
                ),
                name='bp_heart_rate_technical_range',
            ),
        ),
        migrations.AddConstraint(
            model_name='bloodglucose',
            constraint=models.CheckConstraint(
                condition=(
                    Q(
                        unite='G_PER_L',
                        valeur__gte=Decimal('0.1'),
                        valeur__lte=Decimal('15'),
                    )
                    | Q(
                        unite='MG_PER_DL',
                        valeur__gte=Decimal('10'),
                        valeur__lte=Decimal('1500'),
                    )
                ),
                name='bg_value_matches_unit_range',
            ),
        ),
        migrations.AddConstraint(
            model_name='bloodglucose',
            constraint=models.CheckConstraint(
                condition=(
                    Q(hba1c__isnull=True)
                    | Q(hba1c__gte=Decimal('1'), hba1c__lte=Decimal('25'))
                ),
                name='bg_hba1c_technical_range',
            ),
        ),
    ]
