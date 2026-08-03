import { useLocalSearchParams } from 'expo-router';

import { DestinationPlaceholder } from '@/features/session/destination-placeholder';

export default function NotificationDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return (
    <DestinationPlaceholder
      title="Détail de la notification"
      description={id ? 'La notification est prête pour l’écran C07.' : 'Notification introuvable.'}
    />
  );
}
