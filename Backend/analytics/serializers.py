from datetime import datetime, time, timedelta, timezone as datetime_timezone

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import serializers

from monitoring.models import MealContext


PERIOD_DAYS = {'7d': 7, '30d': 30, '90d': 90, '6m': 180, '1y': 365}
GRANULARITIES = ('raw', 'day', 'week', 'month')


def _parse_boundary(value, *, end=False):
    parsed = parse_datetime(value)
    if parsed is None:
        parsed_date = parse_date(value)
        if parsed_date is None:
            raise serializers.ValidationError('Format ISO 8601 attendu.')
        parsed = datetime.combine(parsed_date, time.max if end else time.min)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, datetime_timezone.utc)
    return parsed.astimezone(datetime_timezone.utc)


class AnalyticsQuerySerializer(serializers.Serializer):
    patient_id = serializers.UUIDField(required=False)
    period = serializers.ChoiceField(choices=(*PERIOD_DAYS, 'custom'), required=False)
    date_from = serializers.CharField(required=False)
    date_to = serializers.CharField(required=False)

    def validate(self, attrs):
        has_dates = 'date_from' in attrs or 'date_to' in attrs
        period = attrs.get('period')
        if period and period != 'custom' and has_dates:
            raise serializers.ValidationError('period ne peut pas être combiné avec date_from/date_to.')
        if period == 'custom' and not {'date_from', 'date_to'} <= attrs.keys():
            raise serializers.ValidationError('La période custom exige date_from et date_to.')
        if has_dates and not {'date_from', 'date_to'} <= attrs.keys():
            raise serializers.ValidationError('date_from et date_to doivent être fournis ensemble.')

        now = timezone.now().astimezone(datetime_timezone.utc)
        if has_dates:
            try:
                date_from = _parse_boundary(attrs['date_from'])
                date_to = _parse_boundary(attrs['date_to'], end=True)
            except serializers.ValidationError as exc:
                raise serializers.ValidationError({'period': exc.detail}) from exc
        else:
            days = PERIOD_DAYS.get(period or '30d', 30)
            date_to = now
            date_from = date_to - timedelta(days=days)
        if date_from > date_to:
            raise serializers.ValidationError({'date_to': 'La date finale doit suivre la date initiale.'})
        maximum = int(getattr(settings, 'ANALYTICS_MAX_PERIOD_DAYS', 365))
        if date_to - date_from > timedelta(days=maximum, seconds=1):
            raise serializers.ValidationError({'period': f'La période maximale est de {maximum} jours.'})
        attrs.update(date_from=date_from, date_to=date_to, period=period or ('custom' if has_dates else '30d'))
        return attrs


class SeriesQuerySerializer(AnalyticsQuerySerializer):
    granularity = serializers.ChoiceField(choices=GRANULARITIES, default='raw')
    ordering = serializers.ChoiceField(choices=('asc', 'desc'), default='asc')
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs['granularity'] != 'raw' and ('page' in attrs or 'page_size' in attrs):
            raise serializers.ValidationError('La pagination est réservée aux séries brutes.')
        return attrs


class GlucoseSeriesQuerySerializer(SeriesQuerySerializer):
    context = serializers.ChoiceField(choices=MealContext.values, required=False)


class Hba1cQuerySerializer(AnalyticsQuerySerializer):
    ordering = serializers.ChoiceField(choices=('asc', 'desc'), default='asc')
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)


class BloodPressurePointSerializer(serializers.Serializer):
    date = serializers.DateTimeField()
    systolic = serializers.FloatField()
    diastolic = serializers.FloatField()
    heart_rate = serializers.FloatField(allow_null=True)


class BloodPressureAggregateSerializer(serializers.Serializer):
    date = serializers.DateTimeField()
    count = serializers.IntegerField()
    systolic_avg = serializers.FloatField()
    systolic_min = serializers.FloatField()
    systolic_max = serializers.FloatField()
    diastolic_avg = serializers.FloatField()
    diastolic_min = serializers.FloatField()
    diastolic_max = serializers.FloatField()
    heart_rate_avg = serializers.FloatField(allow_null=True)
    heart_rate_min = serializers.FloatField(allow_null=True)
    heart_rate_max = serializers.FloatField(allow_null=True)


class GlucosePointSerializer(serializers.Serializer):
    date = serializers.DateTimeField()
    value = serializers.FloatField()
    unit = serializers.CharField()
    original_value = serializers.FloatField()
    original_unit = serializers.CharField()
    context = serializers.CharField()


class GlucoseAggregateSerializer(serializers.Serializer):
    date = serializers.DateTimeField()
    count = serializers.IntegerField()
    average = serializers.FloatField()
    minimum = serializers.FloatField()
    maximum = serializers.FloatField()


class Hba1cPointSerializer(serializers.Serializer):
    date = serializers.DateTimeField()
    value = serializers.FloatField()
    trend = serializers.ChoiceField(choices=('UP', 'DOWN', 'STABLE', 'INSUFFICIENT_DATA'))


class RawBloodPressureSeriesSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    unit = serializers.CharField()
    granularity = serializers.CharField()
    results = BloodPressurePointSerializer(many=True)


class RawGlucoseSeriesSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    unit = serializers.CharField()
    granularity = serializers.CharField()
    results = GlucosePointSerializer(many=True)


class AggregateBloodPressureSeriesSerializer(serializers.Serializer):
    unit = serializers.CharField()
    granularity = serializers.CharField()
    results = BloodPressureAggregateSerializer(many=True)


class AggregateGlucoseSeriesSerializer(serializers.Serializer):
    unit = serializers.CharField()
    granularity = serializers.CharField()
    results = GlucoseAggregateSerializer(many=True)


class Hba1cSeriesSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    unit = serializers.CharField()
    granularity = serializers.CharField()
    results = Hba1cPointSerializer(many=True)


class SummarySerializer(serializers.Serializer):
    period = serializers.DictField()
    latest_blood_pressure = serializers.DictField(allow_null=True)
    latest_glucose = serializers.DictField(allow_null=True)
    latest_hba1c = serializers.DictField(allow_null=True)
    measurement_counts = serializers.DictField()
    averages = serializers.DictField()
    alerts = serializers.DictField()
    last_measurement_at = serializers.DateTimeField(allow_null=True)
    disclaimer = serializers.CharField()


class AlertsAnalyticsSerializer(serializers.Serializer):
    period = serializers.DictField()
    total = serializers.IntegerField()
    by_status = serializers.DictField()
    by_severity = serializers.DictField()
    by_rule_code = serializers.DictField()
    evolution = serializers.ListField(child=serializers.DictField())


class TrendsSerializer(serializers.Serializer):
    window_days = serializers.IntegerField()
    minimum_measurements = serializers.IntegerField()
    indicators = serializers.DictField()
    disclaimer = serializers.CharField()
