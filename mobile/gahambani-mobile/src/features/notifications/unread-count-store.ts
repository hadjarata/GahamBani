import { create } from 'zustand';

import { getUnreadNotificationCount } from '@/services/api/notifications-api';

import { toNotificationError, type NotificationFailureKind } from './notification-errors';

type UnreadCountState = {
  count: number;
  status: 'idle' | 'loading' | 'ready' | 'error';
  error?: NotificationFailureKind;
  refresh: () => Promise<void>;
  decrement: () => void;
  clear: () => void;
};

let countRequest: Promise<void> | null = null;

export const useUnreadNotificationCount = create<UnreadCountState>((set) => ({
  count: 0,
  status: 'idle',
  refresh: async () => {
    if (countRequest) return countRequest;
    set({ status: 'loading', error: undefined });
    countRequest = getUnreadNotificationCount()
      .then(({ unread_count }) => set({ count: unread_count, status: 'ready' }))
      .catch((error) => {
        const safeError = toNotificationError(error);
        set({ status: 'error', error: safeError.kind });
      })
      .finally(() => {
        countRequest = null;
      });
    return countRequest;
  },
  decrement: () => set((state) => ({ count: Math.max(0, state.count - 1), status: 'ready' })),
  clear: () => set({ count: 0, status: 'ready', error: undefined }),
}));
