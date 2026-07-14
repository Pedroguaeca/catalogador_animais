export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function apiHeaders(
  idToken?: string | null,
  extra: Record<string, string> = {},
): Record<string, string> {
  const h: Record<string, string> = { ...extra };
  if (idToken) h["Authorization"] = `Bearer ${idToken}`;
  return h;
}
