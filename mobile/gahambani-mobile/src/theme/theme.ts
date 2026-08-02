import {
  DarkTheme,
  DefaultTheme,
  type Theme as NavigationTheme,
} from 'expo-router/react-navigation';
import { palette, radii, shadows, sizes, spacing, typography } from './tokens';

const lightColors = {
  primary: palette.blue500, primaryPressed: palette.blue600, primarySubtle: palette.blue50,
  background: palette.slate50, surface: palette.white, surfaceMuted: palette.slate100,
  text: palette.slate900, textSecondary: palette.slate700, textMuted: palette.slate500,
  textOnPrimary: palette.white, border: palette.slate200, borderFocused: palette.blue500,
  disabled: palette.slate200, disabledText: palette.slate500,
  success: palette.green600, successSubtle: palette.green50,
  warning: palette.amber600, warningSubtle: palette.amber50,
  danger: palette.red600, dangerPressed: palette.red700, dangerSubtle: palette.red50,
  overlay: 'rgba(15, 23, 42, 0.48)',
} as const;

const darkColors = {
  primary: palette.blue500, primaryPressed: palette.blue600, primarySubtle: palette.slate700,
  background: palette.slate900, surface: palette.slate700, surfaceMuted: palette.slate700,
  text: palette.slate50, textSecondary: palette.slate200, textMuted: palette.slate400,
  textOnPrimary: palette.white, border: palette.slate500, borderFocused: palette.blue500,
  disabled: palette.slate700, disabledText: palette.slate400,
  success: palette.green600, successSubtle: palette.slate700,
  warning: palette.amber600, warningSubtle: palette.slate700,
  danger: palette.red600, dangerPressed: palette.red700, dangerSubtle: palette.slate700,
  overlay: 'rgba(0, 0, 0, 0.64)',
} as const;

function navigationTheme(base: NavigationTheme, colors: typeof lightColors | typeof darkColors): NavigationTheme {
  return {
    ...base,
    colors: {
      ...base.colors, primary: colors.primary, background: colors.background,
      card: colors.surface, text: colors.text, border: colors.border, notification: colors.danger,
    },
  };
}

export const lightTheme = {
  mode: 'light', colors: lightColors, spacing, radii, sizes, typography, shadows,
  navigation: navigationTheme(DefaultTheme, lightColors),
} as const;

export const darkTheme = {
  mode: 'dark', colors: darkColors, spacing, radii, sizes, typography, shadows,
  navigation: navigationTheme(DarkTheme, darkColors),
} as const;

export type AppTheme = typeof lightTheme | typeof darkTheme;
