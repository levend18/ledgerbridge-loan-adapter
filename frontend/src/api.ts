import type { Session } from "./types";
export class RequestError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function request<T>(
  path: string,
  session?: Session,
  body?: unknown,
): Promise<T> {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      "Content-Type": "application/json",
      ...(session ? { Authorization: `Bearer ${session.access}` } : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new RequestError(
      response.ok
        ? "Sunucudan geçersiz yanıt alındı. Lütfen yeniden deneyin."
        : `İşlem tamamlanamadı (HTTP ${response.status}). Lütfen yeniden deneyin.`,
      response.status,
    );
  }
  if (!response.ok)
    throw new RequestError(
      problemMessage(data) || `İşlem tamamlanamadı (HTTP ${response.status})`,
      response.status,
    );
  return data as T;
}
function problemMessage(data: unknown): string | undefined {
  if (!data || typeof data !== "object") return;
  const problem = data as Record<string, unknown>;
  for (const key of ["detail", "title"]) {
    if (typeof problem[key] === "string" && problem[key]) return problem[key];
  }
}
export const label = (value: string) => value.replaceAll("_", " ");
export const terminal = (status?: string) =>
  !!status && ["SUCCEEDED", "REJECTED", "FAILED", "SKIPPED"].includes(status);
export function sessionFromToken(access: string, username: string): Session {
  const payload = JSON.parse(
    atob(access.split(".")[1].replaceAll("-", "+").replaceAll("_", "/")),
  );
  return { access, username, tenant: payload.tenant_id };
}
