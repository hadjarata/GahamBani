import uuid

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
        on_delete=models.CASCADE,
        related_name='blood_pressures',
        verbose_name=_('patient profile'),
    )
    systolique = models.PositiveIntegerField(
        _('systolic'),
        validators=[MinValueValidator(90), MaxValueValidator(250)],
    )
    diastolique = models.PositiveIntegerField(
        _('diastolic'),
        validators=[MinValueValidator(40), MaxValueValidator(150)],
    )
    frequence_cardiaque = models.PositiveIntegerField(
        _('heart rate'),
        validators=[MinValueValidator(30), MaxValueValidator(220)],
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
    commentaire = models.TextField(_('comment'), blank=True)
    notes = models.TextField(_('notes'), blank=True)
    date_mesure = models.DateTimeField(_('measurement date'))
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('blood pressure')
        verbose_name_plural = _('blood pressures')
        ordering = ['-date_mesure', '-created_at']
        indexes = [
            models.Index(fields=['patient', 'date_mesure']),
        ]

    def __str__(self):
        return f'BP {self.systolique}/{self.diastolique} for {self.patient.user.email} on {self.date_mesure:%Y-%m-%d %H:%M}'


class BloodGlucose(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        'profiles.PatientProfile',
        on_delete=models.CASCADE,
        related_name='blood_glucoses',
        verbose_name=_('patient profile'),
    )
    valeur = models.DecimalField(
        _('value'),
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(0.1), MaxValueValidator(1000)],
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
        validators=[MinValueValidator(0), MaxValueValidator(20)],
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
            models.Index(fields=['patient', 'date_mesure']),
        ]

    def __str__(self):
        return (
            f'Glucose {self.valeur} {self.get_unite_display()} '
            f'for {self.patient.user.email} on {self.date_mesure:%Y-%m-%d %H:%M}'
        )

    def clean(self):
        """Validate the consistency between measurement type and meal context."""
        super().clean()

        if self.type_mesure == GlucoseType.FASTING and self.contexte_repas != MealContext.BEFORE_MEAL:
            raise ValidationError({
                'contexte_repas': _(
                    'A fasting measurement must be recorded before a meal.'
                ),
            })

        if self.type_mesure == GlucoseType.POST_MEAL and self.contexte_repas != MealContext.AFTER_MEAL:
            raise ValidationError({
                'contexte_repas': _(
                    'A post-meal measurement must be recorded after a meal.'
                ),
            })
