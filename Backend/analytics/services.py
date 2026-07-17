from decimal import Decimal

from django.conf import settings
from django.db.models import Avg, Case, Count, DecimalField, F, Max, Min, Q, Value, When
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek

from alerts.models import AlertLevel, AlertStatus
from monitoring.models import GlucoseUnit

from .selectors import alert_queryset, blood_glucose_queryset, blood_pressure_queryset


CANONICAL_GLUCOSE_UNIT = GlucoseUnit.MG_PER_DL
DISCLAIMER = 'Statistiques descriptives uniquement : elles ne constituent ni un diagnostic ni une recommandation médicale.'
TRUNCATIONS = {'day': TruncDay, 'week': TruncWeek, 'month': TruncMonth}


def normalized_glucose_expression():
    return Case(
        When(unite=GlucoseUnit.G_PER_L, then=F('valeur') * Value(Decimal('100'))),
        default=F('valeur'),
        output_field=DecimalField(max_digits=10, decimal_places=4),
    )


def normalize_glucose(value, unit):
    value = Decimal(value)
    return value * Decimal('100') if unit == GlucoseUnit.G_PER_L else value


def _period_payload(date_from, date_to):
    return {'date_from': date_from, 'date_to': date_to, 'inclusive': True, 'timezone': 'UTC'}


def blood_pressure_series(queryset, granularity):
    if granularity == 'raw':
        return queryset.values(
            date=F('date_mesure'), systolic=F('systolique'), diastolic=F('diastolique'),
            heart_rate=F('frequence_cardiaque'),
        )
    trunc = TRUNCATIONS[granularity]
    return queryset.annotate(date=trunc('date_mesure')).values('date').annotate(
        count=Count('id'),
        systolic_avg=Avg('systolique'), systolic_min=Min('systolique'), systolic_max=Max('systolique'),
        diastolic_avg=Avg('diastolique'), diastolic_min=Min('diastolique'), diastolic_max=Max('diastolique'),
        heart_rate_avg=Avg('frequence_cardiaque'), heart_rate_min=Min('frequence_cardiaque'), heart_rate_max=Max('frequence_cardiaque'),
    )


def blood_glucose_series(queryset, granularity):
    queryset = queryset.annotate(normalized_value=normalized_glucose_expression())
    if granularity == 'raw':
        return queryset.values(
            date=F('date_mesure'), value=F('normalized_value'), original_value=F('valeur'),
            original_unit=F('unite'), context=F('contexte_repas'),
        )
    trunc = TRUNCATIONS[granularity]
    return queryset.annotate(date=trunc('date_mesure')).values('date').annotate(
        count=Count('id'), average=Avg('normalized_value'),
        minimum=Min('normalized_value'), maximum=Max('normalized_value'),
    )


def calculate_summary(*, patient, date_from, date_to):
    pressure = blood_pressure_queryset(patient=patient, date_from=date_from, date_to=date_to)
    glucose = blood_glucose_queryset(patient=patient, date_from=date_from, date_to=date_to)
    alerts = alert_queryset(patient=patient, date_from=date_from, date_to=date_to)
    latest_pressure = pressure.order_by('-date_mesure').values(
        'systolique', 'diastolique', 'frequence_cardiaque', 'date_mesure',
    ).first()
    latest_glucose = glucose.annotate(normalized=normalized_glucose_expression()).order_by('-date_mesure').values(
        'normalized', 'valeur', 'unite', 'date_mesure',
    ).first()
    latest_hba1c = glucose.filter(hba1c__isnull=False).order_by('-date_mesure').values('hba1c', 'date_mesure').first()
    pressure_stats = pressure.aggregate(
        count=Count('id'), systolic=Avg('systolique'), diastolic=Avg('diastolique'),
        heart_rate=Avg('frequence_cardiaque'), last=Max('date_mesure'),
    )
    glucose_stats = glucose.annotate(normalized=normalized_glucose_expression()).aggregate(
        count=Count('id'), average=Avg('normalized'), last=Max('date_mesure'),
    )
    alert_stats = alerts.aggregate(
        total=Count('id'),
        open=Count('id', filter=Q(status=AlertStatus.OPEN)),
        high_or_critical=Count('id', filter=Q(niveau__in=(AlertLevel.HIGH, AlertLevel.CRITICAL))),
    )
    last_dates = [value for value in (pressure_stats['last'], glucose_stats['last']) if value]
    return {
        'period': _period_payload(date_from, date_to),
        'latest_blood_pressure': None if not latest_pressure else {
            'systolic': latest_pressure['systolique'], 'diastolic': latest_pressure['diastolique'],
            'heart_rate': latest_pressure['frequence_cardiaque'], 'measured_at': latest_pressure['date_mesure'], 'unit': 'mmHg',
        },
        'latest_glucose': None if not latest_glucose else {
            'value': latest_glucose['normalized'], 'unit': CANONICAL_GLUCOSE_UNIT,
            'original_value': latest_glucose['valeur'], 'original_unit': latest_glucose['unite'],
            'measured_at': latest_glucose['date_mesure'],
        },
        'latest_hba1c': None if not latest_hba1c else {'value': latest_hba1c['hba1c'], 'unit': '%', 'measured_at': latest_hba1c['date_mesure']},
        'measurement_counts': {'blood_pressure': pressure_stats['count'], 'blood_glucose': glucose_stats['count']},
        'averages': {
            'systolic': pressure_stats['systolic'], 'diastolic': pressure_stats['diastolic'],
            'heart_rate': pressure_stats['heart_rate'], 'blood_glucose': glucose_stats['average'],
            'blood_pressure_unit': 'mmHg', 'heart_rate_unit': 'bpm', 'blood_glucose_unit': CANONICAL_GLUCOSE_UNIT,
        },
        'alerts': alert_stats,
        'last_measurement_at': max(last_dates) if last_dates else None,
        'disclaimer': DISCLAIMER,
    }


