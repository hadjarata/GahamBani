import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserRole(models.TextChoices):
    PATIENT = 'PATIENT', _('Patient')
    DOCTOR = 'DOCTOR', _('Doctor')
    ADMIN = 'ADMIN', _('Admin')


class UserManager(BaseUserManager):
    """Custom manager for the custom User model."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('The Email field must be set'))
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_verified', False)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', UserRole.ADMIN)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_verified', True)

        if extra_fields.get('role') != UserRole.ADMIN:
            raise ValueError('Superuser must have role=ADMIN.')
        if not extra_fields.get('is_staff'):
            raise ValueError('Superuser must have is_staff=True.')
        if not extra_fields.get('is_superuser'):
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(_('first name'), max_length=150, blank=True)
    last_name = models.CharField(_('last name'), max_length=150, blank=True)
    email = models.EmailField(_('email address'), unique=True)
    phone = models.CharField(_('phone number'), max_length=30, blank=True)
    role = models.CharField(
        _('role'),
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.PATIENT,
    )
    is_verified = models.BooleanField(_('verified'), default=False)
    is_active = models.BooleanField(_('active'), default=True)
    is_staff = models.BooleanField(_('staff status'), default=False)
    token_version = models.PositiveIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        ordering = ['-created_at']

    def __str__(self):
        return self.email

    def clean(self):
        super().clean()
        self._validate_role_profile_compatibility()

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        role_may_change = update_fields is None or 'role' in update_fields
        if self.pk and not self._state.adding and role_may_change:
            previous_role = type(self).objects.filter(pk=self.pk).values_list(
                'role',
                flat=True,
            ).first()
            if previous_role is not None and previous_role != self.role:
                self._validate_role_profile_compatibility()
        return super().save(*args, **kwargs)

    def _validate_role_profile_compatibility(self):
        """Prevent silent role changes that orphan domain-specific profiles."""
        if not self.pk:
            return

        errors = []
        if self.role != UserRole.PATIENT and hasattr(self, 'patient_profile'):
            errors.append(_('A user with a patient profile must keep the patient role.'))
        if self.role != UserRole.DOCTOR and hasattr(self, 'doctor_profile'):
            errors.append(_('A user with a doctor profile must keep the doctor role.'))
        if errors:
            raise ValidationError({'role': errors})
