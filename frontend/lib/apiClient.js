/**
 * TurnaroundIQ → FastAPI client
 */

const env = (typeof process !== "undefined" && process.env) || {};

// Expo uses EXPO_PUBLIC_*, Next.js NEXT_PUBLIC_*.
export const API_BASE =
  env.EXPO_PUBLIC_API_BASE || env.NEXT_PUBLIC_API_BASE || "https://api.turnaroundiq.co.uk";

/**
 * The RevenueCat app user id. React Native: set by initPurchases()
 * (lib/revenuecat.js) from Purchases.getAppUserID(); RevenueCat itself
 * persists it on the device, so it is simply re-read on each launch.
 * No shared fallback: without an id the API answers 401 -> paywall.
 * EXPO_PUBLIC_DEV_USER_ID / NEXT_PUBLIC_DEV_USER_ID: local development only.
 */
let currentUserId = null;

function webStorage() {
  try {
    return typeof window !== "undefined" && window.localStorage ? window.localStorage : null;
  } catch {
    return null; // React Native / private mode
  }
}

export function getAppUserId() {
  if (currentUserId) return currentUserId;
  const stored = webStorage()?.getItem("tq_app_user_id");
  if (stored) return stored;
  return env.EXPO_PUBLIC_DEV_USER_ID || env.NEXT_PUBLIC_DEV_USER_ID || null;
}

export function setAppUserId(id) {
  currentUserId = id || null;
  const storage = webStorage();
  if (storage && id) storage.setItem("tq_app_user_id", id);
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
      typeof data?.detail === "object"
        ? data.detail
        : { message: data?.detail || data?.message };
    throw new ApiError(res.status, detail || data);
  }
  return data;
}

export const api = {
  health: () =>
    fetch(`${API_BASE}/health`).then((r) => r.json()),
  me: () => request("/me"),
  opportunities: (limit = 20) =>
    request(`/opportunities?limit=${limit}&include_tracked=true`),
  earlyGoal: (limit = 20) => request(`/features/early-goal?limit=${limit}`),
  chaos: (limit = 20) => request(`/features/chaos?limit=${limit}`),
  patchPrefs: (prefs) => request("/me/prefs", { method: "PATCH", body: prefs }),
  trackedList: (status) =>
    request(status ? `/tracked?status=${status}` : "/tracked"),
  trackedCreate: (body) => request("/tracked", { method: "POST", body }),
  trackedSettle: (id, body) =>
    request(`/tracked/${id}`, { method: "PATCH", body }),
};
