from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from api_contract.exceptions import Conflict, ProfileCreationFailed
from medical_audit.models import MedicalAuditEvent
from profiles.models import PatientProfile

from .admin import UserAdmin
from .admin_forms import TokenRevokingAdminPasswordChangeForm
from .models import User, UserRole
from .permissions import IsAdmin, IsDoctor, IsDoctorOrAdmin, IsOwner, IsPatient
from .tokens import TOKEN_VERSION_CLAIM, VersionedRefreshToken
from .services import register_patient


THROTTLE_TEST_REST_FRAMEWORK = {
    **settings.REST_FRAMEWORK,
    'DEFAULT_THROTTLE_RATES': {
        'anon': '50/minute',
        'user': '50/minute',
        'login': '2/minute',
        'registration': '2/minute',
        'password_reset': '2/minute',
        'password_reset_confirm': '2/minute',
        'token_refresh': '2/minute',
    },
}


class PatientRegistrationTests(APITestCase):
    password = 'SafeRegistration2026!'

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def payload(self, **overrides):
        data = {
            'first_name': 'Aminata',
            'last_name': 'Traore',
            'email': 'NEW.PATIENT@EXAMPLE.COM',
            'phone': '+22370000000',
            'password': self.password,
            'password_confirm': self.password,
        }
        data.update(overrides)
        return data

    def test_v1_registration_atomically_creates_patient_and_incomplete_profile(self):
        response = self.client.post(
            '/api/v1/auth/register/',
            self.payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(set(response.data), {'detail', 'user', 'profile', 'onboarding'})
        self.assertEqual(
            set(response.data['user']),
            {'id', 'email', 'role'},
        )
        self.assertEqual(response.data['user']['email'], 'new.patient@example.com')
        self.assertEqual(response.data['user']['role'], UserRole.PATIENT)
        self.assertEqual(response.data['profile']['profile_type'], UserRole.PATIENT)
        self.assertFalse(response.data['onboarding']['is_complete'])
        self.assertEqual(response.data['onboarding']['completion_percentage'], 43)
        self.assertEqual(
            set(response.data['onboarding']['missing_fields']),
            {'date_naissance', 'sexe', 'poids', 'taille'},
        )
        for forbidden in ('access', 'refresh', 'password', 'is_staff', 'is_verified'):
            self.assertNotIn(forbidden, str(response.data).lower())

        user = User.objects.get(email='new.patient@example.com')
        profile = PatientProfile.objects.get(user=user)
        self.assertEqual(user.role, UserRole.PATIENT)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_verified)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password(self.password))
        self.assertNotEqual(user.password, self.password)
        self.assertEqual(str(profile.pk), response.data['profile']['id'])
        self.assertIsNone(profile.date_naissance)
        self.assertIsNone(profile.sexe)
        self.assertIsNone(profile.poids)
        self.assertIsNone(profile.taille)
        self.assertEqual(MedicalAuditEvent.objects.count(), 0)

    def test_registered_patient_can_login_read_profile_and_complete_onboarding(self):
        self.client.post('/api/v1/auth/register/', self.payload(), format='json')
        login = self.client.post(
            '/api/v1/auth/login/',
            {'email': 'new.patient@example.com', 'password': self.password},
            format='json',
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        incomplete = self.client.get('/api/v1/profiles/me/')
        self.assertEqual(incomplete.status_code, status.HTTP_200_OK)
        self.assertFalse(incomplete.data['onboarding']['is_complete'])
        completed = self.client.patch(
            '/api/v1/profiles/me/',
            {
                'date_naissance': '1995-05-20',
                'sexe': 'FEMALE',
                'poids': '65.50',
                'taille': '168.00',
            },
            format='json',
        )
        self.assertEqual(completed.status_code, status.HTTP_200_OK)
        self.assertTrue(completed.data['onboarding']['is_complete'])
        self.assertEqual(completed.data['onboarding']['completion_percentage'], 100)
        self.assertEqual(completed.data['onboarding']['missing_fields'], [])

    def test_public_registration_rejects_every_sensitive_or_privileged_field(self):
        forbidden_fields = {
            'role': UserRole.DOCTOR,
            'is_staff': True,
            'is_superuser': True,
            'is_verified': True,
            'is_active': False,
            'groups': [],
            'user_permissions': [],
            'token_version': 99,
        }
        for index, (field, value) in enumerate(forbidden_fields.items()):
            with self.subTest(field=field):
                response = self.client.post(
                    '/api/v1/auth/register/',
                    self.payload(
                        email=f'forbidden-{index}@example.com',
                        **{field: value},
                    ),
                    format='json',
                    REMOTE_ADDR=f'198.51.100.{index + 1}',
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data['code'], 'validation_error')
                self.assertIn(field, response.data['errors'])
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(PatientProfile.objects.count(), 0)

    def test_invalid_registration_data_never_creates_partial_rows(self):
        invalid_payloads = (
            self.payload(email='not-an-email'),
            self.payload(
                email='mismatch@example.com',
                password_confirm='DifferentPassword2026!',
            ),
            self.payload(
                email='weak@example.com',
                password='123',
                password_confirm='123',
            ),
            {
                key: value
                for key, value in self.payload(email='missing@example.com').items()
                if key != 'phone'
            },
        )
        for index, payload in enumerate(invalid_payloads):
            with self.subTest(index=index):
                response = self.client.post(
                    '/api/v1/auth/register/',
                    payload,
                    format='json',
                    REMOTE_ADDR=f'203.0.113.{index + 1}',
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data['code'], 'validation_error')
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(PatientProfile.objects.count(), 0)

    def test_v1_duplicate_email_is_a_stable_conflict_and_creates_no_orphan(self):
        first = self.client.post('/api/v1/auth/register/', self.payload(), format='json')
        duplicate = self.client.post(
            '/api/v1/auth/register/',
            self.payload(email='new.patient@example.com'),
            format='json',
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(duplicate.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(duplicate.data['code'], 'conflict')
        self.assertEqual(User.objects.filter(email__iexact='new.patient@example.com').count(), 1)
        self.assertEqual(PatientProfile.objects.count(), 1)

    def test_legacy_success_shape_is_preserved_but_now_creates_profile(self):
        response = self.client.post(reverse('register'), self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['message'], 'Account created successfully.')
        self.assertIn('user', response.data)
        self.assertNotIn('profile', response.data)
        self.assertTrue(
            PatientProfile.objects.filter(user__email='new.patient@example.com').exists(),
        )

    @patch('accounts.services.PatientProfile.save', side_effect=RuntimeError('profile write failed'))
    def test_profile_failure_rolls_back_user(self, mocked_save):
        with self.assertRaises(ProfileCreationFailed):
            register_patient(
                email='rollback-profile@example.com',
                password=self.password,
                first_name='Rollback',
                last_name='Profile',
                phone='+22370000001',
            )
        self.assertTrue(mocked_save.called)
        self.assertFalse(User.objects.filter(email='rollback-profile@example.com').exists())
        self.assertEqual(PatientProfile.objects.count(), 0)

    @patch('accounts.serializers.register_patient', side_effect=ProfileCreationFailed())
    def test_v1_profile_creation_failure_uses_stable_error_code(self, mocked_service):
        response = self.client.post(
            '/api/v1/auth/register/',
            self.payload(email='api-profile-failure@example.com'),
            format='json',
        )

        self.assertTrue(mocked_service.called)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data['code'], 'profile_creation_failed')
        self.assertNotIn('password', str(response.data).lower())

    @patch('accounts.services.User.objects.create_user', side_effect=RuntimeError('user write failed'))
    def test_user_failure_never_attempts_profile_creation(self, mocked_create_user):
        with patch('accounts.services.PatientProfile.save') as profile_save:
            with self.assertRaises(RuntimeError):
                register_patient(
                    email='rollback-user@example.com',
                    password=self.password,
                    first_name='Rollback',
                    last_name='User',
                    phone='+22370000002',
                )
        self.assertTrue(mocked_create_user.called)
        profile_save.assert_not_called()
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(PatientProfile.objects.count(), 0)

    def test_service_duplicate_attempt_is_a_conflict(self):
        kwargs = {
            'email': 'concurrent@example.com',
            'password': self.password,
            'first_name': 'Con',
            'last_name': 'Current',
            'phone': '+22370000003',
        }
        register_patient(**kwargs)
        with self.assertRaises(Conflict):
            register_patient(**kwargs)
        self.assertEqual(User.objects.filter(email='concurrent@example.com').count(), 1)
        self.assertEqual(PatientProfile.objects.count(), 1)


class LoginAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='patient@example.com',
            password='SafePassword2026!',
            first_name='Aminata',
            last_name='Traore',
            phone='+22370000000',
            role=UserRole.PATIENT,
            is_verified=False,
        )
        self.url = reverse('login')

    def test_login_returns_tokens_and_public_user_data(self):
        response = self.client.post(
            self.url,
            {'email': self.user.email, 'password': 'SafePassword2026!'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        refresh = VersionedRefreshToken(response.data['refresh'])
        access = AccessToken(response.data['access'])
        self.assertEqual(refresh[TOKEN_VERSION_CLAIM], self.user.token_version)
        self.assertEqual(access[TOKEN_VERSION_CLAIM], self.user.token_version)
        self.assertEqual(response.data['message'], 'Login successful.')
        self.assertEqual(
            response.data['user'],
            {
                'id': str(self.user.id),
                'first_name': 'Aminata',
                'last_name': 'Traore',
                'email': 'patient@example.com',
                'role': UserRole.PATIENT,
            },
        )

    def test_login_rejects_invalid_credentials(self):
        response = self.client.post(
            self.url,
            {'email': self.user.email, 'password': 'WrongPassword2026!'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)


class MeAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='patient@example.com',
            password='SafePassword2026!',
            first_name='Aminata',
            last_name='Traore',
            phone='+22370000000',
            role=UserRole.PATIENT,
            is_verified=False,
        )
        self.url = reverse('me')
        access_token = VersionedRefreshToken.for_user(self.user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

    def test_me_returns_authenticated_user_with_valid_jwt(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], str(self.user.id))
        self.assertEqual(response.data['email'], self.user.email)
        self.assertEqual(response.data['role'], UserRole.PATIENT)

    def test_me_rejects_unauthenticated_request(self):
        self.client.credentials()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_updates_allowed_fields_only(self):
        response = self.client.patch(
            self.url,
            {'first_name': 'Fatou', 'last_name': 'Keita', 'phone': '+22371111111'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Fatou')
        self.assertEqual(self.user.last_name, 'Keita')
        self.assertEqual(self.user.phone, '+22371111111')

    def test_me_rejects_sensitive_field_updates(self):
        response = self.client.patch(
            self.url,
            {'email': 'other@example.com', 'role': UserRole.ADMIN},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)
        self.assertIn('role', response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'patient@example.com')
        self.assertEqual(self.user.role, UserRole.PATIENT)


class LogoutAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='patient@example.com',
            password='SafePassword2026!',
            first_name='Aminata',
            last_name='Traore',
            phone='+22370000000',
        )
        token = VersionedRefreshToken.for_user(self.user)
        self.refresh_token = str(token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')
        self.url = reverse('logout')

    def test_logout_blacklists_refresh_token(self):
        response = self.client.post(self.url, {'refresh': self.refresh_token}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'message': 'Logout successful.'})

        refresh_response = self.client.post(
            reverse('token_refresh'),
            {'refresh': self.refresh_token},
            format='json',
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_rejects_invalid_refresh_token(self):
        response = self.client.post(self.url, {'refresh': 'not-a-valid-token'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)

    def test_logout_rejects_unauthenticated_request(self):
        self.client.credentials()

        response = self.client.post(self.url, {'refresh': self.refresh_token}, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ChangePasswordAPITests(APITestCase):
    def setUp(self):
        self.old_password = 'SafePassword2026!'
        self.new_password = 'NewSafePassword2027!'
        self.user = User.objects.create_user(
            email='patient@example.com',
            password=self.old_password,
            role=UserRole.PATIENT,
        )
        token = VersionedRefreshToken.for_user(self.user)
        self.old_access_token = str(token.access_token)
        self.old_refresh_token = str(token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.old_access_token}')
        self.url = reverse('change_password')

    def payload(self, **overrides):
        data = {
            'old_password': self.old_password,
            'new_password': self.new_password,
            'new_password_confirm': self.new_password,
        }
        data.update(overrides)
        return data

    def test_change_password_succeeds(self):
        response = self.client.post(self.url, self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'message': 'Password changed successfully.'})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertFalse(self.user.check_password(self.old_password))
        self.assertEqual(self.user.token_version, 1)

    def test_change_password_revokes_old_access_token(self):
        self.client.post(self.url, self.payload(), format='json')

        response = self.client.get(reverse('me'))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn('token_version', str(response.data))

    def test_change_password_revokes_old_refresh_token(self):
        self.client.post(self.url, self.payload(), format='json')

        response = self.client.post(
            reverse('token_refresh'),
            {'refresh': self.old_refresh_token},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn('token_version', str(response.data))

    def test_new_login_and_tokens_work_after_password_change(self):
        self.client.post(self.url, self.payload(), format='json')
        self.client.credentials()

        old_login = self.client.post(
            reverse('login'),
            {'email': self.user.email, 'password': self.old_password},
            format='json',
        )
        new_login = self.client.post(
            reverse('login'),
            {'email': self.user.email, 'password': self.new_password},
            format='json',
        )

        self.assertEqual(old_login.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(new_login.status_code, status.HTTP_200_OK)
        new_access = AccessToken(new_login.data['access'])
        new_refresh = VersionedRefreshToken(new_login.data['refresh'])
        self.assertEqual(new_access[TOKEN_VERSION_CLAIM], 1)
        self.assertEqual(new_refresh[TOKEN_VERSION_CLAIM], 1)

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {new_login.data["access"]}')
        self.assertEqual(self.client.get(reverse('me')).status_code, status.HTTP_200_OK)
        self.client.credentials()
        refresh_response = self.client.post(
            reverse('token_refresh'),
            {'refresh': new_login.data['refresh']},
            format='json',
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)

    def test_change_password_rejects_incorrect_old_password(self):
        response = self.client.post(
            self.url,
            self.payload(old_password='IncorrectPassword2026!'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('old_password', response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))
        self.assertEqual(self.user.token_version, 0)

    def test_change_password_rejects_mismatched_passwords(self):
        response = self.client.post(
            self.url,
            self.payload(new_password_confirm='DifferentPassword2027!'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('new_password_confirm', response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.token_version, 0)

    def test_change_password_applies_django_password_validators(self):
        response = self.client.post(
            self.url,
            self.payload(new_password='123', new_password_confirm='123'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('new_password', response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.token_version, 0)

    def test_change_password_requires_authentication(self):
        self.client.credentials()

        response = self.client.post(self.url, self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PasswordResetAPITests(APITestCase):
    generic_response = {
        'detail': 'Si un compte correspondant existe, un lien de réinitialisation a été envoyé.',
    }

    def setUp(self):
        cache.clear()
        self.old_password = 'SafePassword2026!'
        self.new_password = 'ResetSafePassword2027!'
        self.user = User.objects.create_user(
            email='patient@example.com',
            password=self.old_password,
            role=UserRole.PATIENT,
        )
        self.reset_url = reverse('password_reset')
        self.confirm_url = reverse('password_reset_confirm')

    def request_password_reset(self, email=None):
        return self.client.post(
            self.reset_url,
            {'email': email or self.user.email},
            format='json',
        )

    def credentials_from_email(self):
        self.assertEqual(len(mail.outbox), 1)
        reset_url = next(
            line for line in mail.outbox[0].body.splitlines()
            if line.startswith(settings.FRONTEND_RESET_PASSWORD_URL)
        )
        query = parse_qs(urlparse(reset_url).query)
        return query['uid'][0], query['token'][0], reset_url

    def confirmation_payload(self, uid, token, **overrides):
        data = {
            'uid': uid,
            'token': token,
            'new_password': self.new_password,
            'new_password_confirm': self.new_password,
        }
        data.update(overrides)
        return data

    def test_password_reset_emails_credentials_without_exposing_them(self):
        response = self.request_password_reset()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.generic_response)
        self.assertEqual(set(response.data), {'detail'})
        self.assertNotIn('uid', response.data)
        self.assertNotIn('token', response.data)
        self.assertNotIn(settings.FRONTEND_RESET_PASSWORD_URL, str(response.data))

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        uid, token, reset_url = self.credentials_from_email()
        self.assertTrue(uid)
        self.assertTrue(token)
        self.assertTrue(reset_url.startswith(settings.FRONTEND_RESET_PASSWORD_URL))

    def test_password_reset_hides_unknown_email(self):
        response = self.request_password_reset('unknown@example.com')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.generic_response)
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_hides_inactive_account(self):
        self.user.is_active = False
        self.user.save(update_fields=('is_active',))

        response = self.request_password_reset()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.generic_response)
        self.assertNotIn('uid', response.data)
        self.assertNotIn('token', response.data)
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_hides_email_delivery_errors(self):
        with patch('accounts.services.send_mail', side_effect=RuntimeError('SMTP unavailable')):
            with self.assertLogs('accounts.services', level='ERROR'):
                response = self.request_password_reset()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.generic_response)
        self.assertNotIn('SMTP unavailable', str(response.data))

    def test_password_reset_confirmation_succeeds(self):
        self.request_password_reset()
        uid, token, _ = self.credentials_from_email()

        response = self.client.post(
            self.confirm_url,
            self.confirmation_payload(uid, token),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'message': 'Password reset successful.'})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertFalse(self.user.check_password(self.old_password))
        self.assertEqual(self.user.token_version, 1)

    def test_password_reset_confirmation_revokes_old_tokens_and_allows_new_login(self):
        old_token = VersionedRefreshToken.for_user(self.user)
        old_access = str(old_token.access_token)
        old_refresh = str(old_token)
        self.request_password_reset()
        uid, token, _ = self.credentials_from_email()

        confirm_response = self.client.post(
            self.confirm_url,
            self.confirmation_payload(uid, token),
            format='json',
        )

        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {old_access}')
        self.assertEqual(self.client.get(reverse('me')).status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.credentials()
        old_refresh_response = self.client.post(
            reverse('token_refresh'),
            {'refresh': old_refresh},
            format='json',
        )
        self.assertEqual(old_refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

        login_response = self.client.post(
            reverse('login'),
            {'email': self.user.email, 'password': self.new_password},
            format='json',
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {login_response.data["access"]}',
        )
        self.assertEqual(self.client.get(reverse('me')).status_code, status.HTTP_200_OK)

    def test_password_reset_request_alone_does_not_revoke_tokens(self):
        token = VersionedRefreshToken.for_user(self.user)
        response = self.request_password_reset()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.token_version, 0)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')
        self.assertEqual(self.client.get(reverse('me')).status_code, status.HTTP_200_OK)
        self.client.credentials()
        refresh_response = self.client.post(
            reverse('token_refresh'),
            {'refresh': str(token)},
            format='json',
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)

    def test_password_reset_confirmation_rejects_invalid_token(self):
        self.request_password_reset()
        uid, _, _ = self.credentials_from_email()

        response = self.client.post(
            self.confirm_url,
            self.confirmation_payload(uid, 'invalid-token'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.token_version, 0)

    def test_password_reset_confirmation_rejects_invalid_uid(self):
        self.request_password_reset()
        _, token, _ = self.credentials_from_email()

        response = self.client.post(
            self.confirm_url,
            self.confirmation_payload('invalid-uid', token),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.token_version, 0)

    def test_password_reset_confirmation_rejects_expired_token(self):
        self.request_password_reset()
        uid, token, _ = self.credentials_from_email()
        future = default_token_generator._now() + timedelta(
            seconds=settings.PASSWORD_RESET_TIMEOUT + 1,
        )

        with patch.object(default_token_generator, '_now', return_value=future):
            response = self.client.post(
                self.confirm_url,
                self.confirmation_payload(uid, token),
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.token_version, 0)

    def test_password_reset_confirmation_rejects_weak_password(self):
        self.request_password_reset()
        uid, token, _ = self.credentials_from_email()

        response = self.client.post(
            self.confirm_url,
            self.confirmation_payload(
                uid,
                token,
                new_password='123',
                new_password_confirm='123',
            ),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('new_password', response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.token_version, 0)

    def test_password_reset_confirmation_rejects_mismatched_passwords(self):
        self.request_password_reset()
        uid, token, _ = self.credentials_from_email()

        response = self.client.post(
            self.confirm_url,
            self.confirmation_payload(
                uid,
                token,
                new_password_confirm='DifferentPassword2027!',
            ),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('new_password_confirm', response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.token_version, 0)


class TokenLifecycleSecurityTests(APITestCase):
    def setUp(self):
        self.old_password = 'SafePassword2026!'
        self.new_password = 'NewSafePassword2027!'
        self.user = User.objects.create_user(
            email='token-lifecycle@example.com',
            password=self.old_password,
        )

    def test_refresh_rotation_preserves_version_and_rotated_tokens_are_revoked(self):
        original = VersionedRefreshToken.for_user(self.user)
        refresh_response = self.client.post(
            reverse('token_refresh'),
            {'refresh': str(original)},
            format='json',
        )

        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)
        rotated = VersionedRefreshToken(refresh_response.data['refresh'])
        refreshed_access = AccessToken(refresh_response.data['access'])
        self.assertEqual(rotated[TOKEN_VERSION_CLAIM], 0)
        self.assertEqual(refreshed_access[TOKEN_VERSION_CLAIM], 0)

        original_retry = self.client.post(
            reverse('token_refresh'),
            {'refresh': str(original)},
            format='json',
        )
        self.assertEqual(original_retry.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {refresh_response.data["access"]}',
        )
        change_response = self.client.post(
            reverse('change_password'),
            {
                'old_password': self.old_password,
                'new_password': self.new_password,
                'new_password_confirm': self.new_password,
            },
            format='json',
        )
        self.assertEqual(change_response.status_code, status.HTTP_200_OK)
        self.client.credentials()

        rotated_response = self.client.post(
            reverse('token_refresh'),
            {'refresh': str(rotated)},
            format='json',
        )
        self.assertEqual(rotated_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_inactive_user_is_refused_with_previously_valid_tokens(self):
        token = VersionedRefreshToken.for_user(self.user)
        self.user.is_active = False
        self.user.save(update_fields=('is_active',))

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')
        access_response = self.client.get(reverse('me'))
        self.client.credentials()
        refresh_response = self.client.post(
            reverse('token_refresh'),
            {'refresh': str(token)},
            format='json',
        )

        self.assertEqual(access_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_tokens_without_version_claim_are_refused(self):
        legacy_refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {legacy_refresh.access_token}')

        access_response = self.client.get(reverse('me'))
        self.client.credentials()
        refresh_response = self.client.post(
            reverse('token_refresh'),
            {'refresh': str(legacy_refresh)},
            format='json',
        )

        self.assertEqual(access_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_password_form_revokes_existing_tokens(self):
        token = VersionedRefreshToken.for_user(self.user)
        form = TokenRevokingAdminPasswordChangeForm(
            self.user,
            data={
                'password1': self.new_password,
                'password2': self.new_password,
            },
        )

        self.assertIs(UserAdmin.change_password_form, TokenRevokingAdminPasswordChangeForm)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.user.refresh_from_db()
        self.assertEqual(self.user.token_version, 1)
        self.assertTrue(self.user.check_password(self.new_password))
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')
        self.assertEqual(self.client.get(reverse('me')).status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.credentials()
        refresh_response = self.client.post(
            reverse('token_refresh'),
            {'refresh': str(token)},
            format='json',
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(REST_FRAMEWORK=THROTTLE_TEST_REST_FRAMEWORK)
class AccountThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email='throttle-patient@example.com',
            password='SafePassword2026!',
            role=UserRole.PATIENT,
        )

    def tearDown(self):
        cache.clear()

    @staticmethod
    def registration_payload(index):
        return {
            'first_name': 'Aminata',
            'last_name': 'Traore',
            'email': f'new-patient-{index}@example.com',
            'phone': f'+2237000000{index}',
            'password': 'SafeRegistration2026!',
            'password_confirm': 'SafeRegistration2026!',
        }

    def test_login_throttles_invalid_credentials_and_returns_retry_after(self):
        payload = {'email': self.user.email, 'password': 'WrongPassword2026!'}

        for _ in range(2):
            response = self.client.post(reverse('login'), payload, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        blocked_response = self.client.post(reverse('login'), payload, format='json')

        self.assertEqual(blocked_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn('Retry-After', blocked_response)
        self.assertIn('detail', blocked_response.data)

    def test_login_throttle_keeps_distinct_ip_counters(self):
        payload = {'email': self.user.email, 'password': 'WrongPassword2026!'}

        for _ in range(3):
            first_ip_response = self.client.post(
                reverse('login'),
                payload,
                format='json',
                REMOTE_ADDR='198.51.100.10',
            )
        second_ip_response = self.client.post(
            reverse('login'),
            payload,
            format='json',
            REMOTE_ADDR='198.51.100.11',
        )

        self.assertEqual(
            first_ip_response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )
        self.assertEqual(second_ip_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_registration_is_throttled_after_allowed_requests(self):
        for index in range(2):
            response = self.client.post(
                reverse('register'),
                self.registration_payload(index),
                format='json',
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        blocked_response = self.client.post(
            reverse('register'),
            self.registration_payload(2),
            format='json',
        )

        self.assertEqual(blocked_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_unknown_password_reset_requests_keep_generic_response_until_throttled(self):
        expected_response = {
            'detail': (
                'Si un compte correspondant existe, '
                'un lien de réinitialisation a été envoyé.'
            ),
        }

        for _ in range(2):
            response = self.client.post(
                reverse('password_reset'),
                {'email': 'unknown@example.com'},
                format='json',
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data, expected_response)

        blocked_response = self.client.post(
            reverse('password_reset'),
            {'email': 'unknown@example.com'},
            format='json',
        )

        self.assertEqual(blocked_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_password_reset_confirmations_are_throttled(self):
        payload = {
            'uid': 'invalid-uid',
            'token': 'invalid-token',
            'new_password': 'ResetSafePassword2027!',
            'new_password_confirm': 'ResetSafePassword2027!',
        }

        for _ in range(2):
            response = self.client.post(
                reverse('password_reset_confirm'),
                payload,
                format='json',
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        blocked_response = self.client.post(
            reverse('password_reset_confirm'),
            payload,
            format='json',
        )

        self.assertEqual(blocked_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_valid_token_refreshes_are_throttled(self):
        refresh = str(VersionedRefreshToken.for_user(self.user))

        for _ in range(2):
            response = self.client.post(
                reverse('token_refresh'),
                {'refresh': refresh},
                format='json',
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            refresh = response.data['refresh']

        blocked_response = self.client.post(
            reverse('token_refresh'),
            {'refresh': refresh},
            format='json',
        )

        self.assertEqual(blocked_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_login_and_password_reset_scopes_are_isolated(self):
        login_payload = {
            'email': self.user.email,
            'password': 'WrongPassword2026!',
        }
        for _ in range(3):
            login_response = self.client.post(
                reverse('login'),
                login_payload,
                format='json',
            )

        reset_response = self.client.post(
            reverse('password_reset'),
            {'email': 'unknown@example.com'},
            format='json',
        )

        self.assertEqual(login_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(reset_response.status_code, status.HTTP_200_OK)

    @override_settings(REST_FRAMEWORK={
        **THROTTLE_TEST_REST_FRAMEWORK,
        'DEFAULT_THROTTLE_RATES': {
            **THROTTLE_TEST_REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'],
            'user': '2/minute',
        },
    })
    def test_authenticated_user_global_throttle_protects_me_endpoint(self):
        access_token = VersionedRefreshToken.for_user(self.user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

        for _ in range(2):
            response = self.client.get(reverse('me'))
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        blocked_response = self.client.get(reverse('me'))

        self.assertEqual(blocked_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class AuthenticationSchemaTests(APITestCase):
    def test_schema_documents_every_domain_one_operation(self):
        response = self.client.get(reverse('schema'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        paths = response.data['paths']
        expected_operations = {
            '/api/auth/register/': {'post'},
            '/api/auth/login/': {'post'},
            '/api/auth/refresh/': {'post'},
            '/api/auth/me/': {'get', 'patch'},
            '/api/auth/logout/': {'post'},
            '/api/auth/change-password/': {'post'},
            '/api/auth/password-reset/': {'post'},
            '/api/auth/password-reset-confirm/': {'post'},
        }

        for path, methods in expected_operations.items():
            self.assertIn(path, paths)
            self.assertTrue(methods.issubset(paths[path]))
            for method in methods:
                self.assertEqual(
                    paths[path][method]['tags'],
                    ['Domaine 1 - Authentification'],
                )
                self.assertIn('429', paths[path][method]['responses'])

        reset_response_schema = response.data['components']['schemas'][
            'PasswordResetResponse'
        ]
        self.assertEqual(set(reset_response_schema['properties']), {'detail'})
        self.assertNotIn('uid', reset_response_schema['properties'])
        self.assertNotIn('token', reset_response_schema['properties'])
        self.assertIn('jwtAuth', response.data['components']['securitySchemes'])
        self.assertIn({'jwtAuth': []}, paths['/api/auth/me/']['get']['security'])
        for schema in response.data['components']['schemas'].values():
            self.assertNotIn('token_version', schema.get('properties', {}))

    def test_interactive_documentation_is_available(self):
        swagger_response = self.client.get(reverse('swagger-ui'))
        redoc_response = self.client.get(reverse('redoc'))

        self.assertEqual(swagger_response.status_code, status.HTTP_200_OK)
        self.assertEqual(redoc_response.status_code, status.HTTP_200_OK)


class RolePermissionTests(APITestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            email='patient@example.com', password='SafePassword2026!', role=UserRole.PATIENT,
        )
        self.doctor = User.objects.create_user(
            email='doctor@example.com', password='SafePassword2026!', role=UserRole.DOCTOR,
        )
        self.admin = User.objects.create_user(
            email='admin@example.com', password='SafePassword2026!', role=UserRole.ADMIN,
        )

    @staticmethod
    def request_for(user):
        return SimpleNamespace(user=user)

    def test_role_permissions_allow_only_expected_roles(self):
        patient_request = self.request_for(self.patient)
        doctor_request = self.request_for(self.doctor)
        admin_request = self.request_for(self.admin)

        self.assertTrue(IsPatient().has_permission(patient_request, None))
        self.assertFalse(IsPatient().has_permission(doctor_request, None))
        self.assertFalse(IsPatient().has_permission(admin_request, None))
        self.assertTrue(IsDoctor().has_permission(doctor_request, None))
        self.assertFalse(IsDoctor().has_permission(patient_request, None))
        self.assertFalse(IsDoctor().has_permission(admin_request, None))
        self.assertTrue(IsAdmin().has_permission(admin_request, None))
        self.assertFalse(IsAdmin().has_permission(doctor_request, None))
        self.assertFalse(IsAdmin().has_permission(patient_request, None))
        self.assertTrue(IsDoctorOrAdmin().has_permission(doctor_request, None))
        self.assertTrue(IsDoctorOrAdmin().has_permission(admin_request, None))
        self.assertFalse(IsDoctorOrAdmin().has_permission(patient_request, None))

    def test_role_permissions_reject_anonymous_users(self):
        request = self.request_for(AnonymousUser())

        self.assertFalse(IsPatient().has_permission(request, None))
        self.assertFalse(IsDoctor().has_permission(request, None))
        self.assertFalse(IsAdmin().has_permission(request, None))
        self.assertFalse(IsDoctorOrAdmin().has_permission(request, None))

    def test_is_owner_supports_default_and_configured_owner_paths(self):
        permission = IsOwner()
        patient_request = self.request_for(self.patient)
        other_request = self.request_for(self.doctor)
        user_owned_object = SimpleNamespace(user=self.patient)
        patient_owned_object = SimpleNamespace(patient=SimpleNamespace(user=self.patient))
        patient_view = SimpleNamespace(owner_field='patient')

        self.assertTrue(permission.has_permission(patient_request, None))
        self.assertTrue(permission.has_object_permission(patient_request, None, user_owned_object))
        self.assertFalse(permission.has_object_permission(other_request, None, user_owned_object))
        self.assertTrue(
            permission.has_object_permission(patient_request, patient_view, patient_owned_object)
        )
        self.assertFalse(
            permission.has_object_permission(other_request, patient_view, patient_owned_object)
        )

    def test_is_owner_rejects_anonymous_users_and_missing_owner_fields(self):
        permission = IsOwner()
        anonymous_request = self.request_for(AnonymousUser())
        owned_object = SimpleNamespace(owner=self.patient)
        object_without_owner = SimpleNamespace()

        self.assertFalse(permission.has_permission(anonymous_request, None))
        self.assertFalse(
            permission.has_object_permission(anonymous_request, None, owned_object)
        )
        self.assertFalse(
            permission.has_object_permission(
                self.request_for(self.patient),
                None,
                object_without_owner,
            )
        )
