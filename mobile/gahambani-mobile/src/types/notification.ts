export const notificationPriorities = ['LOW', 'NORMAL', 'HIGH', 'CRITICAL'] as const;
export type NotificationPriority = typeof notificationPriorities[number];

export const notificationTypes = [
  'MEDICAL_ALERT_CREATED',
  'ALERT_ACKNOWLEDGED',
  'ALERT_RESOLVED',
  'ALERT_DISMISSED',
  'SYSTEM',
] as const;
export type NotificationType = typeof notificationTypes[number];

export type Notification = {
  id: string;
  type: NotificationType;
  priority: NotificationPriority;
  title: string;
  message: string;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
  source_domain: string;
  source_type: string;
  source_id: string;
  event_code: string;
  metadata: Record<string, unknown>;
};

export type NotificationReadFilter = 'all' | 'unread' | 'read';

export type NotificationFilters = {
  read: NotificationReadFilter;
  priority?: NotificationPriority;
  type?: NotificationType;
};

export type PaginatedNotifications = {
  count: number;
  next: string | null;
  previous: string | null;
  results: Notification[];
};

export type UnreadCountResponse = { unread_count: number };
export type ReadAllResponse = { updated_count: number };
