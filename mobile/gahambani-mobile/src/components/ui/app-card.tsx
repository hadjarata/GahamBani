import { type PropsWithChildren, useMemo } from 'react';
import { StyleSheet, type ViewProps, View } from 'react-native';
import { useAppTheme } from '@/theme';

type Props = PropsWithChildren<ViewProps> & { elevated?: boolean };

export function AppCard({ elevated = false, style, ...props }: Props) {
  const theme = useAppTheme();
  const styles = useMemo(() => StyleSheet.create({
    card: {
      backgroundColor: theme.colors.surface, borderColor: theme.colors.border,
      borderWidth: theme.sizes.border, borderRadius: theme.radii.lg,
      padding: theme.spacing.lg, ...(elevated ? theme.shadows.sm : theme.shadows.none),
    },
  }), [elevated, theme]);
  return <View {...props} style={[styles.card, style]} />;
}
