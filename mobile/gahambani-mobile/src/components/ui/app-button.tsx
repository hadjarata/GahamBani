import { useMemo } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, type PressableProps, type ViewStyle } from 'react-native';
import { useAppTheme } from '@/theme';
import { AppText } from './app-text';

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';
type Props = Omit<PressableProps, 'children' | 'style'> & {
  label: string; variant?: Variant; loading?: boolean; fullWidth?: boolean; style?: ViewStyle;
};

export function AppButton({
  label, variant = 'primary', loading = false, fullWidth = false, disabled, style, ...props
}: Props) {
  const theme = useAppTheme();
  const unavailable = disabled || loading;
  const styles = useMemo(() => StyleSheet.create({
    base: {
      minHeight: theme.sizes.controlHeight, paddingHorizontal: theme.spacing.xl,
      borderRadius: theme.radii.md, alignItems: 'center', justifyContent: 'center',
      borderWidth: theme.sizes.border,
    },
    full: { alignSelf: 'stretch' },
    primary: { backgroundColor: theme.colors.primary, borderColor: theme.colors.primary },
    secondary: { backgroundColor: theme.colors.surface, borderColor: theme.colors.border },
    danger: { backgroundColor: theme.colors.danger, borderColor: theme.colors.danger },
    ghost: { backgroundColor: 'transparent', borderColor: 'transparent' },
    disabled: { backgroundColor: theme.colors.disabled, borderColor: theme.colors.disabled },
    pressed: { opacity: 0.82 },
  }), [theme]);
  const solid = variant === 'primary' || variant === 'danger';

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: unavailable, busy: loading }}
      disabled={unavailable}
      {...props}
      style={({ pressed }) => [
        styles.base, styles[variant], fullWidth && styles.full,
        unavailable && styles.disabled, pressed && !unavailable && styles.pressed, style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={solid ? theme.colors.textOnPrimary : theme.colors.primary} />
      ) : (
        <AppText variant="bodyStrong" tone={unavailable ? 'muted' : solid ? 'onPrimary' : 'default'}>
          {label}
        </AppText>
      )}
    </Pressable>
  );
}
