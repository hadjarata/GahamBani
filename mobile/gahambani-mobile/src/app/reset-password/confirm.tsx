import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMemo, useRef, useState } from 'react';
import { Keyboard, StyleSheet, TextInput, View } from 'react-native';

import { AppButton, AppCard, AppInput, AppText, Screen } from '@/components/ui';
import { usePasswordResetConfirmation } from '@/features/auth/use-password-reset';
import { validateNewPassword } from '@/features/auth/validation';
import { sessionRoutes } from '@/features/session/session-routes';
import { useAppTheme } from '@/theme';

type FieldErrors = { new_password?: string; new_password_confirm?: string };

const errorMessages = {
  validation: 'Corrigez les champs indiqués.',
  invalid_link: 'Ce lien de réinitialisation est invalide ou a expiré. Demandez-en un nouveau.',
  rate_limited: 'Trop de tentatives. Patientez avant de réessayer.',
  network: 'Connexion au service impossible. Vérifiez votre réseau.',
  server: 'Le service est temporairement indisponible.',
  unexpected: 'Une erreur inattendue est survenue. Réessayez.',
} as const;

function singleParam(value: string | string[] | undefined): string {
  return typeof value === 'string' ? value : '';
}

export default function ResetPasswordConfirmScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ uid?: string | string[]; token?: string | string[] }>();
  const uid = singleParam(params.uid);
  const token = singleParam(params.token);
  const linkComplete = uid.length > 0 && token.length > 0;
  const theme = useAppTheme();
  const confirmationRef = useRef<TextInput>(null);
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [confirmationVisible, setConfirmationVisible] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const { state, submit, resetError } = usePasswordResetConfirmation();
  const loading = state.status === 'loading';
  const backendFields = state.status === 'error' ? state.fields : {};
  const errors = { ...backendFields, ...fieldErrors };

  const styles = useMemo(() => StyleSheet.create({
    content: { justifyContent: 'center', paddingBottom: theme.spacing.xxxl },
    header: { gap: theme.spacing.sm, marginBottom: theme.spacing.xl },
    form: { gap: theme.spacing.lg },
    notice: { marginBottom: theme.spacing.lg },
  }), [theme]);

  function updatePassword(value: string, confirmationField = false) {
    if (confirmationField) setConfirmation(value);
    else setPassword(value);
    setFieldErrors((current) => ({
      ...current,
      [confirmationField ? 'new_password_confirm' : 'new_password']: undefined,
    }));
    resetError();
  }

  function handleSubmit() {
    if (loading || !linkComplete) return;
    const nextErrors: FieldErrors = { new_password: validateNewPassword(password) };
    if (!confirmation) nextErrors.new_password_confirm = 'Confirmez votre nouveau mot de passe.';
    else if (password !== confirmation) {
      nextErrors.new_password_confirm = 'Les deux mots de passe ne correspondent pas.';
    }
    setFieldErrors(nextErrors);
    if (Object.values(nextErrors).some(Boolean)) return;
    Keyboard.dismiss();
    void submit({
      uid,
      token,
      new_password: password,
      new_password_confirm: confirmation,
    });
  }

  return (
    <Screen scroll contentStyle={styles.content}>
      <View style={styles.header}>
        <AppText variant="display">Nouveau mot de passe</AppText>
        <AppText tone="secondary">Choisissez un nouveau mot de passe sécurisé.</AppText>
      </View>

      {!linkComplete || (state.status === 'error' && state.kind === 'invalid_link') ? (
        <AppCard accessibilityLiveRegion="polite" accessibilityRole="alert" style={styles.notice}>
          <AppText tone="danger">{errorMessages.invalid_link}</AppText>
        </AppCard>
      ) : null}

      {state.status === 'error' && state.kind !== 'invalid_link' ? (
        <AppCard accessibilityLiveRegion="polite" accessibilityRole="alert" style={styles.notice}>
          <AppText tone="danger">{errorMessages[state.kind]}</AppText>
        </AppCard>
      ) : null}

      {state.status === 'success' ? (
        <AppCard accessibilityLiveRegion="polite" accessibilityRole="alert" style={styles.notice}>
          <AppText tone="success">Votre mot de passe a bien été modifié.</AppText>
        </AppCard>
      ) : null}

      {linkComplete && state.status !== 'success' ? (
        <View style={styles.form}>
          <AppInput
            label="Nouveau mot de passe"
            value={password}
            error={errors.new_password}
            onChangeText={(value) => updatePassword(value)}
            secureTextEntry={!passwordVisible}
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="new-password"
            textContentType="newPassword"
            returnKeyType="next"
            blurOnSubmit={false}
            onSubmitEditing={() => confirmationRef.current?.focus()}
            editable={!loading}
            actionLabel={passwordVisible ? 'Masquer' : 'Afficher'}
            onAction={() => setPasswordVisible((visible) => !visible)}
          />
          <AppInput
            ref={confirmationRef}
            label="Confirmer le nouveau mot de passe"
            value={confirmation}
            error={errors.new_password_confirm}
            onChangeText={(value) => updatePassword(value, true)}
            secureTextEntry={!confirmationVisible}
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="new-password"
            textContentType="newPassword"
            returnKeyType="done"
            onSubmitEditing={handleSubmit}
            editable={!loading}
            actionLabel={confirmationVisible ? 'Masquer' : 'Afficher'}
            onAction={() => setConfirmationVisible((visible) => !visible)}
          />
          <AppButton label="Modifier le mot de passe" onPress={handleSubmit} loading={loading} fullWidth />
        </View>
      ) : null}

      {state.status === 'success' ? (
        <AppButton
          label="Continuer vers la connexion"
          onPress={() => {
            setPassword('');
            setConfirmation('');
            router.replace(sessionRoutes.login);
          }}
          fullWidth
        />
      ) : null}

      {!linkComplete ? (
        <AppButton
          label="Demander un nouveau lien"
          variant="secondary"
          onPress={() => router.replace(sessionRoutes.forgotPassword)}
          fullWidth
        />
      ) : null}
    </Screen>
  );
}