def calculate_alert_analytics(*, patient, date_from, date_to):
    queryset = alert_queryset(patient=patient, date_from=date_from, date_to=date_to)
    by_status = {value: 0 for value in AlertStatus.values}
    by_severity = {value: 0 for value in AlertLevel.values}
    by_status.update({row['status']: row['count'] for row in queryset.values('status').annotate(count=Count('id'))})
    by_severity.update({row['niveau']: row['count'] for row in queryset.values('niveau').annotate(count=Count('id'))})
    by_rule = {row['rule_code']: row['count'] for row in queryset.values('rule_code').annotate(count=Count('id')).order_by('rule_code')}
    evolution = list(queryset.annotate(date=TruncDay('detected_at')).values('date').annotate(count=Count('id')).order_by('date'))
    return {
        'period': _period_payload(date_from, date_to), 'total': queryset.count(),
        'by_status': by_status, 'by_severity': by_severity, 'by_rule_code': by_rule,
        'evolution': evolution,
    }


def _trend(current, previous, *, minimum, stable_threshold):
    if current['count'] < minimum or previous['count'] < minimum:
        return {'direction': 'INSUFFICIENT_DATA', 'current_average': current['average'], 'previous_average': previous['average'], 'absolute_change': None, 'percentage_change': None, 'message': 'Données insuffisantes.'}
    current_avg, previous_avg = Decimal(str(current['average'])), Decimal(str(previous['average']))
    delta = current_avg - previous_avg
    direction = 'STABLE' if abs(delta) <= stable_threshold else ('UP' if delta > 0 else 'DOWN')
    percentage = None if previous_avg == 0 else (delta / previous_avg) * Decimal('100')
    messages = {'UP': 'La moyenne a augmenté.', 'DOWN': 'La moyenne a diminué.', 'STABLE': 'La moyenne est stable.'}
    return {'direction': direction, 'current_average': current_avg, 'previous_average': previous_avg, 'absolute_change': delta, 'percentage_change': percentage, 'message': messages[direction]}


def calculate_trends(*, patient, date_to):
    from datetime import timedelta

    days = int(getattr(settings, 'ANALYTICS_TREND_WINDOW_DAYS', 7))
    minimum = int(getattr(settings, 'ANALYTICS_TREND_MIN_MEASUREMENTS', 2))
    stable = Decimal(str(getattr(settings, 'ANALYTICS_TREND_STABLE_THRESHOLD', '0.01')))
    current_from, previous_from = date_to - timedelta(days=days), date_to - timedelta(days=days * 2)
    pressure = blood_pressure_queryset(patient=patient, date_from=previous_from, date_to=date_to)
    glucose = blood_glucose_queryset(patient=patient, date_from=previous_from, date_to=date_to).annotate(normalized=normalized_glucose_expression())

    def windows(queryset, field):
        current = queryset.filter(date_mesure__gte=current_from).aggregate(count=Count(field), average=Avg(field))
        previous = queryset.filter(date_mesure__gte=previous_from, date_mesure__lt=current_from).aggregate(count=Count(field), average=Avg(field))
        return _trend(current, previous, minimum=minimum, stable_threshold=stable)

    return {
        'window_days': days, 'minimum_measurements': minimum,
        'indicators': {
            'systolic': windows(pressure, 'systolique'), 'diastolic': windows(pressure, 'diastolique'),
            'heart_rate': windows(pressure, 'frequence_cardiaque'), 'blood_glucose': windows(glucose, 'normalized'),
        },
        'disclaimer': DISCLAIMER,
    }


def hba1c_points(queryset):
    points, previous = [], None
    for measurement in queryset:
        value = measurement.hba1c
        trend = 'INSUFFICIENT_DATA' if previous is None else ('STABLE' if value == previous else ('UP' if value > previous else 'DOWN'))
        points.append({'date': measurement.date_mesure, 'value': value, 'trend': trend})
        previous = value
    return points
