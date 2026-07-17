from datetime import datetime, time
from uuid import UUID

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.exceptions import ValidationError


def parse_temporal_filter(value, *, end_of_day=False):
    parsed = parse_datetime(value)
    if parsed is None:
        parsed_date = parse_date(value)
        if parsed_date is None:
            raise ValidationError('Les filtres de date doivent respecter le format ISO 8601.')
        parsed = datetime.combine(parsed_date, time.max if end_of_day else time.min)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def parse_patient_id(value):
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({'patient_id': 'Identifiant patient invalide.'}) from exc
