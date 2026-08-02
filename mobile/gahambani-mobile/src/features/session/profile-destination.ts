import type { CurrentProfile } from '@/types/profile';

import { sessionRoutes, type SessionDestination } from './session-routes';

export function getProfileDestination(profile: CurrentProfile): SessionDestination | null {
  if (profile.user.role !== profile.profile_type) return null;
  if (profile.user.role === 'PATIENT') {
    return profile.onboarding.is_complete
      ? sessionRoutes.patientHome
      : sessionRoutes.patientOnboarding;
  }
  if (profile.user.role === 'DOCTOR') return sessionRoutes.doctorHome;
  return null;
}
