import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Keyboard,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';

import {
  AppButton,
  AppCard,
  AppInput,
  AppText,
  Screen,
} from '@/components/ui';
import { useLogin } from '@/features/auth/use-login';
import { validateEmailAddress } from '@/features/auth/validation';
import { sessionRoutes } from '@/features/session/session-routes';
import { useSessionState } from '@/features/session/session-state';
import { useAppTheme } from '@/theme';

type FieldErrors = { email?: string; password?: string };

const errorMessages = {
  invalid_credentials: 'Email ou mot de passe incorrect.',
  rate_limited: 'Trop de tentatives. Patientez avant de réessayer.',
  network: 'Connexion au service impossible. Vérifiez votre réseau.',
  server: 'Le service est temporairement indisponible.',
  profile_unavailable: 'Connexion réussie, mais votre profil ne peut pas être chargé pour le moment.',
  unexpected: 'Une erreur inattendue est survenue. Réessayez.',
} as const;

function validate(email: string, password: string): FieldErrors {
  const errors: FieldErrors = {};
  const normalizedEmail = email.trim();
  const emailError = validateEmailAddress(normalizedEmail);
  if (emailError) errors.email = emailError;
  if (!password) errors.password = 'Saisissez votre mot de passe.';
  return errors;
}

export default function LoginScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ email?: string; registered?: string }>();
  const theme = useAppTheme();
  const passwordRef = useRef<TextInput>(null);
  const [email, setEmail] = useState(
    typeof params.email === 'string' ? params.email : '',
  );
  const [password, setPassword] = useState('');
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const { state, submit, resume } = useLogin();
  const setAuthenticated = useSessionState((session) => session.setAuthenticated);
  const loading = state.status === 'loading';

  const styles = useMemo(() => StyleSheet.create({
    content: { justifyContent: 'center' },
    header: { gap: theme.spacing.sm, marginBottom: theme.spacing.xl },
    form: { gap: theme.spacing.lg },
    error: { marginBottom: theme.spacing.lg },
    success: { marginBottom: theme.spacing.lg },
    forgot: { alignSelf: 'flex-end' },
  }), [theme]);

  useEffect(() => {
    if (state.status === 'success') {
      setAuthenticated(state.result.profile);
      router.replace(state.result.destination);
    }
  }, [router, setAuthenticated, state]);

  function handleSubmit() {
    if (loading) return;
    const errors = validate(email, password);
    setFieldErrors(errors);
    if (Object.values(errors).some(Boolean)) return;
    Keyboard.dismiss();
    void submit({ email: email.trim().toLowerCase(), password });
  }

  return (
    <Screen scroll contentStyle={styles.content}>
      <View style={styles.header}>
        <AppText variant="display">Connexion</AppText>
        <AppText tone="secondary">
          Accédez à votre espace de suivi GahamBani.
        </AppText>
      </View>

      {params.registered === '1' ? (
        <AppCard
          accessibilityLiveRegion="polite"
          accessibilityRole="alert"
          style={styles.success}
        >
          <AppText tone="success">
            Votre compte patient a été créé. Vous pouvez maintenant vous connecter.
          </AppText>
        </AppCard>
      ) : null}

      {state.status === 'error' ? (
        <AppCard
          accessibilityLiveRegion="polite"
          accessibilityRole="alert"
          style={styles.error}
        >
          <AppText tone="danger">{errorMessages[state.kind]}</AppText>
          {state.canResume ? (
            <AppButton
              label="Réessayer de charger mon profil"
              variant="secondary"
              onPress={() => void resume()}
              loading={loading}
              fullWidth
            />
          ) : null}
        </AppCard>
      ) : null}

      <View style={styles.form}>
        <AppInput
          label="Adresse email"
          value={email}
          error={fieldErrors.email}
          onChangeText={(value) => {
            setEmail(value);
            if (fieldErrors.email) setFieldErrors((current) => ({ ...current, email: undefined }));
          }}
          placeholder="nom@exemple.com"
          keyboardType="email-address"
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="email"
          textContentType="emailAddress"
          returnKeyType="next"
          blurOnSubmit={false}
          onSubmitEditing={() => passwordRef.current?.focus()}
          editable={!loading}
        />

        <AppInput
          ref={passwordRef}
          label="Mot de passe"
          value={password}
          error={fieldErrors.password}
          onChangeText={(value) => {
            setPassword(value);
            if (fieldErrors.password) {
              setFieldErrors((current) => ({ ...current, password: undefined }));
            }
          }}
          secureTextEntry={!passwordVisible}
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="current-password"
          textContentType="password"
          returnKeyType="done"
          onSubmitEditing={handleSubmit}
          editable={!loading}
          actionLabel={passwordVisible ? 'Masquer' : 'Afficher'}
          onAction={() => setPasswordVisible((visible) => !visible)}
        />

        <AppButton
          label="Mot de passe oublié ?"
          variant="ghost"
          onPress={() => router.push(sessionRoutes.forgotPassword)}
          style={styles.forgot}
          disabled={loading}
        />

        <AppButton
          label="Se connecter"
          onPress={handleSubmit}
          loading={loading}
          fullWidth
        />
        <AppButton
          label="Créer un compte patient"
          variant="secondary"
          onPress={() => router.push(sessionRoutes.register)}
          disabled={loading}
          fullWidth
        />
      </View>
    </Screen>
  );
}
