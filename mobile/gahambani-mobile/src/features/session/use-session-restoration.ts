import { useCallback, useEffect, useRef, useState } from 'react';

import { restoreSession, type RestorationResult } from './restore-session';

export type RestorationState =
  | { status: 'loading' }
  | RestorationResult;

export function useSessionRestoration() {
  const [state, setState] = useState<RestorationState>({ status: 'loading' });
  const attempt = useRef(0);

  const retry = useCallback(async () => {
    const currentAttempt = ++attempt.current;
    setState({ status: 'loading' });
    const result = await restoreSession();
    if (attempt.current === currentAttempt) setState(result);
  }, []);

  useEffect(() => {
    const currentAttempt = ++attempt.current;
    void restoreSession().then((result) => {
      if (attempt.current === currentAttempt) setState(result);
    });
    return () => {
      attempt.current += 1;
    };
  }, []);

  return { state, retry };
}
