/**
 * TurnaroundIQ API client. Every call carries
 * `Authorization: Bearer <RevenueCat appUserID>` — the same id RevenueCat
 * sends in webhooks, which is how the server knows who is Pro.
 */
export const API_BASE = import.meta.env.VITE_API_BASE || "https://api.turnaroundiq.co.uk";

let userId = null;
export function setUserId(id) {
  userId = id || null;
}
export function getUserId() {
  return userId;
}

export class ApiError extends Error {
  constructor(status, detail) {
    const msg =
      (detail && (detail.message || detail.detail || detail.code)) || `HTTP ${status}`;
    super(typeof msg === "string" ? msg : JSON.stringify(msg));
    this.status = status;
    this.detail = detail;
  }
  /** 401 (no user yet) or 402 (not subscribed) -> show the paywall */
  get needsPro() {
    return this.status === 401 || this.status === 402;
  }
}

async function request(path, { method = "GET", body } = {}) {
  const headers = { Accept: "application/json" };
  if (userId) headers.Authorization = `Bearer ${userId}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(API_BASE + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, { message: "Can't reach TurnaroundIQ — check your connection." });
  }
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { message: text };
  }
  if (!res.ok) {
    const detail = data && typeof data.detail === "object" ? data.detail : { message: data?.detail || data?.message };
    throw new ApiError(res.status, detail);
  }
  return data;
}

export const api = {
  authStart: (email) => request("/auth/start", { method: "POST", body: { email } }),
  authVerify: (email, code) => request("/auth/verify", { method: "POST", body: { email, code } }),
  authLogout: () => request("/auth/logout", { method: "POST" }),
  me: () => request("/me"),
  deleteMe: () => request("/me", { method: "DELETE" }),
  patchPrefs: (prefs) => request("/me/prefs", { method: "PATCH", body: prefs }),
  // next 24h only: odds (and exchange lay liquidity) exist for that window
  opportunities: (limit = 100) => request(`/opportunities?limit=${limit}&include_tracked=false&hours=24`),
  refreshOdds: () => request("/odds/refresh", { method: "POST" }),
  oddsRefreshStatus: () => request("/odds/refresh"),
  earlyGoal: (limit = 30) => request(`/features/early-goal?limit=${limit}`),
  chaos: (limit = 30) => request(`/features/chaos?limit=${limit}`),
  tracked: (status) => request(status ? `/tracked?status=${status}&limit=200` : "/tracked?limit=200"),
  track: (body) => request("/tracked", { method: "POST", body }),
  paper: () => request("/paper"),
  autoSettle: () => request("/paper/auto-settle", { method: "POST" }),
  modelRuns: () => request("/model/runs"),
};
