import { AxiosError, create, isAxiosError } from 'axios';

import { API_BASE_URL, API_TIMEOUT_MS } from '@/config/api';
import type { ApiErrorBody } from '@/types/api';

export const apiClient = create({
  baseURL: API_BASE_URL,
  timeout: API_TIMEOUT_MS,
  headers: { Accept: 'application/json' },
});

export function bearerHeader(accessToken: string) {
  return { Authorization: `Bearer ${accessToken}` };
}

export function isAuthenticationError(error: unknown): boolean {
  return isAxiosError<ApiErrorBody>(error) && error.response?.status === 401;
}

export function isRecoverableApiError(error: unknown): boolean {
  if (!isAxiosError(error)) return false;
  if (!error.response) return true;
  const status = error.response.status;
  return status === 408 || status === 429 || status >= 500;
}

export function getSafeErrorCode(error: unknown): string | undefined {
  return error instanceof AxiosError
    ? (error.response?.data as ApiErrorBody | undefined)?.code
    : undefined;
}
