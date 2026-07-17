import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class MeasurementSource(models.TextChoices):
    MANUAL = 'MANUAL', _('Manual')
    DEVICE = 'DEVICE', _('Device')
    CONNECTED_DEVICE = 'CONNECTED_DEVICE', _('Connected device')


class MeasurementContext(models.TextChoices):
    REST = 'REST', _('Rest')
    EXERCISE = 'EXERCISE', _('Exercise')
    STRESS = 'STRESS', _('Stress')
    ILLNESS = 'ILLNESS', _('Illness')


class BloodPressurePosition(models.TextChoices):
    SITTING = 'SITTING', _('Sitting')
    STANDING = 'STANDING', _('Standing')
    LYING = 'LYING', _('Lying')


class BloodPressureArm(models.TextChoices):
    LEFT = 'LEFT', _('Left')
    RIGHT = 'RIGHT', _('Right')
    BOTH = 'BOTH', _('Both')


class GlucoseUnit(models.TextChoices):
    G_PER_L = 'G_PER_L', _('g/L')
    MG_PER_DL = 'MG_PER_DL', _('mg/dL')


class GlucoseType(models.TextChoices):
    FASTING = 'FASTING', _('Fasting')
    POST_MEAL = 'POST_MEAL', _('Post meal')
    RANDOM = 'RANDOM', _('Random')


class MealContext(models.TextChoices):
    BEFORE_MEAL = 'BEFORE_MEAL', _('Before meal')
    AFTER_MEAL = 'AFTER_MEAL', _('After meal')
    NO_MEAL = 'NO_MEAL', _('No meal')


class SampleType(models.TextChoices):
    CAPILLARY = 'CAPILLARY', _('Capillary')
    LABORATORY = 'LABORATORY', _('Laboratory')
    SENSOR = 'SENSOR', _('Sensor')


class BloodPressure(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        'profiles.PatientProfile',
        on_delete=models.PROTECT,
        related_name='blood_pressures',
        verbose_name=_('patient profile'),
    )
    systolique = models.PositiveIntegerField(
        _('systolic'),
        validators=[MinValueValidator(40), MaxValueValidator(300)],
    )
    diastolique = models.PositiveIntegerField(
        _('diastolic'),
        validators=[MinValueValidator(20), MaxValueValidator(200)],
    )
    frequence_cardiaque = models.PositiveIntegerField(
        _('heart rate'),
        validators=[MinValueValidator(20), MaxValueValidator(250)],
        null=True,
        blank=True,
    )
    source_mesure = models.CharField(
        _('measurement source'),
        max_length=20,
        choices=MeasurementSource.choices,
        default=MeasurementSource.MANUAL,
    )
    measurement_context = models.CharField(
        _('measurement context'),
        max_length=20,
        choices=MeasurementContext.choices,
        default=MeasurementContext.REST,
    )
    position = models.CharField(
        _('position'),
        max_length=10,
        choices=BloodPressurePosition.choices,
        default=BloodPressurePosition.SITTING,
    )
    bras_utilise = models.CharField(
        _('arm used'),
        max_length=10,
        choices=BloodPressureArm.choices,
        default=BloodPressureArm.BOTH,
    )
    numero_mesure = models.PositiveIntegerField(
        _('measurement number'),
        null=True,
        blank=True,
    )
    notes = models.TextField(_('notes'), blank=True)
    date_mesure = models.DateTimeField(_('measurement date'))
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('blood pressure')
        verbose_name_plural = _('blood pressures')
        ordering = ['-date_mesure', '-created_at']
        indexes = [
            models.Index(
                fields=['patient', '-date_mesure'],
                name='mon_bp_patient_date_idx',
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(systolique__gte=40, systolique__lte=300),
                name='bp_systolic_technical_range',
            ),
            models.CheckConstraint(
                condition=models.Q(diastolique__gte=20, diastolique__lte=200),
                name='bp_diastolic_technical_range',
            ),
            models.CheckConstraint(
                condition=models.Q(systolique__gt=models.F('diastolique')),
                name='bp_systolic_above_diastolic',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(frequence_cardiaque__isnull=True)
                    | models.Q(frequence_cardiaque__gte=20, frequence_cardiaque__lte=250)
                ),
                name='bp_heart_rate_technical_range',
            ),
        ]

    def __str__(self):
        return f'BP {self.systolique}/{self.diastolique} for {self.patient.user.email} on {self.date_mesure:%Y-%m-%d %H:%M}'

    def clean(self):
        """Reject internally inconsistent data without hiding dangerous values."""
        super().clean()
        errors = {}
        if self.patient_id:
            from accounts.models import UserRole

            if self.patient.user.role != UserRole.PATIENT:
                errors['patient'] = _('The profile user must have the patient role.')
            elif not self.patient.user.is_active:
                errors['patient'] = _('The patient user must be active.')
        if self.systolique is not None and self.diastolique is not None:
            if self.systolique <= self.diastolique:
                errors['systolique'] = _('Systolic pressure must be higher than diastolic pressure.')
        if self.date_mesure and self.date_mesure > timezone.now():
            errors['date_mesure'] = _('The measurement date cannot be in the future.')
        if errors:
            raise ValidationError(errors)


