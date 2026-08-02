import { apiClient } from './client';
import type {
  LoginCredentials,
  LoginResponse,
  MessageResponse,
  PasswordResetConfirmRequest,
  PasswordResetRequest,
  PasswordResetResponse,
  RegisterRequest,
  RegisterResponse,
  RefreshResponse,
} from '@/types/session';

function isLoginResponse(value: unknown): value is LoginResponse {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<LoginResponse>;
  return (
    typeof candidate.access === 'string' &&
    candidate.access.length > 0 &&
    typeof candidate.refresh === 'string' &&
    candidate.refresh.length > 0
  );
}

export class InvalidLoginResponseError extends Error {
  constructor() {
    super('La réponse de connexion est invalide.');
    this.name = 'InvalidLoginResponseError';
  }
}

export async function requestLogin(credentials: LoginCredentials): Promise<LoginResponse> {
  const response = await apiClient.post<unknown>('/auth/login/', credentials);
  if (!isLoginResponse(response.data)) throw new InvalidLoginResponseError();
  return response.data;
}

function isRegisterResponse(value: unknown): value is RegisterResponse {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<RegisterResponse>;
  return Boolean(
    typeof candidate.detail === 'string' &&
      candidate.user &&
      candidate.user.role === 'PATIENT' &&
      typeof candidate.user.email === 'string' &&
      candidate.profile &&
      candidate.profile.profile_type === 'PATIENT' &&
      candidate.onboarding &&
      typeof candidate.onboarding.is_complete === 'boolean',
  );
}

export class InvalidRegisterResponseError extends Error {
  constructor() {
    super('La réponse d’inscription est invalide.');
    this.name = 'InvalidRegisterResponseError';
  }
}

export async function requestRegistration(data: RegisterRequest): Promise<RegisterResponse> {
  const response = await apiClient.post<unknown>('/auth/register/', data);
  if (!isRegisterResponse(response.data)) throw new InvalidRegisterResponseError();
  return response.data;
}

export async function requestPasswordReset(
  data: PasswordResetRequest,
): Promise<PasswordResetResponse> {
  const response = await apiClient.post<PasswordResetResponse>('/auth/password-reset/', data);
  return response.data;
}

export async function confirmPasswordReset(
  data: PasswordResetConfirmRequest,
): Promise<MessageResponse> {
  const response = await apiClient.post<MessageResponse>(
    '/auth/password-reset-confirm/',
    data,
  );
  return response.data;
}

export async function requestTokenRefresh(refreshToken: string): Promise<RefreshResponse> {
  const response = await apiClient.post<RefreshResponse>('/auth/refresh/', {
    refresh: refreshToken,
  });
  return response.data;
}
