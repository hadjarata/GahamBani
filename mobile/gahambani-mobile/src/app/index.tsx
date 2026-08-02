import { useRouter } from 'expo-router';
import { useEffect } from 'react';

import { sessionRoutes } from '@/features/session/session-routes';
import { useSessionState } from '@/features/session/session-state';
import { SessionStatusScreen } from '@/features/session/session-status-screen';
import { useSessionRestoration } from '@/features/session/use-session-restoration';

export default function SplashScreen() {
  const router = useRouter();
  const { state, retry } = useSessionRestoration();
  const setAnonymous = useSessionState((session) => session.setAnonymous);
  const setAuthenticated = useSessionState((session) => session.setAuthenticated);

  useEffect(() => {
    if (state.status === 'unauthenticated') {
      setAnonymous();
      router.replace(sessionRoutes.login);
    } else if (state.status === 'authenticated') {
      setAuthenticated(state.profile);
      router.replace(state.destination);
    } else if (state.status === 'inconsistent-session') {
      setAnonymous();
    }
  }, [router, setAnonymous, setAuthenticated, state]);

  if (state.status === 'recoverable-error') {
    return (
      <SessionStatusScreen
        description="Impossible de joindre le service pour le moment. Votre session a été conservée."
        actionLabel="Réessayer"
        onAction={() => void retry()}
      />
    );
  }

  if (state.status === 'inconsistent-session') {
    return (
      <SessionStatusScreen
        description="La session ne peut pas être restaurée. Reconnectez-vous pour continuer."
        actionLabel="Aller à la connexion"
        onAction={() => router.replace(sessionRoutes.login)}
      />
    );
  }

  return (
    <SessionStatusScreen
      description="Préparation de votre espace sécurisé…"
      loading
    />
  );
}
