import { type Href, useRouter } from 'expo-router';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Keyboard, StyleSheet, TextInput, View } from 'react-native';

import {
  AppButton,
  AppCard,
  AppInput,
  AppText,
  Screen,
} from '@/components/ui';
import { useRegistration } from '@/features/auth/use-registration';
import {
  validateEmailAddress,
  validateNewPassword,
} from '@/features/auth/validation';
import { sessionRoutes } from '@/features/session/session-routes';
import { useAppTheme } from '@/theme';
import type { RegisterRequest } from '@/types/session';

type FieldErrors = Partial<Record<keyof RegisterRequest, string>>;

const errorMessages = {
  validation: 'Certains champs doivent être corrigés.',
  email_conflict: 'Cette adresse email est déjà associée à un compte.',
  rate_limited: 'Trop de tentatives. Patientez avant de réessayer.',
  network: 'Connexion au service impossible. Vérifiez votre réseau.',
  server: 'Le compte ne peut pas être créé pour le moment.',
  unexpected: 'Une erreur inattendue est survenue. Réessayez.',
} as const;

function validate(values: RegisterRequest): FieldErrors {
  const errors: FieldErrors = {};
  if (!values.first_name.trim()) errors.first_name = 'Saisissez votre prénom.';
  else if (values.first_name.trim().length > 150) errors.first_name = 'Le prénom est trop long.';
  if (!values.last_name.trim()) errors.last_name = 'Saisissez votre nom.';
  else if (values.last_name.trim().length > 150) errors.last_name = 'Le nom est trop long.';

  const emailError = validateEmailAddress(values.email);
  if (emailError) errors.email = emailError;

  const phone = values.phone.trim();
  if (!phone) errors.phone = 'Saisissez votre numéro de téléphone.';
  else if (phone.length > 30) errors.phone = 'Le numéro ne peut pas dépasser 30 caractères.';

  const passwordError = validateNewPassword(values.password);
  if (passwordError) errors.password = passwordError;
  if (!values.password_confirm) {
    errors.password_confirm = 'Confirmez votre mot de passe.';
  } else if (values.password !== values.password_confirm) {
    errors.password_confirm = 'Les deux mots de passe ne correspondent pas.';
  }
  return errors;
}

const emptyValues: RegisterRequest = {
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  password: '',
  password_confirm: '',
};

