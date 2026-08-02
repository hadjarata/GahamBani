import { useCallback, useRef, useState } from 'react';

import type { LoginCredentials } from '@/types/session';

import {
  resumeSignIn,
  signIn,
  SignInError,
  type SignInFailureKind,
  type SignInResult,
} from './sign-in';

export type LoginState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; result: SignInResult }
  | { status: 'error'; kind: SignInFailureKind; canResume: boolean };

export function useLogin() {
  const [state, setState] = useState<LoginState>({ status: 'idle' });
  const inFlight = useRef(false);

  const run = useCallback(async (operation: () => Promise<SignInResult>) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setState({ status: 'loading' });
    try {
      const result = await operation();
      setState({ status: 'success', result });
    } catch (error) {
      const kind = error instanceof SignInError ? error.kind : 'unexpected';
      setState({ status: 'error', kind, canResume: kind === 'profile_unavailable' });
    } finally {
      inFlight.current = false;
    }
  }, []);

  const submit = useCallback(
    (credentials: LoginCredentials) => run(() => signIn(credentials)),
    [run],
  );
  const resume = useCallback(() => run(resumeSignIn), [run]);

  return { state, submit, resume };
}
