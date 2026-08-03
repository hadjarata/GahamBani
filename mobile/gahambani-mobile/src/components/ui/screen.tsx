import { type PropsWithChildren, useMemo } from 'react';
import { ScrollView, StyleSheet, View, type ViewStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAppTheme } from '@/theme';

type Props = PropsWithChildren<{ scroll?: boolean; contentStyle?: ViewStyle }>;

export function Screen({ children, scroll = false, contentStyle }: Props) {
  const theme = useAppTheme();
  const styles = useMemo(() => StyleSheet.create({
    safe: { flex: 1, backgroundColor: theme.colors.background },
    content: {
      flexGrow: 1, width: '100%', maxWidth: theme.sizes.contentMaxWidth,
      alignSelf: 'center', padding: theme.spacing.xl,
    },
  }), [theme]);
  return (
    <SafeAreaView style={styles.safe}>
      {scroll ? (
        <ScrollView
          contentContainerStyle={[styles.content, contentStyle]}
          keyboardShouldPersistTaps="handled"
        >
          {children}
        </ScrollView>
      ) : (
        <View style={[styles.content, contentStyle]}>{children}</View>
      )}
    </SafeAreaView>
  );
}
