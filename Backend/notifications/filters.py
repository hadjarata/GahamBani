from datetime import datetime, time

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.exceptions import ValidationError


def parse_date_filter(value, *, end=False):
    parsed = parse_datetime(value)
    if parsed is None:
        parsed_date = parse_date(value)
        if parsed_date is None:
            raise ValidationError('Les dates doivent respecter ISO 8601.')
        parsed = datetime.combine(parsed_date, time.max if end else time.min)
    return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
