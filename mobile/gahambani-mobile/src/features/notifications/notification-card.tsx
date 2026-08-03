import { useMemo } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppBadge, AppCard, AppText } from '@/components/ui';
import { useAppTheme } from '@/theme';
import type { Notification, NotificationPriority, NotificationType } from '@/types/notification';

const priorityLabels: Record<NotificationPriority, string> = {
  LOW: 'Faible', NORMAL: 'Normale', HIGH: 'Haute', CRITICAL: 'Critique',
};

const priorityTones = {
  LOW: 'neutral', NORMAL: 'info', HIGH: 'warning', CRITICAL: 'danger',
} as const;

export const typeLabels: Record<NotificationType, string> = {
  MEDICAL_ALERT_CREATED: 'Nouvelle alerte',
  ALERT_ACKNOWLEDGED: 'Alerte prise en charge',
  ALERT_RESOLVED: 'Alerte résolue',
  ALERT_DISMISSED: 'Alerte écartée',
  SYSTEM: 'Système',
};

type Props = { notification: Notification; onPress: () => void };

export function NotificationCard({ notification, onPress }: Props) {
  const theme = useAppTheme();
  const date = useMemo(() => new Intl.DateTimeFormat('fr-FR', {
    dateStyle: 'medium', timeStyle: 'short',
  }).format(new Date(notification.created_at)), [notification.created_at]);
  const styles = useMemo(() => StyleSheet.create({
    card: { gap: theme.spacing.sm },
    unread: {
      backgroundColor: theme.colors.primarySubtle,
      borderLeftColor: theme.colors.primary,
      borderLeftWidth: theme.sizes.borderStrong,
    },
    header: { flexDirection: 'row', justifyContent: 'space-between', gap: theme.spacing.md },
    title: { flex: 1 },
    badges: { flexDirection: 'row', flexWrap: 'wrap', gap: theme.spacing.sm },
  }), [theme]);

  return (
    <Pressable accessibilityRole="button" onPress={onPress}>
      <AppCard style={[styles.card, !notification.is_read && styles.unread]}>
        <View style={styles.header}>
          <AppText variant="bodyStrong" style={styles.title}>{notification.title}</AppText>
          {!notification.is_read ? <AppBadge tone="info">Non lue</AppBadge> : null}
        </View>
        <AppText tone="secondary" numberOfLines={2}>{notification.message}</AppText>
        <View style={styles.badges}>
          <AppBadge tone={priorityTones[notification.priority]}>
            {priorityLabels[notification.priority]}
          </AppBadge>
          <AppBadge>{typeLabels[notification.type]}</AppBadge>
          <AppBadge>{date}</AppBadge>
        </View>
      </AppCard>
    </Pressable>
  );
}
