import { type Href, useRouter } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { FlatList, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';

import {
  AppBadge,
  AppButton,
  AppCard,
  AppLoadingIndicator,
  AppText,
  EmptyState,
  Screen,
} from '@/components/ui';
import { NotificationCard, typeLabels } from '@/features/notifications/notification-card';
import { useNotifications } from '@/features/notifications/use-notifications';
import { useUnreadNotificationCount } from '@/features/notifications/unread-count-store';
import { sessionRoutes } from '@/features/session/session-routes';
import { useSessionState } from '@/features/session/session-state';
import { useAppTheme } from '@/theme';
import {
  notificationPriorities,
  notificationTypes,
  type NotificationFilters,
  type NotificationPriority,
  type NotificationReadFilter,
  type NotificationType,
} from '@/types/notification';

const errorMessages = {
  unauthorized: 'Votre session a expiré. Reconnectez-vous.',
  forbidden: 'Vous n’avez pas accès à ces notifications.',
  not_found: 'La notification demandée est introuvable.',
  rate_limited: 'Trop de demandes. Patientez avant de réessayer.',
  network: 'Connexion au service impossible. Vérifiez votre réseau.',
  server: 'Le service est temporairement indisponible.',
  unexpected: 'Une erreur inattendue est survenue.',
} as const;

const readLabels: Record<NotificationReadFilter, string> = {
  all: 'Toutes', unread: 'Non lues', read: 'Lues',
};
const priorityLabels: Record<NotificationPriority, string> = {
  LOW: 'Faible', NORMAL: 'Normale', HIGH: 'Haute', CRITICAL: 'Critique',
};

export default function NotificationsScreen() {
  const router = useRouter();
  const theme = useAppTheme();
  const setAnonymous = useSessionState((session) => session.setAnonymous);
  const [read, setRead] = useState<NotificationReadFilter>('all');
  const [priority, setPriority] = useState<NotificationPriority>();
  const [type, setType] = useState<NotificationType>();
  const filters = useMemo<NotificationFilters>(() => ({ read, priority, type }), [priority, read, type]);
  const { state, refresh, loadMore, markRead, markAllRead } = useNotifications(filters);
  const unreadCount = useUnreadNotificationCount((store) => store.count);
  const unreadCountError = useUnreadNotificationCount((store) => store.error);
  const refreshUnreadCount = useUnreadNotificationCount((store) => store.refresh);

  useEffect(() => { void refreshUnreadCount(); }, [refreshUnreadCount]);
  useEffect(() => {
    if (state.error !== 'unauthorized' && unreadCountError !== 'unauthorized') return;
    setAnonymous();
    router.replace(sessionRoutes.login);
  }, [router, setAnonymous, state.error, unreadCountError]);

  const styles = useMemo(() => StyleSheet.create({
    screen: { paddingHorizontal: theme.spacing.none, paddingBottom: theme.spacing.none },
    header: { paddingHorizontal: theme.spacing.xl, paddingTop: theme.spacing.xl, gap: theme.spacing.md },
    titleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: theme.spacing.md },
    filters: { gap: theme.spacing.sm, paddingHorizontal: theme.spacing.xl },
    filterRow: { flexDirection: 'row', gap: theme.spacing.sm },
    filterButton: { minHeight: 40, paddingHorizontal: theme.spacing.md },
    list: { padding: theme.spacing.xl, gap: theme.spacing.md, flexGrow: 1 },
    separator: { height: theme.spacing.md },
    error: { marginHorizontal: theme.spacing.xl, marginTop: theme.spacing.md, gap: theme.spacing.md },
    footer: { paddingVertical: theme.spacing.xl },
  }), [theme]);

  function openNotification(notification: Parameters<typeof markRead>[0]) {
    void markRead(notification);
    router.push(`/notifications/${notification.id}` as Href);
  }

  async function refreshAll() {
    await Promise.all([refresh(), refreshUnreadCount()]);
  }

  const empty = !state.initialLoading && !state.error ? (
    <EmptyState
      title="Aucune notification"
      description="Aucune notification ne correspond aux filtres sélectionnés."
    />
  ) : null;

  return (
    <Screen contentStyle={styles.screen}>
      <View style={styles.header}>
        <View style={styles.titleRow}>
          <AppText variant="title">Notifications</AppText>
          {unreadCount > 0 ? <AppBadge tone="info">{unreadCount} non lue{unreadCount > 1 ? 's' : ''}</AppBadge> : null}
        </View>
        {unreadCount > 0 ? (
          <AppButton
            label="Tout marquer comme lu"
            variant="secondary"
            loading={state.markingAll}
            onPress={() => void markAllRead()}
            fullWidth
          />
        ) : null}
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}>
        <View style={styles.filterRow}>
          {(Object.keys(readLabels) as NotificationReadFilter[]).map((value) => (
            <AppButton
              key={value}
              label={readLabels[value]}
              variant={read === value ? 'primary' : 'secondary'}
              onPress={() => setRead(value)}
              style={styles.filterButton}
            />
          ))}
          <AppButton
            label={priority ? `Priorité : ${priorityLabels[priority]}` : 'Toutes priorités'}
            variant={priority ? 'primary' : 'secondary'}
            onPress={() => {
              const index = priority ? notificationPriorities.indexOf(priority) + 1 : 0;
              setPriority(notificationPriorities[index]);
            }}
            style={styles.filterButton}
          />
          <AppButton
            label={type ? typeLabels[type] : 'Tous les types'}
            variant={type ? 'primary' : 'secondary'}
            onPress={() => {
              const index = type ? notificationTypes.indexOf(type) + 1 : 0;
              setType(notificationTypes[index]);
            }}
            style={styles.filterButton}
          />
        </View>
      </ScrollView>

      {state.error && state.error !== 'unauthorized' ? (
        <AppCard style={styles.error} accessibilityRole="alert">
          <AppText tone="danger">{errorMessages[state.error]}</AppText>
          <AppButton label="Réessayer" variant="secondary" onPress={() => void refreshAll()} fullWidth />
        </AppCard>
      ) : null}

      {state.initialLoading ? (
        <AppLoadingIndicator accessibilityLabel="Chargement des notifications" />
      ) : (
        <FlatList
          data={state.items}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <NotificationCard notification={item} onPress={() => openNotification(item)} />
          )}
          contentContainerStyle={styles.list}
          ItemSeparatorComponent={() => <View style={styles.separator} />}
          ListEmptyComponent={empty}
          ListFooterComponent={state.loadingMore ? (
            <View style={styles.footer}><AppLoadingIndicator accessibilityLabel="Chargement de la suite" /></View>
          ) : null}
          refreshControl={<RefreshControl refreshing={state.refreshing} onRefresh={() => void refreshAll()} />}
          onEndReached={loadMore}
          onEndReachedThreshold={0.4}
        />
      )}
    </Screen>
  );
}
