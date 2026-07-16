from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, UserRole
from .permissions import IsAdmin, IsDoctor, IsDoctorOrAdmin, IsOwner, IsPatient


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
        access_token = RefreshToken.for_user(self.user).access_token
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
        token = RefreshToken.for_user(self.user)
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
        access_token = RefreshToken.for_user(self.user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
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

    def test_change_password_rejects_mismatched_passwords(self):
        response = self.client.post(
            self.url,
            self.payload(new_password_confirm='DifferentPassword2027!'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('new_password_confirm', response.data)

    def test_change_password_applies_django_password_validators(self):
        response = self.client.post(
            self.url,
            self.payload(new_password='123', new_password_confirm='123'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('new_password', response.data)

    def test_change_password_requires_authentication(self):
        self.client.credentials()

        response = self.client.post(self.url, self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PasswordResetAPITests(APITestCase):
    def setUp(self):
        self.old_password = 'SafePassword2026!'
        self.new_password = 'ResetSafePassword2027!'
        self.user = User.objects.create_user(
            email='patient@example.com',
            password=self.old_password,
            role=UserRole.PATIENT,
        )
        self.reset_url = reverse('password_reset')
        self.confirm_url = reverse('password_reset_confirm')

    def request_reset_credentials(self):
        response = self.client.post(
            self.reset_url,
            {'email': self.user.email},
            format='json',
        )
        return response.data['uid'], response.data['token']

    def confirmation_payload(self, uid, token, **overrides):
        data = {
            'uid': uid,
            'token': token,
            'new_password': self.new_password,
            'new_password_confirm': self.new_password,
        }
        data.update(overrides)
        return data

    def test_password_reset_generates_uid_and_token(self):
        response = self.client.post(
            self.reset_url,
            {'email': self.user.email},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Password reset link generated.')
        self.assertTrue(response.data['uid'])
        self.assertTrue(response.data['token'])

    def test_password_reset_hides_unknown_email(self):
        response = self.client.post(
            self.reset_url,
            {'email': 'unknown@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {'message': 'If the account exists, a reset link has been generated.'},
        )

    def test_password_reset_confirmation_succeeds(self):
        uid, token = self.request_reset_credentials()

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

    def test_password_reset_confirmation_rejects_invalid_token(self):
        uid, _ = self.request_reset_credentials()

        response = self.client.post(
            self.confirm_url,
            self.confirmation_payload(uid, 'invalid-token'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)

    def test_password_reset_confirmation_rejects_invalid_uid(self):
        _, token = self.request_reset_credentials()

        response = self.client.post(
            self.confirm_url,
            self.confirmation_payload('invalid-uid', token),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)


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
