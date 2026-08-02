import { ActivityIndicator, type ActivityIndicatorProps } from 'react-native';

import { useAppTheme } from '@/theme';

export function AppLoadingIndicator(props: ActivityIndicatorProps) {
  const theme = useAppTheme();
  return <ActivityIndicator color={theme.colors.primary} size="large" {...props} />;
}
