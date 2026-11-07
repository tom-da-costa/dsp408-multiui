export interface Me {
  client_id: string;
  name: string;
}

export class LoginError extends Error {
  constructor(
    message: string,
    readonly code: string,
  ) {
    super(message);
  }
}

export async function currentSession(): Promise<Me | null> {
  const response = await fetch("/api/session", { credentials: "same-origin" });
  if (!response.ok) return null;
  return (await response.json()) as Me;
}

export async function login(pin: string, name: string): Promise<Me> {
  const response = await fetch("/api/login", {
    method: "POST",
    credentials: "same-origin",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ pin, name: name || null }),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { error?: string; message?: string };
    throw new LoginError(body.message ?? "login failed", body.error ?? "error");
  }
  return (await response.json()) as Me;
}

export async function logout(): Promise<void> {
  await fetch("/api/logout", { method: "POST", credentials: "same-origin" });
}
