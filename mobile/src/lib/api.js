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

export const MIN_FTA = 1.8;
export const MIN_SCORE = 40;

export const api = {
  authStart: (email) => request("/auth/start", { method: "POST", body: { email } }),
  authVerify: (email, code) => request("/auth/verify", { method: "POST", body: { email, code } }),
  authLogout: () => request("/auth/logout", { method: "POST" }),
  me: () => request("/me"),
  deleteMe: () => request("/me", { method: "DELETE" }),
  patchPrefs: (prefs) => request("/me/prefs", { method: "PATCH", body: prefs }),
  // Next 24h only (odds and exchange lay liquidity exist for that window), and only
  // picks above a quality floor: FTA >= 1.8%, Hunter / Chaos >= 40/100.
  opportunities: (limit = 100) => request(`/opportunities?limit=${limit}&include_tracked=false&hours=24&min_fta=${MIN_FTA}`),
  refreshOdds: () => request("/odds/refresh", { method: "POST" }),
  oddsRefreshStatus: () => request("/odds/refresh"),
  oddsBookmakers: () => request("/odds/bookmakers"),
  earlyGoal: (limit = 50) => request(`/features/early-goal?limit=${limit}&hours=24&min_score=${MIN_SCORE}`),
  chaos: (limit = 50) => request(`/features/chaos?limit=${limit}&hours=24&min_score=${MIN_SCORE}`),
  tracked: (status) => request(status ? `/tracked?status=${status}&limit=200` : "/tracked?limit=200"),
  track: (body) => request("/tracked", { method: "POST", body }),
  editTracked: (id, body) => request(`/tracked/${id}`, { method: "PUT", body }),
  deleteTracked: (id) => request(`/tracked/${id}`, { method: "DELETE" }),
  live: () => request("/live"),
  liveTurnaround: ({ team, opponent, league, isHome, minute, teamGoals, oppGoals }) =>
    request(`/live/turnaround?team=${encodeURIComponent(team)}&opponent=${encodeURIComponent(opponent)}` +
      `&league=${encodeURIComponent(league || "")}&is_home=${isHome ? "true" : "false"}` +
      `&minute=${minute}&team_goals=${teamGoals}&opp_goals=${oppGoals}`),
  settleTracked: (id, result, actualProfit) =>
    request(`/tracked/${id}`, { method: "PATCH", body: actualProfit == null ? { result } : { result, actual_profit: actualProfit } }),
  paper: () => request("/paper"),
  autoSettle: () => request("/paper/auto-settle", { method: "POST" }),
  modelRuns: () => request("/model/runs"),
  // The Stables (horse racing extra places)
  stablesRaces: (date, refresh = false) => {
    const qs = [date && `date=${encodeURIComponent(date)}`, refresh && "refresh=true"].filter(Boolean).join("&");
    return request("/stables/races" + (qs ? "?" + qs : ""));
  },
  stablesPrice: (race) => request("/stables/price", { method: "POST", body: race }),
  stablesTrack: (bet) => request("/stables/track", { method: "POST", body: bet }),
  stablesTracker: (paper) => request("/stables/tracker" + (paper == null ? "" : `?paper=${paper}`)),
  stablesAddOffers: (offer) => request("/stables/offers", { method: "POST", body: offer }),
  stablesPasteOffers: (date, text) => request("/stables/offers/paste", { method: "POST", body: { date, text } }),
  stablesDeleteOffer: (raceId, bookmaker) =>
    request(`/stables/offers?race_id=${raceId}&bookmaker=${encodeURIComponent(bookmaker)}`, { method: "DELETE" }),
};
