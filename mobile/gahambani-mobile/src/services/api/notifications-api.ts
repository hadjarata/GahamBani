import { authenticatedRequest } from './authenticated-request';
import type {
  Notification,
  NotificationFilters,
  PaginatedNotifications,
  ReadAllResponse,
  UnreadCountResponse,
} from '@/types/notification';

export async function getNotifications(filters: NotificationFilters, page: number) {
  const isRead = filters.read === 'all' ? undefined : filters.read === 'read';
  const response = await authenticatedRequest<PaginatedNotifications>({
    method: 'GET',
    url: '/notifications/',
    params: {
      page,
      page_size: 20,
      is_read: isRead,
      priority: filters.priority,
      type: filters.type,
    },
  });
  return response.data;
}

export async function getUnreadNotificationCount() {
  const response = await authenticatedRequest<UnreadCountResponse>({
    method: 'GET',
    url: '/notifications/unread-count/',
  });
  return response.data;
}

export async function markNotificationRead(id: string) {
  const response = await authenticatedRequest<Notification>({
    method: 'PATCH',
    url: `/notifications/${encodeURIComponent(id)}/read/`,
  });
  return response.data;
}

export async function markAllNotificationsRead() {
  const response = await authenticatedRequest<ReadAllResponse>({
    method: 'PATCH',
    url: '/notifications/read-all/',
  });
  return response.data;
}
