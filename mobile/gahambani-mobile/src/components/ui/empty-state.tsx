import { useMemo } from 'react';
import { StyleSheet, View } from 'react-native';
import { useAppTheme } from '@/theme';
import { AppButton } from './app-button';
import { AppText } from './app-text';

type Props = { title: string; description: string; actionLabel?: string; onAction?: () => void };

export function EmptyState({ title, description, actionLabel, onAction }: Props) {
  const theme = useAppTheme();
  const styles = useMemo(() => StyleSheet.create({
    root: { alignItems: 'center', gap: theme.spacing.md, paddingVertical: theme.spacing.xxxl },
    description: { textAlign: 'center' },
    action: { marginTop: theme.spacing.sm },
  }), [theme]);
  return (
    <View style={styles.root}>
      <AppText variant="heading">{title}</AppText>
      <AppText tone="secondary" style={styles.description}>{description}</AppText>
      {actionLabel && onAction ? <AppButton label={actionLabel} onPress={onAction} style={styles.action} /> : null}
    </View>
  );
}
