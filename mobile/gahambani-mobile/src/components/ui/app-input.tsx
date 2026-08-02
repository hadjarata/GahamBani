import { forwardRef, useMemo } from 'react';
import {
  Pressable,
  StyleSheet,
  TextInput,
  type TextInputProps,
  View,
} from 'react-native';
import { useAppTheme } from '@/theme';
import { AppText } from './app-text';

type Props = TextInputProps & {
  label: string;
  error?: string;
  hint?: string;
  actionLabel?: string;
  onAction?: () => void;
};

export const AppInput = forwardRef<TextInput, Props>(function AppInput(
  { label, error, hint, actionLabel, onAction, style, ...props }, ref,
) {
  const theme = useAppTheme();
  const help = error ?? hint;
  const styles = useMemo(() => StyleSheet.create({
    wrapper: { gap: theme.spacing.sm },
    inputContainer: {
      minHeight: theme.sizes.controlHeight, borderWidth: theme.sizes.border,
      borderColor: error ? theme.colors.danger : theme.colors.border,
      borderRadius: theme.radii.md, backgroundColor: theme.colors.surface,
      flexDirection: 'row', alignItems: 'center', paddingHorizontal: theme.spacing.lg,
    },
    input: { flex: 1, color: theme.colors.text, ...theme.typography.body },
    action: { padding: theme.spacing.sm },
  }), [error, theme]);

  return (
    <View style={styles.wrapper}>
      <AppText variant="label">{label}</AppText>
      <View style={styles.inputContainer}>
        <TextInput
          ref={ref} accessibilityLabel={label} accessibilityHint={help}
          placeholderTextColor={theme.colors.textMuted} {...props} style={[styles.input, style]}
        />
        {actionLabel && onAction ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={actionLabel}
            hitSlop={theme.spacing.sm}
            onPress={onAction}
            style={styles.action}
          >
            <AppText variant="label" tone="secondary">{actionLabel}</AppText>
          </Pressable>
        ) : null}
      </View>
      {help ? (
        <AppText
          accessibilityLiveRegion={error ? 'polite' : 'none'}
          variant="caption"
          tone={error ? 'danger' : 'muted'}
        >
          {help}
        </AppText>
      ) : null}
    </View>
  );
});
