from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings

from monitoring.models import BloodGlucose, BloodPressure, GlucoseUnit

from .models import AlertLevel, AlertType


@dataclass(frozen=True)
class RuleResult:
    rule_code: str
    rule_name: str
    alert_type: str
    severity: str
    message: str
    observed_value: str
    unit: str
    metadata: dict = field(default_factory=dict)


class AlertRule:
    code = ''
    name = ''
    description = ''
    severity = AlertLevel.INFO
    alert_type = AlertType.GENERAL
    measurement_model = None

    @property
    def thresholds(self):
        return settings.ALERT_RULE_THRESHOLDS

    def result(self, *, message, observed_value, unit, metadata=None):
        return RuleResult(
            rule_code=self.code, rule_name=self.name, alert_type=self.alert_type,
            severity=self.severity, message=message,
            observed_value=str(observed_value), unit=unit, metadata=metadata or {},
        )


class BloodPressureVeryLowRule(AlertRule):
    code = 'BP_VERY_LOW'; name = 'Tension très basse'; alert_type = AlertType.HYPERTENSION
    description = 'Signale une mesure sous les seuils bas configurés.'
    severity = AlertLevel.CRITICAL; measurement_model = BloodPressure

    def evaluate(self, measurement):
        config = self.thresholds['blood_pressure']
        if measurement.systolique <= config['very_low_systolic'] or measurement.diastolique <= config['very_low_diastolic']:
            return self.result(
                message='Mesure de tension sous un seuil de signalement configuré; une attention professionnelle peut être nécessaire.',
                observed_value=f'{measurement.systolique}/{measurement.diastolique}', unit='mmHg',
                metadata={'triggered_parameters': [name for name, triggered in (('systolique', measurement.systolique <= config['very_low_systolic']), ('diastolique', measurement.diastolique <= config['very_low_diastolic'])) if triggered]},
            )


class BloodPressureElevatedRule(AlertRule):
    code = 'BP_ELEVATED'; name = 'Tension élevée'; alert_type = AlertType.HYPERTENSION
    description = 'Signale une mesure au-dessus des seuils élevés configurés.'
    severity = AlertLevel.HIGH; measurement_model = BloodPressure

    def evaluate(self, measurement):
        config = self.thresholds['blood_pressure']
        elevated = measurement.systolique >= config['elevated_systolic'] or measurement.diastolique >= config['elevated_diastolic']
        very_high = measurement.systolique >= config['very_high_systolic'] or measurement.diastolique >= config['very_high_diastolic']
        if elevated and not very_high:
            return self.result(
                message='Mesure de tension au-dessus d’un seuil de signalement configuré.',
                observed_value=f'{measurement.systolique}/{measurement.diastolique}', unit='mmHg',
                metadata={'triggered_parameters': ['blood_pressure']},
            )


class BloodPressureVeryHighRule(AlertRule):
    code = 'BP_VERY_HIGH'; name = 'Tension très élevée'; alert_type = AlertType.HYPERTENSION
    description = 'Signale une mesure très au-dessus des seuils configurés.'
    severity = AlertLevel.CRITICAL; measurement_model = BloodPressure

    def evaluate(self, measurement):
        config = self.thresholds['blood_pressure']
        if measurement.systolique >= config['very_high_systolic'] or measurement.diastolique >= config['very_high_diastolic']:
            return self.result(
                message='Mesure de tension très au-dessus d’un seuil de signalement configuré; une attention rapide peut être nécessaire.',
                observed_value=f'{measurement.systolique}/{measurement.diastolique}', unit='mmHg',
                metadata={'triggered_parameters': ['blood_pressure']},
            )


class BloodPressureCriticalCombinationRule(AlertRule):
    code = 'BP_CRITICAL_COMBINATION'; name = 'Combinaison tensionnelle critique'
    alert_type = AlertType.HYPERTENSION; severity = AlertLevel.CRITICAL
    description = 'Signale une combinaison systolique et diastolique au-dessus des deux seuils critiques.'
    measurement_model = BloodPressure

    def evaluate(self, measurement):
        config = self.thresholds['blood_pressure']
        if measurement.systolique >= config['critical_systolic'] and measurement.diastolique >= config['critical_diastolic']:
            return self.result(
                message='Les deux paramètres de tension dépassent les seuils combinés de signalement configurés.',
                observed_value=f'{measurement.systolique}/{measurement.diastolique}', unit='mmHg',
                metadata={'triggered_parameters': ['systolique', 'diastolique']},
            )


