from datetime import datetime, time
from uuid import UUID

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.exceptions import ValidationError


def parse_date_filter(value, *, end_of_day=False):
    parsed = parse_datetime(value)
    if parsed is None:
        parsed_date = parse_date(value)
        if parsed_date is None:
            raise ValidationError('Les dates doivent respecter ISO 8601.')
        parsed = datetime.combine(parsed_date, time.max if end_of_day else time.min)
    return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed


def parse_patient_id(value):
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError({'patient_id': 'Identifiant patient invalide.'}) from exc
