import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from api_contract.exceptions import Conflict, ProfileCreationFailed
from profiles.models import PatientProfile

from .models import User, UserRole


logger = logging.getLogger(__name__)


def register_patient(*, email, password, first_name, last_name, phone):
    """Create the public patient account and its empty profile as one unit."""
    normalized_email = User.objects.normalize_email(email).strip().lower()
    if User.objects.filter(email__iexact=normalized_email).exists():
        raise Conflict('Un compte utilise déjà cette adresse e-mail.')

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                email=normalized_email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                role=UserRole.PATIENT,
                is_active=True,
                is_verified=False,
            )
            user.full_clean(exclude=('password',))

            try:
                profile = PatientProfile(user=user)
                profile.full_clean()
                profile.save(force_insert=True)
            except IntegrityError:
                raise
            except Exception as exc:
                raise ProfileCreationFailed() from exc
    except IntegrityError as exc:
        raise Conflict('Un compte utilise déjà cette adresse e-mail.') from exc
    except ValidationError:
        raise

    return user, profile


@transaction.atomic
def set_user_password_and_revoke_tokens(user, raw_password, *, usable=True):
    """Atomically replace a password and invalidate every existing JWT."""
    locked_user = type(user)._default_manager.select_for_update().get(pk=user.pk)
    if usable:
        locked_user.set_password(raw_password)
    else:
        locked_user.set_unusable_password()

    locked_user.token_version = F('token_version') + 1
    locked_user.save(update_fields=('password', 'token_version', 'updated_at'))
    locked_user.refresh_from_db(fields=('password', 'token_version', 'updated_at'))

    # Keep the caller's instance coherent (serializers and Django admin both
    # continue using it after this service returns).
    user.password = locked_user.password
    user.token_version = locked_user.token_version
    user.updated_at = locked_user.updated_at
    return user


def send_password_reset_email(user):
    """Send reset credentials only to the active account's email address.

    Delivery failures are deliberately hidden from the public endpoint. The
    log records only the user identifier and exception type, never the token,
    reset URL, password, or email address.
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    separator = '&' if '?' in settings.FRONTEND_RESET_PASSWORD_URL else '?'
    reset_url = (
        f'{settings.FRONTEND_RESET_PASSWORD_URL}{separator}'
        f'{urlencode({"uid": uid, "token": token})}'
    )

    try:
        send_mail(
            subject='Réinitialisation de votre mot de passe GahamBani',
            message=(
                'Une demande de réinitialisation de votre mot de passe a été reçue.\n\n'
                f'Utilisez ce lien pour choisir un nouveau mot de passe :\n{reset_url}\n\n'
                'Si vous n’êtes pas à l’origine de cette demande, ignorez cet e-mail.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as exc:  # Email backends expose implementation-specific errors.
        logger.error(
            'Password reset email delivery failed for user_id=%s error_type=%s',
            user.pk,
            type(exc).__name__,
        )
        return False

    return True
