import type { SessionTokens } from '@/types/session';

const SESSION_KEY = 'gahambani.session.v1';

function getBrowserSessionStorage(): Storage | null {
  return typeof window === 'undefined' ? null : window.sessionStorage;
}

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
  const storage = getBrowserSessionStorage();
  if (!storage) return null;

  const serialized = storage.getItem(SESSION_KEY);
  if (!serialized) return null;

  try {
    const parsed: unknown = JSON.parse(serialized);
    if (isSessionTokens(parsed)) return parsed;
  } catch {
    // Une valeur illisible n'est jamais utilisée comme authentification.
  }

  storage.removeItem(SESSION_KEY);
  return null;
}

export async function saveSession(tokens: SessionTokens): Promise<void> {
  getBrowserSessionStorage()?.setItem(SESSION_KEY, JSON.stringify(tokens));
}

export async function clearSession(): Promise<void> {
  getBrowserSessionStorage()?.removeItem(SESSION_KEY);
}
