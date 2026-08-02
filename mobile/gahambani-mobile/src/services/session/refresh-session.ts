import { requestTokenRefresh } from '@/services/api/auth-api';
import type { SessionTokens } from '@/types/session';

import { saveSession } from './session-store';

let refreshInFlight: Promise<SessionTokens> | null = null;

export function refreshSessionOnce(tokens: SessionTokens): Promise<SessionTokens> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    const refreshed = await requestTokenRefresh(tokens.refreshToken);
    const nextTokens = {
      accessToken: refreshed.access,
      refreshToken: refreshed.refresh ?? tokens.refreshToken,
    };
    await saveSession(nextTokens);
    return nextTokens;
  })().finally(() => {
    refreshInFlight = null;
  });

  return refreshInFlight;
}
