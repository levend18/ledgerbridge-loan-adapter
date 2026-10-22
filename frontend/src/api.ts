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
  const data = await response.json();
  if (!response.ok)
    throw new RequestError(
      data.detail || data.title || "İşlem tamamlanamadı",
      response.status,
    );
  return data as T;
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
