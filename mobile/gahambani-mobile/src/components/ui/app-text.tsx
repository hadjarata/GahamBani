import { type ComponentProps, useMemo } from 'react';
import { StyleSheet, Text } from 'react-native';
import { useAppTheme, type TypographyVariant } from '@/theme';

type Props = ComponentProps<typeof Text> & {
  variant?: TypographyVariant;
  tone?: 'default' | 'secondary' | 'muted' | 'danger' | 'success' | 'onPrimary';
};

export function AppText({ variant = 'body', tone = 'default', style, ...props }: Props) {
  const theme = useAppTheme();
  const color = {
    default: theme.colors.text, secondary: theme.colors.textSecondary,
    muted: theme.colors.textMuted, danger: theme.colors.danger,
    success: theme.colors.success, onPrimary: theme.colors.textOnPrimary,
  }[tone];
  const styles = useMemo(() => StyleSheet.create({
    text: { ...theme.typography[variant], color },
  }), [color, theme, variant]);
  return <Text {...props} style={[styles.text, style]} />;
}
