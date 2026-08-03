import { isAxiosError } from 'axios';

import {
  confirmPasswordReset,
  requestPasswordReset,
} from '@/services/api/auth-api';
import type { ApiErrorBody } from '@/types/api';
import type {
  PasswordResetConfirmRequest,
  PasswordResetRequest,
} from '@/types/session';

export type PasswordResetFailureKind =
  | 'validation'
  | 'invalid_link'
  | 'rate_limited'
  | 'network'
  | 'server'
  | 'unexpected';

export class PasswordResetError extends Error {
  constructor(
    public readonly kind: PasswordResetFailureKind,
    public readonly fields: Partial<Record<'new_password' | 'new_password_confirm', string>> = {},
  ) {
    super(kind);
    this.name = 'PasswordResetError';
  }
}

function classify(error: unknown, confirmation: boolean): PasswordResetError {
  if (!isAxiosError<ApiErrorBody>(error)) return new PasswordResetError('unexpected');
  if (!error.response) return new PasswordResetError('network');

  const { status, data } = error.response;
  if (status === 429) return new PasswordResetError('rate_limited');
  if (status >= 500) return new PasswordResetError('server');
  if (status === 400) {
    if (!confirmation) return new PasswordResetError('validation');
    const errors = data.errors;
    if (errors?.new_password?.length) {
      return new PasswordResetError('validation', {
        new_password: 'Le mot de passe ne respecte pas les règles de sécurité.',
      });
    }
    if (errors?.new_password_confirm?.length) {
      return new PasswordResetError('validation', {
        new_password_confirm: 'La confirmation du mot de passe est invalide.',
      });
    }
    return new PasswordResetError('invalid_link');
  }
  return new PasswordResetError('unexpected');
}

export async function sendPasswordResetRequest(data: PasswordResetRequest): Promise<void> {
  try {
    await requestPasswordReset(data);
  } catch (error) {
    throw classify(error, false);
  }
}

export async function setNewPassword(data: PasswordResetConfirmRequest): Promise<void> {
  try {
    await confirmPasswordReset(data);
  } catch (error) {
    throw classify(error, true);
  }
}
