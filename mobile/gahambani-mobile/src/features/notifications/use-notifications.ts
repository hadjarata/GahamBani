import { useCallback, useEffect, useRef, useState } from 'react';

import {
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '@/services/api/notifications-api';
import type { Notification, NotificationFilters } from '@/types/notification';

import { toNotificationError, type NotificationFailureKind } from './notification-errors';
import { useUnreadNotificationCount } from './unread-count-store';

type ListState = {
  items: Notification[];
  total: number;
  nextPage: number | null;
  initialLoading: boolean;
  refreshing: boolean;
  loadingMore: boolean;
  markingAll: boolean;
  error?: NotificationFailureKind;
};

const initialState: ListState = {
  items: [], total: 0, nextPage: null, initialLoading: true,
  refreshing: false, loadingMore: false, markingAll: false,
};

function mergeUnique(current: Notification[], incoming: Notification[]) {
  const byId = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) byId.set(item.id, item);
  return Array.from(byId.values());
}

export function useNotifications(filters: NotificationFilters) {
  const [state, setState] = useState<ListState>(initialState);
  const generation = useRef(0);
  const pagesInFlight = useRef(new Set<string>());
  const readsInFlight = useRef(new Set<string>());
  const decrementCount = useUnreadNotificationCount((store) => store.decrement);
  const clearCount = useUnreadNotificationCount((store) => store.clear);

  const loadPage = useCallback(async (page: number, mode: 'initial' | 'refresh' | 'more') => {
    const requestGeneration = generation.current;
    const requestKey = `${requestGeneration}:${page}`;
    if (pagesInFlight.current.has(requestKey)) return;
    pagesInFlight.current.add(requestKey);
    setState((current) => ({
      ...current,
      error: undefined,
      initialLoading: mode === 'initial',
      refreshing: mode === 'refresh',
      loadingMore: mode === 'more',
      ...(mode === 'initial' ? { items: [], total: 0, nextPage: null } : {}),
    }));
    try {
      const response = await getNotifications(filters, page);
      if (generation.current !== requestGeneration) return;
      setState((current) => ({
        ...current,
        items: page === 1 ? response.results : mergeUnique(current.items, response.results),
        total: response.count,
        nextPage: response.next ? page + 1 : null,
        initialLoading: false,
        refreshing: false,
        loadingMore: false,
      }));
    } catch (error) {
      if (generation.current !== requestGeneration) return;
      setState((current) => ({
        ...current,
        initialLoading: false,
        refreshing: false,
        loadingMore: false,
        error: toNotificationError(error).kind,
      }));
    } finally {
      pagesInFlight.current.delete(requestKey);
    }
  }, [filters]);

  useEffect(() => {
    generation.current += 1;
    pagesInFlight.current.clear();
    void loadPage(1, 'initial');
  }, [loadPage]);

  const refresh = useCallback(() => {
    generation.current += 1;
    pagesInFlight.current.clear();
    return loadPage(1, 'refresh');
  }, [loadPage]);

  const loadMore = useCallback(() => {
    if (state.nextPage === null || state.loadingMore || state.initialLoading) return;
    void loadPage(state.nextPage, 'more');
  }, [loadPage, state.initialLoading, state.loadingMore, state.nextPage]);

  const markRead = useCallback(async (notification: Notification) => {
    if (notification.is_read || readsInFlight.current.has(notification.id)) return true;
    readsInFlight.current.add(notification.id);
    try {
      const updated = await markNotificationRead(notification.id);
      setState((current) => ({
        ...current,
        items: filters.read === 'unread'
          ? current.items.filter((item) => item.id !== updated.id)
          : current.items.map((item) => item.id === updated.id ? updated : item),
        total: filters.read === 'unread' ? Math.max(0, current.total - 1) : current.total,
      }));
      decrementCount();
      return true;
    } catch (error) {
      setState((current) => ({ ...current, error: toNotificationError(error).kind }));
      return false;
    } finally {
      readsInFlight.current.delete(notification.id);
    }
  }, [decrementCount, filters.read]);

  const markAllRead = useCallback(async () => {
    if (state.markingAll) return;
    setState((current) => ({ ...current, markingAll: true, error: undefined }));
    try {
      await markAllNotificationsRead();
      const readAt = new Date().toISOString();
      setState((current) => ({
        ...current,
        markingAll: false,
        items: filters.read === 'unread' ? [] : current.items.map((item) => (
          item.is_read ? item : { ...item, is_read: true, read_at: readAt }
        )),
        total: filters.read === 'unread' ? 0 : current.total,
      }));
      clearCount();
    } catch (error) {
      setState((current) => ({
        ...current, markingAll: false, error: toNotificationError(error).kind,
      }));
    }
  }, [clearCount, filters.read, state.markingAll]);

  return { state, refresh, loadMore, markRead, markAllRead };
}
