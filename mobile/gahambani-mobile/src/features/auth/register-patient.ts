import { isAxiosError } from 'axios';

import { requestRegistration } from '@/services/api/auth-api';
import type { ApiErrorBody } from '@/types/api';
import type { RegisterRequest, RegisterResponse } from '@/types/session';

export type RegistrationField =
  | 'first_name'
  | 'last_name'
  | 'email'
  | 'phone'
  | 'password'
  | 'password_confirm';

export type RegistrationFailureKind =
  | 'validation'
  | 'email_conflict'
  | 'rate_limited'
  | 'network'
  | 'server'
  | 'unexpected';

export class RegistrationError extends Error {
  constructor(
    public readonly kind: RegistrationFailureKind,
    public readonly fields: Partial<Record<RegistrationField, string>> = {},
  ) {
    super(kind);
    this.name = 'RegistrationError';
  }
}

const fieldMessages: Record<RegistrationField, string> = {
  first_name: 'Vérifiez le prénom saisi.',
  last_name: 'Vérifiez le nom saisi.',
  email: 'Vérifiez l’adresse email saisie.',
  phone: 'Vérifiez le numéro de téléphone saisi.',
  password: 'Le mot de passe ne respecte pas les règles de sécurité.',
  password_confirm: 'La confirmation du mot de passe est invalide.',
};

function safeFieldErrors(
  errors: ApiErrorBody['errors'],
): Partial<Record<RegistrationField, string>> {
  if (!errors) return {};
  const fields: Partial<Record<RegistrationField, string>> = {};
  for (const field of Object.keys(fieldMessages) as RegistrationField[]) {
    if (errors[field]?.length) fields[field] = fieldMessages[field];
  }
  return fields;
}

function classify(error: unknown): RegistrationError {
  if (!isAxiosError<ApiErrorBody>(error)) return new RegistrationError('unexpected');
  if (!error.response) return new RegistrationError('network');
  const { status, data } = error.response;
  if (status === 400) {
    return new RegistrationError('validation', safeFieldErrors(data.errors));
  }
  if (status === 409 || data.code === 'conflict') {
    return new RegistrationError('email_conflict', {
      email: 'Un compte utilise déjà cette adresse email.',
    });
  }
  if (status === 429) return new RegistrationError('rate_limited');
  if (status >= 500) return new RegistrationError('server');
  return new RegistrationError('unexpected');
}

export async function registerPatient(data: RegisterRequest): Promise<RegisterResponse> {
  try {
    return await requestRegistration(data);
  } catch (error) {
    throw classify(error);
  }
}
