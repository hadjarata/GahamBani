import type { AxiosRequestConfig, AxiosResponse } from 'axios';

import { refreshSessionOnce } from '@/services/session/refresh-session';
import { clearSession, readSession } from '@/services/session/session-store';

import { apiClient, bearerHeader, isAuthenticationError } from './client';

export class SessionExpiredError extends Error {
  constructor() {
    super('session_expired');
    this.name = 'SessionExpiredError';
  }
}

export async function authenticatedRequest<T>(config: AxiosRequestConfig): Promise<AxiosResponse<T>> {
  let tokens = await readSession();
  if (!tokens) throw new SessionExpiredError();

  try {
    return await apiClient.request<T>({
      ...config,
      headers: { ...config.headers, ...bearerHeader(tokens.accessToken) },
    });
  } catch (error) {
    if (!isAuthenticationError(error)) throw error;
  }

  try {
    tokens = await refreshSessionOnce(tokens);
  } catch (error) {
    if (!isAuthenticationError(error)) throw error;
    await clearSession();
    throw new SessionExpiredError();
  }

  try {
    return await apiClient.request<T>({
      ...config,
      headers: { ...config.headers, ...bearerHeader(tokens.accessToken) },
    });
  } catch (error) {
    if (!isAuthenticationError(error)) throw error;
    await clearSession();
    throw new SessionExpiredError();
  }
}