class HeartRateLowRule(AlertRule):
    code = 'HR_LOW'; name = 'Fréquence cardiaque basse'; alert_type = AlertType.HEART_RATE
    description = 'Signale une fréquence sous le seuil configuré.'
    severity = AlertLevel.HIGH; measurement_model = BloodPressure

    def evaluate(self, measurement):
        value = measurement.frequence_cardiaque
        threshold = self.thresholds['heart_rate']['low']
        if value is not None and value <= threshold:
            return self.result(message='Fréquence cardiaque sous un seuil de signalement configuré.', observed_value=value, unit='bpm', metadata={'triggered_parameters': ['frequence_cardiaque']})


class HeartRateHighRule(AlertRule):
    code = 'HR_HIGH'; name = 'Fréquence cardiaque élevée'; alert_type = AlertType.HEART_RATE
    description = 'Signale une fréquence au-dessus du seuil configuré.'
    severity = AlertLevel.HIGH; measurement_model = BloodPressure

    def evaluate(self, measurement):
        value = measurement.frequence_cardiaque
        threshold = self.thresholds['heart_rate']['high']
        if value is not None and value >= threshold:
            return self.result(message='Fréquence cardiaque au-dessus d’un seuil de signalement configuré.', observed_value=value, unit='bpm', metadata={'triggered_parameters': ['frequence_cardiaque']})


def glucose_to_mg_dl(value, unit):
    value = Decimal(value)
    if unit == GlucoseUnit.MG_PER_DL:
        return value
    if unit == GlucoseUnit.G_PER_L:
        return value * Decimal('100')
    raise ValueError('Unsupported glucose unit.')


class GlucoseRule(AlertRule):
    alert_type = AlertType.DIABETES; measurement_model = BloodGlucose

    def glucose_result(self, measurement, message):
        return self.result(
            message=message, observed_value=measurement.valeur,
            unit=measurement.unite,
            metadata={'normalized_mg_dl': str(glucose_to_mg_dl(measurement.valeur, measurement.unite)), 'measurement_context': measurement.type_mesure},
        )


class GlucoseVeryLowRule(GlucoseRule):
    code = 'GLUCOSE_VERY_LOW'; name = 'Glycémie très basse'; severity = AlertLevel.CRITICAL
    description = 'Signale une glycémie normalisée sous le seuil bas configuré.'

    def evaluate(self, measurement):
        if glucose_to_mg_dl(measurement.valeur, measurement.unite) <= Decimal(str(self.thresholds['blood_glucose']['very_low_mg_dl'])):
            return self.glucose_result(measurement, 'Glycémie sous un seuil de signalement configuré; une attention rapide peut être nécessaire.')


class GlucoseHighRule(GlucoseRule):
    code = 'GLUCOSE_HIGH'; name = 'Glycémie élevée'; severity = AlertLevel.HIGH
    description = 'Signale une glycémie normalisée dans la plage élevée configurée.'

    def evaluate(self, measurement):
        value = glucose_to_mg_dl(measurement.valeur, measurement.unite)
        config = self.thresholds['blood_glucose']
        if Decimal(str(config['high_mg_dl'])) <= value < Decimal(str(config['very_high_mg_dl'])):
            return self.glucose_result(measurement, 'Glycémie au-dessus d’un seuil de signalement configuré.')


class GlucoseVeryHighRule(GlucoseRule):
    code = 'GLUCOSE_VERY_HIGH'; name = 'Glycémie très élevée'; severity = AlertLevel.CRITICAL
    description = 'Signale une glycémie normalisée au-dessus du seuil très élevé configuré.'

    def evaluate(self, measurement):
        if glucose_to_mg_dl(measurement.valeur, measurement.unite) >= Decimal(str(self.thresholds['blood_glucose']['very_high_mg_dl'])):
            return self.glucose_result(measurement, 'Glycémie très au-dessus d’un seuil de signalement configuré; une attention rapide peut être nécessaire.')


class HbA1cHighRule(GlucoseRule):
    code = 'HBA1C_HIGH'; name = 'HbA1c élevée'; severity = AlertLevel.HIGH
    description = 'Signale une HbA1c au-dessus du seuil configurable.'

    def evaluate(self, measurement):
        threshold = Decimal(str(self.thresholds['blood_glucose']['hba1c_high_percent']))
        if measurement.hba1c is not None and Decimal(measurement.hba1c) >= threshold:
            return self.result(message='HbA1c au-dessus d’un seuil de signalement configuré.', observed_value=measurement.hba1c, unit='percent', metadata={'triggered_parameters': ['hba1c']})


RULES = (
    BloodPressureVeryLowRule(), BloodPressureElevatedRule(), BloodPressureVeryHighRule(),
    BloodPressureCriticalCombinationRule(), HeartRateLowRule(), HeartRateHighRule(),
    GlucoseVeryLowRule(), GlucoseHighRule(), GlucoseVeryHighRule(), HbA1cHighRule(),
)


def rules_for_measurement(measurement):
    return tuple(rule for rule in RULES if isinstance(measurement, rule.measurement_model))
