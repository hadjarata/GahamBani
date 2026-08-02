import { isAxiosError } from 'axios';

import { requestLogin } from '@/services/api/auth-api';
import { isRecoverableApiError } from '@/services/api/client';
import { getCurrentProfile } from '@/services/api/profile-api';
import { clearSession, saveSession } from '@/services/session/session-store';
import type { ApiErrorBody } from '@/types/api';
import type { CurrentProfile } from '@/types/profile';
import type { LoginCredentials } from '@/types/session';
import { getProfileDestination } from '@/features/session/profile-destination';
import { restoreSession } from '@/features/session/restore-session';
import type { SessionDestination } from '@/features/session/session-routes';

export type SignInFailureKind =
  | 'invalid_credentials'
  | 'rate_limited'
  | 'network'
  | 'server'
  | 'profile_unavailable'
  | 'unexpected';

export class SignInError extends Error {
  constructor(public readonly kind: SignInFailureKind) {
    super(kind);
    this.name = 'SignInError';
  }
}

export type SignInResult = {
  profile: CurrentProfile;
  destination: SessionDestination;
};

function classifyLoginError(error: unknown): SignInError {
  if (!isAxiosError<ApiErrorBody>(error)) return new SignInError('unexpected');
  if (!error.response) return new SignInError('network');
  if (error.response.status === 400 || error.response.status === 401) {
    return new SignInError('invalid_credentials');
  }
  if (error.response.status === 429) return new SignInError('rate_limited');
  if (error.response.status >= 500) return new SignInError('server');
  return new SignInError('unexpected');
}

function resultFor(profile: CurrentProfile): SignInResult | null {
  const destination = getProfileDestination(profile);
  return destination ? { profile, destination } : null;
}

export async function signIn(credentials: LoginCredentials): Promise<SignInResult> {
  let response;
  try {
    response = await requestLogin(credentials);
  } catch (error) {
    throw classifyLoginError(error);
  }

  await saveSession({
    accessToken: response.access,
    refreshToken: response.refresh,
  });

  try {
    const profile = await getCurrentProfile(response.access);
    const result = resultFor(profile);
    if (result) return result;
  } catch (error) {
    if (isRecoverableApiError(error)) throw new SignInError('profile_unavailable');
  }

  await clearSession();
  throw new SignInError('unexpected');
}

export async function resumeSignIn(): Promise<SignInResult> {
  const restored = await restoreSession();
  if (restored.status === 'authenticated') {
    return { profile: restored.profile, destination: restored.destination };
  }
  if (restored.status === 'recoverable-error') {
    throw new SignInError('profile_unavailable');
  }
  throw new SignInError(
    restored.status === 'unauthenticated' ? 'invalid_credentials' : 'unexpected',
  );
}
