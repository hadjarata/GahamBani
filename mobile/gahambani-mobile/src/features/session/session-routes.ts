import type { Href } from 'expo-router';

export const sessionRoutes = {
  login: '/auth/login' as Href,
  register: '/auth/register' as Href,
  forgotPassword: '/auth/forgot-password' as Href,
  patientOnboarding: '/onboarding/health' as Href,
  patientHome: '/patient' as Href,
  doctorHome: '/doctor' as Href,
} as const;

export type SessionDestination =
  | typeof sessionRoutes.patientOnboarding
  | typeof sessionRoutes.patientHome
  | typeof sessionRoutes.doctorHome;
