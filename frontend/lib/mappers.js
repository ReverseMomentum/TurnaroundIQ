/**
 * Map FastAPI JSON → shapes already used by OpportunityCard / EarlyGoal / Chaos.
 */

function splitMatch(match) {
  if (!match || typeof match !== "string") return { home: "", away: "" };
  const parts = match.split(/\s+vs\s+/i);
  if (parts.length >= 2) return { home: parts[0].trim(), away: parts[1].trim() };
  return { home: match, away: "" };
}

/** Opportunities engine row → OpportunityCard props */
export function mapOpportunity(row) {
  const fromMatch = splitMatch(row.match);
  const home = row.home_team || fromMatch.home;
  const away = row.away_team || fromMatch.away;
  const ftaPct = Number(row.fta_pct ?? 0);
  const conf = Number(row.confidence ?? 0);
  // confidence from model is often 0–1; UI used 0–100
  const confidence_score = conf <= 1 ? Math.round(conf * 100) : Math.round(conf);

  return {
    fixture_id: row.match_id || row.team || row.match,
    kickoff: row.kickoff || "",
    league: row.league || "",
    home_team: home,
    away_team: away,
    team: row.team || home,
    book_odds: row.back_odds,
    lay_odds: row.lay_odds,
    estimated_lay: !!row.estimated_lay,
    bookmaker: row.bookmaker || "",
    // UI "EV %" — live engine uses ev_percent (can be small / negative)
    ev: Number(row.ev_percent ?? row.ev_rating ?? 0),
    ev_rating: Number(row.ev_rating ?? 0),
    probability_turnaround: ftaPct / 100,
    fta_pct: ftaPct,
    confidence_score,
    combined_probability: ftaPct / 100,
    market_edge: Number(row.ev_percent ?? 0),
    stake: row.stake,
    lay_stake: row.lay_stake,
    liability: row.liability,
    qualifying_loss: row.qualifying_loss,
    commission: row.commission,
    _raw: row,
  };
}

/** Early goal match → EarlyGoalHunterRow */
export function mapEarlyGoal(row) {
  return {
    fixture_id: row.match_id || row.match,
    kickoff: row.kickoff || "",
    league: row.league || "",
    home_team: row.home_team,
    away_team: row.away_team,
    match: row.match,
    hunter_score: Number(row.hunter_score ?? 0),
    p_first_half_goal: Number(row.p_first_half_goal ?? 0),
    p_home_scores_first: Number(row.p_home_scores_first ?? 0),
    p_away_scores_first: Number(row.p_away_scores_first ?? 0),
    away_first_home_leak: Number(row.away_first_home_leak ?? 0),
    home_first_away_leak: Number(row.home_first_away_leak ?? 0),
    home: row.home || {},
    away: row.away || {},
    _raw: row,
  };
}

/** Chaos match → ChaosFixtureCard (pie from API.pie) */
export function mapChaos(row) {
  const components = row.components || row.chaos_components || {};
  const pie = row.pie || components;
  return {
    fixture_id: row.match_id || row.match,
    kickoff: row.kickoff || "",
    league: row.league || "",
    home_team: row.home_team,
    away_team: row.away_team,
    match: row.match,
    chaos_index: Number(row.chaos_index ?? 0),
    chaos_label: row.chaos_label || "medium",
    chaos_components: {
      o2_5: Number(components.o2_5 ?? 0),
      btts: Number(components.btts ?? 0),
      early_goal: Number(components.early_goal ?? 0),
      instability: Number(components.instability ?? 0),
    },
    pie: {
      o2_5: Number(pie.o2_5 ?? components.o2_5 ?? 0),
      btts: Number(pie.btts ?? components.btts ?? 0),
      early_goal: Number(pie.early_goal ?? components.early_goal ?? 0),
      instability: Number(pie.instability ?? components.instability ?? 0),
    },
    home: row.home || {},
    away: row.away || {},
    _raw: row,
  };
}

export function mapMe(data) {
  return {
    entitled: !!data.entitled,
    entitlement: data.entitlement || (data.entitled ? "pro" : "free"),
    status: data.status || (data.entitled ? "active" : "free"),
    expires_at: data.expires_at || null,
    product_id: data.product_id || null,
    environment: data.environment || null,
    prefs: data.prefs || {},
    app_user_id: data.app_user_id,
  };
}
