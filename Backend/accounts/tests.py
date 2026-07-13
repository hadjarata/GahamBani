from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, UserRole


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
