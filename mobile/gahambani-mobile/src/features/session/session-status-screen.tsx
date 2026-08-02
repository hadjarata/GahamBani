import { useMemo } from 'react';
import { StyleSheet, View } from 'react-native';

import {
  AppButton,
  AppLoadingIndicator,
  AppText,
  Screen,
} from '@/components/ui';
import { useAppTheme } from '@/theme';

type Props = {
  description: string;
  loading?: boolean;
  actionLabel?: string;
  onAction?: () => void;
  secondaryActionLabel?: string;
  onSecondaryAction?: () => void;
};

export function SessionStatusScreen({
  description,
  loading = false,
  actionLabel,
  onAction,
  secondaryActionLabel,
  onSecondaryAction,
}: Props) {
  const theme = useAppTheme();
  const styles = useMemo(() => StyleSheet.create({
    content: { alignItems: 'center', justifyContent: 'center', gap: theme.spacing.xl },
    logo: {
      width: theme.sizes.logo, height: theme.sizes.logo,
      alignItems: 'center', justifyContent: 'center',
      borderRadius: theme.radii.xl, backgroundColor: theme.colors.primary,
      ...theme.shadows.md,
    },
    description: { textAlign: 'center' },
    actions: { alignSelf: 'stretch', gap: theme.spacing.md },
  }), [theme]);

  return (
    <Screen contentStyle={styles.content}>
      <View style={styles.logo}>
        <AppText variant="display" tone="onPrimary">G</AppText>
      </View>
      <AppText variant="title">GahamBani</AppText>
      <AppText tone="secondary" style={styles.description}>{description}</AppText>
      {loading ? <AppLoadingIndicator accessibilityLabel="Chargement de la session" /> : null}
      {actionLabel && onAction ? (
        <View style={styles.actions}>
          <AppButton label={actionLabel} onPress={onAction} fullWidth />
          {secondaryActionLabel && onSecondaryAction ? (
            <AppButton
              label={secondaryActionLabel}
              onPress={onSecondaryAction}
              variant="ghost"
              fullWidth
            />
          ) : null}
        </View>
      ) : null}
    </Screen>
  );
}
