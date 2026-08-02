import {
  isAuthenticationError,
  isRecoverableApiError,
} from '@/services/api/client';
import { getCurrentProfile } from '@/services/api/profile-api';
import { refreshSessionOnce } from '@/services/session/refresh-session';
import { clearSession, readSession } from '@/services/session/session-store';
import type { CurrentProfile } from '@/types/profile';

import { getProfileDestination } from './profile-destination';
import type { SessionDestination } from './session-routes';

export type RestorationResult =
  | { status: 'unauthenticated' }
  | { status: 'authenticated'; destination: SessionDestination; profile: CurrentProfile }
  | { status: 'recoverable-error' }
  | { status: 'inconsistent-session' };

async function invalidateSession(status: 'unauthenticated' | 'inconsistent-session') {
  await clearSession();
  return { status } as const;
}

export async function restoreSession(): Promise<RestorationResult> {
  let tokens;
  try {
    tokens = await readSession();
  } catch {
    return { status: 'recoverable-error' };
  }
  if (!tokens) return { status: 'unauthenticated' };

  let profile: CurrentProfile;
  try {
    profile = await getCurrentProfile(tokens.accessToken);
  } catch (error) {
    if (!isAuthenticationError(error)) {
      if (isRecoverableApiError(error)) return { status: 'recoverable-error' };
      return invalidateSession('inconsistent-session');
    }

    try {
      tokens = await refreshSessionOnce(tokens);
    } catch (refreshError) {
      if (isRecoverableApiError(refreshError)) return { status: 'recoverable-error' };
      return invalidateSession('unauthenticated');
    }

    try {
      profile = await getCurrentProfile(tokens.accessToken);
    } catch (retryError) {
      if (isRecoverableApiError(retryError)) return { status: 'recoverable-error' };
      return invalidateSession(
        isAuthenticationError(retryError) ? 'unauthenticated' : 'inconsistent-session',
      );
    }
  }

  const destination = getProfileDestination(profile);
  if (!destination) return invalidateSession('inconsistent-session');
  return { status: 'authenticated', destination, profile };
}
