/**
 * TurnaroundIQ → FastAPI client
 *
 * Env:
 *   NEXT_PUBLIC_API_BASE=http://144.91.92.72:8080
 *   NEXT_PUBLIC_DEV_USER_ID=test_user   (dev only, until RevenueCat)
 */

export const API_BASE =
  (typeof process !== "undefined" &&
    process.env &&
    process.env.NEXT_PUBLIC_API_BASE) ||
  "http://144.91.92.72:8080";

export function getAppUserId() {
  if (typeof window === "undefined") return null;
  const stored = window.localStorage.getItem("tq_app_user_id");
  if (stored) return stored;
  const dev =
    (typeof process !== "undefined" &&
      process.env &&
      process.env.NEXT_PUBLIC_DEV_USER_ID) ||
    "dev_user";
  return dev;
}

export function setAppUserId(id) {
  if (typeof window !== "undefined" && id) {
    window.localStorage.setItem("tq_app_user_id", id);
  }
}

export class ApiError extends Error {
  constructor(status, body) {
    super((body && body.message) || (body && body.detail) || `HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function request(path, { method = "GET", body, token } = {}) {
  const headers = { Accept: "application/json" };
  const userId = token || getAppUserId();
  if (userId) headers.Authorization = `Bearer ${userId}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  let data = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { raw: text };
    }
  }

  if (!res.ok) {
    const detail =
      typeof data?.detail === "object" ? data.detail : { message: data?.detail || data?.message };
    throw new ApiError(res.status, detail || data);
  }
  return data;
}

export const api = {
  health: () => request("/health", { token: null }).catch(() =>
    fetch(`${API_BASE}/health`).then((r) => r.json())
  ),
  me: () => request("/me"),
  opportunities: (limit = 20) => request(`/opportunities?limit=${limit}`),
  earlyGoal: (limit = 20) => request(`/features/early-goal?limit=${limit}`),
  chaos: (limit = 20) => request(`/features/chaos?limit=${limit}`),
  patchPrefs: (prefs) => request("/me/prefs", { method: "PATCH", body: prefs }),
};
