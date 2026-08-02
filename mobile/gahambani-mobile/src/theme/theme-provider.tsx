import { StatusBar } from 'expo-status-bar';
import { ThemeProvider as NavigationThemeProvider } from 'expo-router/react-navigation';
import { createContext, type PropsWithChildren, useContext, useMemo } from 'react';
import { useColorScheme } from 'react-native';

import { darkTheme, lightTheme, type AppTheme } from './theme';

const AppThemeContext = createContext<AppTheme | null>(null);

export function AppThemeProvider({ children }: PropsWithChildren) {
  const colorScheme = useColorScheme();
  const theme = useMemo(() => colorScheme === 'dark' ? darkTheme : lightTheme, [colorScheme]);

  return (
    <AppThemeContext.Provider value={theme}>
      <NavigationThemeProvider value={theme.navigation}>
        <StatusBar style={theme.mode === 'dark' ? 'light' : 'dark'} />
        {children}
      </NavigationThemeProvider>
    </AppThemeContext.Provider>
  );
}

export function useAppTheme(): AppTheme {
  const theme = useContext(AppThemeContext);
  if (!theme) throw new Error('useAppTheme doit être utilisé dans AppThemeProvider.');
  return theme;
}