export default function RegisterScreen() {
  const router = useRouter();
  const theme = useAppTheme();
  const lastNameRef = useRef<TextInput>(null);
  const emailRef = useRef<TextInput>(null);
  const phoneRef = useRef<TextInput>(null);
  const passwordRef = useRef<TextInput>(null);
  const confirmationRef = useRef<TextInput>(null);
  const [values, setValues] = useState<RegisterRequest>(emptyValues);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [confirmationVisible, setConfirmationVisible] = useState(false);
  const { state, submit, resetError } = useRegistration();
  const loading = state.status === 'loading';
  const backendErrors = state.status === 'error' ? state.fields : {};
  const errors = { ...backendErrors, ...fieldErrors };

  const styles = useMemo(() => StyleSheet.create({
    content: { paddingBottom: theme.spacing.xxxl },
    header: { gap: theme.spacing.sm, marginBottom: theme.spacing.xl },
    form: { gap: theme.spacing.lg },
    error: { marginBottom: theme.spacing.lg },
  }), [theme]);

  useEffect(() => {
    if (state.status === 'success') {
      const email = encodeURIComponent(state.response.user.email);
      router.replace(`/auth/login?email=${email}&registered=1` as Href);
    }
  }, [router, state]);

  function update(field: keyof RegisterRequest, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setFieldErrors((current) => ({ ...current, [field]: undefined }));
    resetError();
  }

  function handleSubmit() {
    if (loading) return;
    const validationErrors = validate(values);
    setFieldErrors(validationErrors);
    if (Object.values(validationErrors).some(Boolean)) return;
    Keyboard.dismiss();
    void submit({
      ...values,
      first_name: values.first_name.trim(),
      last_name: values.last_name.trim(),
      email: values.email.trim().toLowerCase(),
      phone: values.phone.trim(),
    });
  }

  return (
    <Screen scroll contentStyle={styles.content}>
      <View style={styles.header}>
        <AppText variant="display">Créer un compte</AppText>
        <AppText tone="secondary">
          Inscrivez-vous en tant que patient GahamBani.
        </AppText>
      </View>

      {state.status === 'error' ? (
        <AppCard accessibilityRole="alert" accessibilityLiveRegion="polite" style={styles.error}>
          <AppText tone="danger">{errorMessages[state.kind]}</AppText>
        </AppCard>
      ) : null}

      <View style={styles.form}>
        <AppInput
          label="Prénom"
          value={values.first_name}
          error={errors.first_name}
          onChangeText={(value) => update('first_name', value)}
          autoComplete="given-name"
          textContentType="givenName"
          autoCapitalize="words"
          returnKeyType="next"
          onSubmitEditing={() => lastNameRef.current?.focus()}
          editable={!loading}
        />
        <AppInput
          ref={lastNameRef}
          label="Nom"
          value={values.last_name}
          error={errors.last_name}
          onChangeText={(value) => update('last_name', value)}
          autoComplete="family-name"
          textContentType="familyName"
          autoCapitalize="words"
          returnKeyType="next"
          onSubmitEditing={() => emailRef.current?.focus()}
          editable={!loading}
        />
        <AppInput
          ref={emailRef}
          label="Adresse email"
          value={values.email}
          error={errors.email}
          onChangeText={(value) => update('email', value)}
          keyboardType="email-address"
          autoComplete="email"
          textContentType="emailAddress"
          autoCapitalize="none"
          autoCorrect={false}
          returnKeyType="next"
          onSubmitEditing={() => phoneRef.current?.focus()}
          editable={!loading}
        />
        <AppInput
          ref={phoneRef}
          label="Téléphone"
          value={values.phone}
          error={errors.phone}
          onChangeText={(value) => update('phone', value)}
          keyboardType="phone-pad"
          autoComplete="tel"
          textContentType="telephoneNumber"
          returnKeyType="next"
          onSubmitEditing={() => passwordRef.current?.focus()}
          editable={!loading}
        />
        <AppInput
          ref={passwordRef}
          label="Mot de passe"
          value={values.password}
          error={errors.password}
          hint="8 caractères minimum, pas uniquement des chiffres."
          onChangeText={(value) => update('password', value)}
          secureTextEntry={!passwordVisible}
          autoComplete="new-password"
          textContentType="newPassword"
          autoCapitalize="none"
          autoCorrect={false}
          returnKeyType="next"
          onSubmitEditing={() => confirmationRef.current?.focus()}
          editable={!loading}
          actionLabel={passwordVisible ? 'Masquer' : 'Afficher'}
          onAction={() => setPasswordVisible((visible) => !visible)}
        />
        <AppInput
          ref={confirmationRef}
          label="Confirmer le mot de passe"
          value={values.password_confirm}
          error={errors.password_confirm}
          onChangeText={(value) => update('password_confirm', value)}
          secureTextEntry={!confirmationVisible}
          autoComplete="new-password"
          textContentType="newPassword"
          autoCapitalize="none"
          autoCorrect={false}
          returnKeyType="done"
          onSubmitEditing={handleSubmit}
          editable={!loading}
          actionLabel={confirmationVisible ? 'Masquer' : 'Afficher'}
          onAction={() => setConfirmationVisible((visible) => !visible)}
        />

        <AppButton
          label="Créer mon compte"
          onPress={handleSubmit}
          loading={loading}
          fullWidth
        />
        <AppButton
          label="J’ai déjà un compte"
          variant="ghost"
          onPress={() => router.replace(sessionRoutes.login)}
          disabled={loading}
          fullWidth
        />
      </View>
    </Screen>
  );
}
