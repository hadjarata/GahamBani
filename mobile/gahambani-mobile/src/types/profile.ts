export type UserRole = 'PATIENT' | 'DOCTOR';

type ProfileUser = {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  role: string;
};

type Onboarding = {
  is_complete: boolean;
  completion_percentage: number;
  missing_fields: string[];
};

export type CurrentProfile = {
  user: ProfileUser;
  profile_type: string;
  profile: Record<string, unknown>;
  onboarding: Onboarding;
};

export function isCurrentProfile(value: unknown): value is CurrentProfile {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<CurrentProfile>;
  return Boolean(
    candidate.user &&
      typeof candidate.user === 'object' &&
      typeof candidate.user.role === 'string' &&
      typeof candidate.profile_type === 'string' &&
      candidate.onboarding &&
      typeof candidate.onboarding === 'object' &&
      typeof candidate.onboarding.is_complete === 'boolean' &&
      Array.isArray(candidate.onboarding.missing_fields),
  );
}
