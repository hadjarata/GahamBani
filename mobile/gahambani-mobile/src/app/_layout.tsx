import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';

import { AppThemeProvider } from '@/theme';

SplashScreen.preventAutoHideAsync().catch(() => {
  // Le splash peut déjà être contrôlé pendant le rechargement à chaud.
});

export default function RootLayout() {
  useEffect(() => {
    SplashScreen.hideAsync().catch(() => {
      // Évite de bloquer l'application si le splash est déjà masqué.
    });
  }, []);

  return (
    <AppThemeProvider>
      <Stack
        screenOptions={{
          headerShown: false,
          animation: 'fade',
        }}
      />
    </AppThemeProvider>
  );
}
