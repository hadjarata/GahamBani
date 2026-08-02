export type SessionTokens = {
  accessToken: string;
  refreshToken: string;
};

export type RefreshResponse = {
  access: string;
  refresh?: string;
};

export type LoginCredentials = {
  email: string;
  password: string;
};

export type LoginResponse = {
  access: string;
  refresh: string;
};

export type RegisterRequest = {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  password: string;
  password_confirm: string;
};

export type RegisterResponse = {
  detail: string;
  user: { id: string; email: string; role: 'PATIENT' };
  profile: { id: string; profile_type: 'PATIENT' };
  onboarding: {
    is_complete: boolean;
    completion_percentage: number;
    missing_fields: string[];
  };
};

export type PasswordResetRequest = { email: string };
export type PasswordResetResponse = { detail: string };

export type PasswordResetConfirmRequest = {
  uid: string;
  token: string;
  new_password: string;
  new_password_confirm: string;
};

export type MessageResponse = { message: string };
