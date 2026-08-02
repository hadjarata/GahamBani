import { useCallback, useRef, useState } from 'react';

import type { RegisterRequest, RegisterResponse } from '@/types/session';

import {
  registerPatient,
  RegistrationError,
  type RegistrationFailureKind,
  type RegistrationField,
} from './register-patient';

export type RegistrationState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; response: RegisterResponse }
  | {
      status: 'error';
      kind: RegistrationFailureKind;
      fields: Partial<Record<RegistrationField, string>>;
    };

export function useRegistration() {
  const [state, setState] = useState<RegistrationState>({ status: 'idle' });
  const inFlight = useRef(false);

  const submit = useCallback(async (data: RegisterRequest) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setState({ status: 'loading' });
    try {
      const response = await registerPatient(data);
      setState({ status: 'success', response });
    } catch (error) {
      const registrationError =
        error instanceof RegistrationError
          ? error
          : new RegistrationError('unexpected');
      setState({
        status: 'error',
        kind: registrationError.kind,
        fields: registrationError.fields,
      });
    } finally {
      inFlight.current = false;
    }
  }, []);

  const resetError = useCallback(() => {
    setState((current) => current.status === 'error' ? { status: 'idle' } : current);
  }, []);

  return { state, submit, resetError };
}