class BloodGlucose(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        'profiles.PatientProfile',
        on_delete=models.PROTECT,
        related_name='blood_glucoses',
        verbose_name=_('patient profile'),
    )
    valeur = models.DecimalField(
        _('value'),
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(Decimal('1500'))],
    )
    unite = models.CharField(
        _('unit'),
        max_length=10,
        choices=GlucoseUnit.choices,
        default=GlucoseUnit.G_PER_L,
    )
    type_mesure = models.CharField(
        _('measurement type'),
        max_length=20,
        choices=GlucoseType.choices,
        default=GlucoseType.FASTING,
    )
    source_mesure = models.CharField(
        _('measurement source'),
        max_length=20,
        choices=MeasurementSource.choices,
        default=MeasurementSource.MANUAL,
    )
    hba1c = models.DecimalField(
        _('HbA1c'),
        max_digits=4,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('1')), MaxValueValidator(Decimal('25'))],
        null=True,
        blank=True,
    )
    contexte_repas = models.CharField(
        _('meal context'),
        max_length=20,
        choices=MealContext.choices,
        default=MealContext.BEFORE_MEAL,
    )
    heure_mesure = models.TimeField(_('measurement time'), null=True, blank=True)
    type_prelevement = models.CharField(
        _('sample type'),
        max_length=20,
        choices=SampleType.choices,
        default=SampleType.CAPILLARY,
    )
    notes = models.TextField(_('notes'), blank=True)
    date_mesure = models.DateTimeField(_('measurement date'))
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('blood glucose')
        verbose_name_plural = _('blood glucoses')
        ordering = ['-date_mesure', '-created_at']
        indexes = [
            models.Index(
                fields=['patient', '-date_mesure'],
                name='mon_bg_patient_date_idx',
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        unite=GlucoseUnit.G_PER_L,
                        valeur__gte=Decimal('0.1'),
                        valeur__lte=Decimal('15'),
                    )
                    | models.Q(
                        unite=GlucoseUnit.MG_PER_DL,
                        valeur__gte=Decimal('10'),
                        valeur__lte=Decimal('1500'),
                    )
                ),
                name='bg_value_matches_unit_range',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(hba1c__isnull=True)
                    | models.Q(hba1c__gte=Decimal('1'), hba1c__lte=Decimal('25'))
                ),
                name='bg_hba1c_technical_range',
            ),
        ]

    def __str__(self):
        return (
            f'Glucose {self.valeur} {self.get_unite_display()} '
            f'for {self.patient.user.email} on {self.date_mesure:%Y-%m-%d %H:%M}'
        )

    def clean(self):
        """Validate the consistency between measurement type and meal context."""
        super().clean()

        errors = {}

        if self.patient_id:
            from accounts.models import UserRole

            if self.patient.user.role != UserRole.PATIENT:
                errors['patient'] = _('The profile user must have the patient role.')
            elif not self.patient.user.is_active:
                errors['patient'] = _('The patient user must be active.')

        if self.unite == GlucoseUnit.G_PER_L and self.valeur is not None:
            if not Decimal('0.1') <= self.valeur <= Decimal('15'):
                errors['valeur'] = _('A value in g/L must be between 0.1 and 15.')
        elif self.unite == GlucoseUnit.MG_PER_DL and self.valeur is not None:
            if not Decimal('10') <= self.valeur <= Decimal('1500'):
                errors['valeur'] = _('A value in mg/dL must be between 10 and 1500.')

        if self.type_mesure == GlucoseType.FASTING and self.contexte_repas != MealContext.BEFORE_MEAL:
            errors['contexte_repas'] = _(
                'A fasting measurement must be recorded before a meal.'
            )

        if self.type_mesure == GlucoseType.POST_MEAL and self.contexte_repas != MealContext.AFTER_MEAL:
            errors['contexte_repas'] = _(
                'A post-meal measurement must be recorded after a meal.'
            )
        if self.date_mesure and self.date_mesure > timezone.now():
            errors['date_mesure'] = _('The measurement date cannot be in the future.')
        if errors:
            raise ValidationError(errors)
