import { Platform } from 'react-native';

const developmentBaseUrl = Platform.select({
  android: 'http://10.0.2.2:8000/api/v1',
  ios: 'http://127.0.0.1:8000/api/v1',
  web: 'http://127.0.0.1:8000/api/v1',
  default: 'http://127.0.0.1:8000/api/v1',
});

export const API_BASE_URL = (
  process.env.EXPO_PUBLIC_API_URL ?? developmentBaseUrl
).replace(/\/+$/, '');

export const API_TIMEOUT_MS = 15_000;
