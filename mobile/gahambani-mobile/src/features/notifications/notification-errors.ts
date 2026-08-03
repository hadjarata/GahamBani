import { isAxiosError } from 'axios';

import { SessionExpiredError } from '@/services/api/authenticated-request';

export type NotificationFailureKind =
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'rate_limited'
  | 'network'
  | 'server'
  | 'unexpected';

export class NotificationError extends Error {
  constructor(public readonly kind: NotificationFailureKind) {
    super(kind);
    this.name = 'NotificationError';
  }
}

export function toNotificationError(error: unknown): NotificationError {
  if (error instanceof SessionExpiredError) return new NotificationError('unauthorized');
  if (!isAxiosError(error)) return new NotificationError('unexpected');
  if (!error.response) return new NotificationError('network');
  const status = error.response.status;
  if (status === 401) return new NotificationError('unauthorized');
  if (status === 403) return new NotificationError('forbidden');
  if (status === 404) return new NotificationError('not_found');
  if (status === 429) return new NotificationError('rate_limited');
  if (status >= 500) return new NotificationError('server');
  return new NotificationError('unexpected');
}
