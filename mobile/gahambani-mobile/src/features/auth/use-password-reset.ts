import { useCallback, useRef, useState } from 'react';

import type { PasswordResetConfirmRequest, PasswordResetRequest } from '@/types/session';

import {
  PasswordResetError,
  type PasswordResetFailureKind,
  sendPasswordResetRequest,
  setNewPassword,
} from './password-reset';

type ResetState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success' }
  | {
      status: 'error';
      kind: PasswordResetFailureKind;
      fields: Partial<Record<'new_password' | 'new_password_confirm', string>>;
    };

function useProtectedSubmission<T>(operation: (data: T) => Promise<void>) {
  const [state, setState] = useState<ResetState>({ status: 'idle' });
  const inFlight = useRef(false);

  const submit = useCallback(async (data: T) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setState({ status: 'loading' });
    try {
      await operation(data);
      setState({ status: 'success' });
    } catch (error) {
      const safeError = error instanceof PasswordResetError
        ? error
        : new PasswordResetError('unexpected');
      setState({ status: 'error', kind: safeError.kind, fields: safeError.fields });
    } finally {
      inFlight.current = false;
    }
  }, [operation]);

  const resetError = useCallback(() => {
    setState((current) => current.status === 'error' ? { status: 'idle' } : current);
  }, []);

  return { state, submit, resetError };
}

export function usePasswordResetRequest() {
  return useProtectedSubmission<PasswordResetRequest>(sendPasswordResetRequest);
}

export function usePasswordResetConfirmation() {
  return useProtectedSubmission<PasswordResetConfirmRequest>(setNewPassword);
}
