import * as SecureStore from 'expo-secure-store';

import type { SessionTokens } from '@/types/session';

const SESSION_KEY = 'gahambani.session.v1';

function isSessionTokens(value: unknown): value is SessionTokens {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<SessionTokens>;
  return (
    typeof candidate.accessToken === 'string' &&
    candidate.accessToken.length > 0 &&
    typeof candidate.refreshToken === 'string' &&
    candidate.refreshToken.length > 0
  );
}

export async function readSession(): Promise<SessionTokens | null> {
  const serialized = await SecureStore.getItemAsync(SESSION_KEY);
  if (!serialized) return null;

  try {
    const parsed: unknown = JSON.parse(serialized);
    if (isSessionTokens(parsed)) return parsed;
  } catch {
    // Une valeur illisible n'est jamais utilisée comme authentification.
  }

  await clearSession();
  return null;
}

export async function saveSession(tokens: SessionTokens): Promise<void> {
  await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(tokens));
}

export async function clearSession(): Promise<void> {
  await SecureStore.deleteItemAsync(SESSION_KEY);
}
