export function validateEmailAddress(value: string): string | undefined {
  const email = value.trim();
  if (!email) return 'Saisissez votre adresse email.';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return 'Saisissez une adresse email valide.';
  }
  if (email.length > 254) return 'L’adresse email est trop longue.';
  return undefined;
}

export function validateNewPassword(value: string): string | undefined {
  if (!value) return 'Saisissez un mot de passe.';
  if (value.length < 8) return 'Utilisez au moins 8 caractères.';
  if (/^\d+$/.test(value)) {
    return 'Le mot de passe ne peut pas être entièrement numérique.';
  }
  return undefined;
}
