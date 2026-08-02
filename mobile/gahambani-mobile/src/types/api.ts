export type ApiErrorBody = {
  code?: string;
  detail?: string;
  errors?: Record<string, string[]>;
  retry_after?: number;
};
