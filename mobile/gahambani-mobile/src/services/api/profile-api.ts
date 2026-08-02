import { isCurrentProfile, type CurrentProfile } from '@/types/profile';
import { apiClient, bearerHeader } from './client';

export class InvalidProfileResponseError extends Error {
  constructor() {
    super('La réponse du profil est incohérente.');
    this.name = 'InvalidProfileResponseError';
  }
}

export async function getCurrentProfile(accessToken: string): Promise<CurrentProfile> {
  const response = await apiClient.get<unknown>('/profiles/me/', {
    headers: bearerHeader(accessToken),
  });
  if (!isCurrentProfile(response.data)) throw new InvalidProfileResponseError();
  return response.data;
}
