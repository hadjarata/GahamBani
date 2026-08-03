import { useRouter } from 'expo-router';
import { useMemo, useState } from 'react';
import { Keyboard, StyleSheet, View } from 'react-native';

import { AppButton, AppCard, AppInput, AppText, Screen } from '@/components/ui';
import { usePasswordResetRequest } from '@/features/auth/use-password-reset';
import { validateEmailAddress } from '@/features/auth/validation';
import { sessionRoutes } from '@/features/session/session-routes';
import { useAppTheme } from '@/theme';

const neutralMessage =
  'Si un compte correspond à cette adresse, un lien de réinitialisation vous sera envoyé.';

const errorMessages = {
  validation: 'Vérifiez l’adresse email saisie.',
  invalid_link: 'Le lien de réinitialisation est invalide ou expiré.',
  rate_limited: 'Trop de demandes. Patientez avant de réessayer.',
  network: 'Connexion au service impossible. Vérifiez votre réseau.',
  server: 'Le service est temporairement indisponible.',
  unexpected: 'Une erreur inattendue est survenue. Réessayez.',
} as const;

export default function ForgotPasswordScreen() {
  const router = useRouter();
  const theme = useAppTheme();
  const [email, setEmail] = useState('');
  const [emailError, setEmailError] = useState<string>();
  const { state, submit, resetError } = usePasswordResetRequest();
  const loading = state.status === 'loading';

  const styles = useMemo(() => StyleSheet.create({
    content: { justifyContent: 'center' },
    header: { gap: theme.spacing.sm, marginBottom: theme.spacing.xl },
    form: { gap: theme.spacing.lg },
    notice: { marginBottom: theme.spacing.lg },
  }), [theme]);

  function handleSubmit() {
    if (loading) return;
    const error = validateEmailAddress(email);
    setEmailError(error);
    if (error) return;
    Keyboard.dismiss();
    void submit({ email: email.trim().toLowerCase() });
  }

  return (
    <Screen scroll contentStyle={styles.content}>
      <View style={styles.header}>
        <AppText variant="display">Mot de passe oublié</AppText>
        <AppText tone="secondary">
          Saisissez votre adresse email pour recevoir les instructions.
        </AppText>
      </View>

      {state.status === 'success' ? (
        <AppCard accessibilityLiveRegion="polite" accessibilityRole="alert" style={styles.notice}>
          <AppText tone="success">{neutralMessage}</AppText>
        </AppCard>
      ) : null}

      {state.status === 'error' ? (
        <AppCard accessibilityLiveRegion="polite" accessibilityRole="alert" style={styles.notice}>
          <AppText tone="danger">{errorMessages[state.kind]}</AppText>
        </AppCard>
      ) : null}

      <View style={styles.form}>
        <AppInput
          label="Adresse email"
          value={email}
          error={emailError}
          onChangeText={(value) => {
            setEmail(value);
            setEmailError(undefined);
            resetError();
          }}
          placeholder="nom@exemple.com"
          keyboardType="email-address"
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="email"
          textContentType="emailAddress"
          returnKeyType="send"
          onSubmitEditing={handleSubmit}
          editable={!loading}
        />
        <AppButton label="Envoyer le lien" onPress={handleSubmit} loading={loading} fullWidth />
        <AppButton
          label="Retour à la connexion"
          variant="ghost"
          onPress={() => router.replace(sessionRoutes.login)}
          disabled={loading}
          fullWidth
        />
      </View>
    </Screen>
  );
}
