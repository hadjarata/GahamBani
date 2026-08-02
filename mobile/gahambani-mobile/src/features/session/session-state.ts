import { create } from 'zustand';

import type { CurrentProfile } from '@/types/profile';

type SessionState = {
  status: 'unknown' | 'anonymous' | 'authenticated';
  profile: CurrentProfile | null;
  setAuthenticated: (profile: CurrentProfile) => void;
  setAnonymous: () => void;
};

export const useSessionState = create<SessionState>((set) => ({
  status: 'unknown',
  profile: null,
  setAuthenticated: (profile) => set({ status: 'authenticated', profile }),
  setAnonymous: () => set({ status: 'anonymous', profile: null }),
}));
