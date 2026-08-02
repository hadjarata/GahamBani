import { type PropsWithChildren, useMemo } from 'react';
import { StyleSheet, View } from 'react-native';
import { useAppTheme } from '@/theme';
import { AppText } from './app-text';

type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

export function AppBadge({ children, tone = 'neutral' }: PropsWithChildren<{ tone?: Tone }>) {
  const theme = useAppTheme();
  const backgroundColor = {
    neutral: theme.colors.surfaceMuted, info: theme.colors.primarySubtle,
    success: theme.colors.successSubtle, warning: theme.colors.warningSubtle,
    danger: theme.colors.dangerSubtle,
  }[tone];
  const styles = useMemo(() => StyleSheet.create({
    badge: {
      alignSelf: 'flex-start', borderRadius: theme.radii.full,
      paddingHorizontal: theme.spacing.md, paddingVertical: theme.spacing.xs, backgroundColor,
    },
  }), [backgroundColor, theme]);
  return (
    <View style={styles.badge}>
      <AppText variant="caption" tone={tone === 'danger' ? 'danger' : tone === 'success' ? 'success' : 'secondary'}>
        {children}
      </AppText>
    </View>
  );
}
