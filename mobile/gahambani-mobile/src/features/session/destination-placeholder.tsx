import { EmptyState, Screen } from '@/components/ui';

type Props = { title: string; description: string };

export function DestinationPlaceholder({ title, description }: Props) {
  return (
    <Screen>
      <EmptyState title={title} description={description} />
    </Screen>
  );
}
