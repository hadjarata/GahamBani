import { Platform, type TextStyle, type ViewStyle } from 'react-native';

export const palette = {
  blue50: '#EFF6FF', blue500: '#2F80ED', blue600: '#1D6FD6',
  slate50: '#F8FAFC', slate100: '#F1F5F9', slate200: '#E2E8F0',
  slate400: '#94A3B8', slate500: '#64748B', slate700: '#334155',
  slate900: '#0F172A', white: '#FFFFFF', black: '#000000',
  green50: '#F0FDF4', green600: '#16A34A',
  amber50: '#FFFBEB', amber600: '#D97706',
  red50: '#FEF2F2', red600: '#DC2626', red700: '#B91C1C',
} as const;

export const spacing = {
  none: 0, xxs: 2, xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48,
} as const;

export const radii = { none: 0, sm: 8, md: 12, lg: 16, xl: 20, full: 999 } as const;

export const sizes = {
  controlHeight: 48, iconSm: 16, iconMd: 24, iconLg: 32,
  logo: 72, contentMaxWidth: 560, border: 1, borderStrong: 2,
} as const;

export const fontFamilies = {
  regular: Platform.select({
    ios: 'System', android: 'sans-serif',
    web: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    default: 'System',
  }),
  medium: Platform.select({
    ios: 'System', android: 'sans-serif-medium',
    web: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    default: 'System',
  }),
} as const;

export const typography = {
  display: { fontFamily: fontFamilies.medium, fontSize: 32, lineHeight: 40, fontWeight: '700' },
  title: { fontFamily: fontFamilies.medium, fontSize: 24, lineHeight: 32, fontWeight: '700' },
  heading: { fontFamily: fontFamilies.medium, fontSize: 20, lineHeight: 28, fontWeight: '600' },
  body: { fontFamily: fontFamilies.regular, fontSize: 16, lineHeight: 24, fontWeight: '400' },
  bodyStrong: { fontFamily: fontFamilies.medium, fontSize: 16, lineHeight: 24, fontWeight: '600' },
  label: { fontFamily: fontFamilies.medium, fontSize: 14, lineHeight: 20, fontWeight: '600' },
  caption: { fontFamily: fontFamilies.regular, fontSize: 13, lineHeight: 18, fontWeight: '400' },
} satisfies Record<string, TextStyle>;

export const shadows = {
  none: {} as ViewStyle,
  sm: Platform.select<ViewStyle>({
    ios: { shadowColor: palette.black, shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.08, shadowRadius: 3 },
    android: { elevation: 2 }, default: {},
  }),
  md: Platform.select<ViewStyle>({
    ios: { shadowColor: palette.black, shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.1, shadowRadius: 10 },
    android: { elevation: 4 }, default: {},
  }),
} as const;

export type TypographyVariant = keyof typeof typography;
