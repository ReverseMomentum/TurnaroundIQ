import React, { useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import {
  Bell,
  ChevronRight,
  Home,
  Rocket,
  RadioTower,
  Wallet,
  Menu,
  X,
  Calculator,
  Settings,
  Eye,
  Bookmark,
  ArrowUpRight,
  ArrowDownRight,
  Info,
  Circle,
  Zap,
  RotateCcw,
  User,
  CreditCard,
  Shield,
  LogOut,
  Lock,
  Crosshair,
  Flame,
  FlaskConical,
} from "lucide-react";

/*
  ICON LIBRARY NOTE FOR PRODUCTION:
  This preview uses lucide-react (the only icon set available in this
  sandbox). The real Next.js build should use @tabler/icons-react
  (NOT @tabler/icons-react-native -- that package is for React Native
  mobile apps and won't work in a Next.js web project).

  Confirmed mapping to swap in:
    Home            -> IconHome
    Opportunities   -> IconRocket              (stand-in here: Rocket)
    Live            -> IconBuildingBroadcastTower  (stand-in here: RadioTower)
    Bets            -> IconWallet
    More/Menu       -> IconMenu2
    Calculator      -> IconCalculator
    Settings        -> IconSettings
    Notifications   -> IconBell
*/

// ---- Brand tokens (locked palette) ----
const c = {
  bg: "#060B18",
  card: "#0B1224",
  cardAlt: "#0B1020",
  border: "#18233D",
  green: "#36E98F",
  greenDark: "#0B3D26",
  cyan: "#4BC7FF",
  blue: "#4B6FFF",
  orange: "#FF9C42",
  red: "#FF5252",
  text: "#F5F7FA",
  textSecondary: "#A0A8C0",
};

const LOGO_SRC =
  "data:image/png;base64,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";

// ============================================================
// SHARED CALCULATIONS -- ported 1:1 from calculations.py.
// One copy, used by the Opportunity modal, Calculator, and the
// Dashboard's Live P/L figure, so they can never drift apart.
// ============================================================
function calcLayStake(backOdds, layOdds, stake, commission) {
  const denom = layOdds - commission / 100;
  if (denom <= 0) return 0;
  return (backOdds * stake) / denom;
}
function calcLiability(layOdds, layStake) {
  return (layOdds - 1) * layStake;
}
function calcQualifyingLoss(backOdds, layOdds, stake, layStake) {
  const bookmakerProfit = stake * (backOdds - 1);
  const liability = (layOdds - 1) * layStake;
  return bookmakerProfit - liability;
}
function calcFtaProfit(stake, backOdds, layStake, commission) {
  const bookmakerReturn = stake * backOdds;
  const layWin = layStake * (1 - commission / 100);
  return bookmakerReturn + layWin - stake;
}
function calcExpectedProfit(ftaProfit, qualifyingLoss, ftaPct) {
  const p = ftaPct / 100;
  return ftaProfit * p - Math.abs(qualifyingLoss) * (1 - p);
}
function calcEvPercent(expectedProfit, qualifyingLoss) {
  const risk = Math.abs(qualifyingLoss);
  if (risk <= 0) return 0;
  return (expectedProfit / risk) * 100;
}
// Free bet, stake NOT returned: only the winnings portion needs hedging.
function calcLayStakeSNR(backOdds, layOdds, freeBetStake, commission) {
  const denom = layOdds - commission / 100;
  if (denom <= 0) return 0;
  return ((backOdds - 1) * freeBetStake) / denom;
}
// Free bet, stake returned: behaves like a normal qualifying bet.
function calcLayStakeSR(backOdds, layOdds, freeBetStake, commission) {
  return calcLayStake(backOdds, layOdds, freeBetStake, commission);
}

// ============================================================
// SHARED DATA -- single source of truth. Previously duplicated
// across 5 separate files; consolidating here was the main point
// of building this connected shell.
// ============================================================
export const opportunities = [
  {
    fixture_id: 1, kickoff: "17:00", league: "Premier League",
    home_team: "Liverpool", away_team: "Brighton",
    book_odds: 2.70, lay_odds: 2.82, commission: 2.5,
    probability_qualification: 0.242, probability_turnaround: 0.087,
    combined_probability: 0.021, confidence_score: 88, market_edge: 2.4,
    ev: 102.4, tq_score: 92,
  },
  {
    fixture_id: 2, kickoff: "17:00", league: "Ekstraklasa",
    home_team: "Gornik Zabrze", away_team: "Pogon Szczecin",
    book_odds: 2.70, lay_odds: 2.82, commission: 2.0,
    probability_qualification: 0.251, probability_turnaround: 0.091,
    combined_probability: 0.023, confidence_score: 86, market_edge: 2.2,
    ev: 102.4, tq_score: 90,
  },
  {
    fixture_id: 3, kickoff: "19:30", league: "Ekstraklasa",
    home_team: "Jagiellonia Bialystok", away_team: "Cracovia",
    book_odds: 4.60, lay_odds: 5.20, commission: 2.0,
    probability_qualification: 0.198, probability_turnaround: 0.134,
    combined_probability: 0.027, confidence_score: 64, market_edge: 1.6,
    ev: 100.3, tq_score: 78,
  },
  {
    fixture_id: 4, kickoff: "19:45", league: "Ligue 1",
    home_team: "Lille", away_team: "Lens",
    book_odds: 1.95, lay_odds: 2.02, commission: 2.0,
    probability_qualification: 0.221, probability_turnaround: 0.089,
    combined_probability: 0.020, confidence_score: 61, market_edge: 1.2,
    ev: 100.3, tq_score: 74,
  },
  {
    fixture_id: 5, kickoff: "20:00", league: "Bundesliga",
    home_team: "Union Berlin", away_team: "Werder Bremen",
    book_odds: 2.35, lay_odds: 2.48, commission: 2.0,
    probability_qualification: 0.205, probability_turnaround: 0.095,
    combined_probability: 0.019, confidence_score: 58, market_edge: 1.0,
    ev: 98.7, tq_score: 70,
  },
];

// Early Goal Hunter and Chaos Factor are separate scoring engines
// (early_goal_hunter.py, chaos_index.py) from the FTA opportunities
// engine -- this pool intentionally does NOT reuse the `opportunities`
// fixtures above. These are matches that may not qualify as FTA
// opportunities at all, but score well on one of these two other
// signals.
export const otherFixtures = [
  {
    fixture_id: 301, league: "La Liga", kickoff: "20:00",
    home_team: "Villarreal", away_team: "Real Betis",
    // early_goal_hunter.py fields
    p_first_half_goal: 0.71, p_home_scores_first: 0.58, p_away_scores_first: 0.42,
    hunter_score: 88.4,
    // chaos_index.py fields
    chaos_index: 62.0, chaos_label: "medium",
    chaos_components: { o2_5: 58, btts: 64, early_goal: 71, instability: 48 },
  },
  {
    fixture_id: 302, league: "Bundesliga", kickoff: "17:30",
    home_team: "Bayern Munich", away_team: "Borussia Dortmund",
    p_first_half_goal: 0.79, p_home_scores_first: 0.66, p_away_scores_first: 0.34,
    hunter_score: 91.2,
    chaos_index: 74.5, chaos_label: "high",
    chaos_components: { o2_5: 82, btts: 70, early_goal: 79, instability: 55 },
  },
  {
    fixture_id: 303, league: "Serie A", kickoff: "19:45",
    home_team: "Napoli", away_team: "Inter Milan",
    p_first_half_goal: 0.52, p_home_scores_first: 0.51, p_away_scores_first: 0.49,
    hunter_score: 61.0,
    chaos_index: 44.0, chaos_label: "medium",
    chaos_components: { o2_5: 46, btts: 52, early_goal: 52, instability: 38 },
  },
  {
    fixture_id: 304, league: "Eredivisie", kickoff: "18:00",
    home_team: "Ajax", away_team: "PSV Eindhoven",
    p_first_half_goal: 0.68, p_home_scores_first: 0.47, p_away_scores_first: 0.53,
    hunter_score: 79.6,
    chaos_index: 69.0, chaos_label: "high",
    chaos_components: { o2_5: 74, btts: 68, early_goal: 68, instability: 52 },
  },
  {
    fixture_id: 305, league: "Primera Division", kickoff: "23:30",
    home_team: "Boca Juniors", away_team: "River Plate",
    p_first_half_goal: 0.38, p_home_scores_first: 0.55, p_away_scores_first: 0.45,
    hunter_score: 42.0,
    chaos_index: 81.0, chaos_label: "high",
    chaos_components: { o2_5: 34, btts: 40, early_goal: 38, instability: 96 },
  },
];

export const liveMatches = [
  {
    fixture_id: 101, league: "Premier League",
    home_team: "Liverpool", away_team: "Brighton",
    home_score: 2, away_score: 0, minute: "67'", status: "live",
    twoUpActive: true, earlyPayoutTriggered: true,
    backOdds2up: 1.74, layOdds: 1.95, commission: 2,
    potentialProfit: 84.0,
    timeline: [
      { minute: "12'", team: "Liverpool", score: "1 - 0" },
      { minute: "34'", team: "Liverpool", score: "2 - 0", tag: "2UP" },
    ],
  },
  {
    fixture_id: 102, league: "Bundesliga",
    home_team: "Leverkusen", away_team: "Mainz",
    home_score: 2, away_score: 2, minute: "84'", status: "live",
    twoUpActive: true, earlyPayoutTriggered: true,
    backOdds2up: 1.68, layOdds: 1.90, commission: 2,
    potentialProfit: 91.5,
    timeline: [
      { minute: "18'", team: "Leverkusen", score: "1 - 0" },
      { minute: "29'", team: "Leverkusen", score: "2 - 0", tag: "2UP" },
      { minute: "61'", team: "Mainz", score: "2 - 1" },
      { minute: "80'", team: "Mainz", score: "2 - 2" },
    ],
  },
  {
    fixture_id: 103, league: "Premier League",
    home_team: "Arsenal", away_team: "Fulham",
    home_score: 2, away_score: 2, minute: "FT", status: "finished",
    finishedMinutesAgo: 3, twoUpActive: true, earlyPayoutTriggered: true,
    backOdds2up: 1.62, layOdds: 1.85, commission: 2,
    potentialProfit: 76.2,
    timeline: [
      { minute: "22'", team: "Arsenal", score: "1 - 0" },
      { minute: "40'", team: "Arsenal", score: "2 - 0", tag: "2UP" },
      { minute: "70'", team: "Fulham", score: "2 - 1" },
      { minute: "89'", team: "Fulham", score: "2 - 2" },
    ],
  },
  {
    // Past the 5-minute grace window -- proves the visibility filter.
    // Won't render in the Live tab; it only exists in My Bets now.
    fixture_id: 104, league: "Serie A",
    home_team: "Roma", away_team: "Lazio",
    home_score: 2, away_score: 3, minute: "FT", status: "finished",
    finishedMinutesAgo: 12, twoUpActive: true, earlyPayoutTriggered: true,
    backOdds2up: 1.90, layOdds: 2.10, commission: 2,
    potentialProfit: 68.4,
    timeline: [],
  },
];

export const upcomingMatches = [
  {
    fixture_id: 201, league: "Ligue 1",
    home_team: "PSG", away_team: "Marseille",
    kickoffIn: "2h 18m", layOdds: 2.1,
  },
];

// Single unified bet ledger. Open bets carry the live odds/score needed
// for the Dashboard's Live P/L figure; settled bets carry the outcome.
export const bets = [
  {
    id: "b1", match: "Liverpool vs Brighton", league: "Premier League",
    stake: 100, expected_profit: 12.4, actual_profit: null,
    status: "Open", result: null, opened: "Today, 17:00",
    backOdds: 2.70, layOdds: 2.82, commission: 2,
    homeScore: 2, awayScore: 0, earlyPayoutTriggered: true,
  },
  {
    id: "b2", match: "Leverkusen vs Mainz", league: "Bundesliga",
    stake: 100, expected_profit: 18.9, actual_profit: null,
    status: "Open", result: null, opened: "Today, 15:30",
    backOdds: 1.68, layOdds: 1.90, commission: 2,
    homeScore: 2, awayScore: 2, earlyPayoutTriggered: true,
  },
  {
    id: "b3", match: "Arsenal vs Fulham", league: "Premier League",
    stake: 100, expected_profit: 14.1, actual_profit: 76.2,
    status: "Settled", result: "FTA win",
    opened: "Today, 12:30", settled: "Today, just now",
  },
  {
    id: "b4", match: "Roma vs Lazio", league: "Serie A",
    stake: 100, expected_profit: 9.8, actual_profit: 68.4,
    status: "Settled", result: "FTA win",
    opened: "Today, 11:00", settled: "Today, 12 min ago",
  },
  {
    id: "b5", match: "Sevilla vs Betis", league: "La Liga",
    stake: 100, expected_profit: 11.2, actual_profit: -3.4,
    status: "Settled", result: "Book win",
    opened: "Yesterday, 20:00", settled: "Yesterday",
  },
];

// Deliberately the same underlying events as opportunities/liveMatches/
// bets above, surfaced as notifications rather than a disconnected feed.
const ALERT_TYPES = {
  opportunity: { icon: Rocket, tone: c.green, label: "Opportunity found" },
  trigger: { icon: Zap, tone: c.orange, label: "Live trigger" },
  settled: { icon: Wallet, tone: c.green, label: "Bet settled" },
  system: { icon: Info, tone: c.textSecondary, label: "System" },
};

const INITIAL_ALERTS = [
  { id: "a1", type: "opportunity", title: "New high EV opportunity", detail: "Liverpool vs Brighton — 102.4% EV", time: "2 min ago", unread: true },
  { id: "a2", type: "trigger", title: "2UP triggered", detail: "Leverkusen vs Mainz — lead achieved, pending result", time: "18 min ago", unread: true },
  { id: "a3", type: "settled", title: "Bet settled — FTA win", detail: "Arsenal vs Fulham — profit +£76.20", time: "3 min ago", unread: true },
  { id: "a4", type: "settled", title: "Bet settled — FTA win", detail: "Roma vs Lazio — profit +£68.40", time: "12 min ago", unread: false },
  { id: "a5", type: "system", title: "Model updated", detail: "FTA prediction model upgraded to V4.0", time: "1 hour ago", unread: false },
];

const ALERT_PREFS = [
  "Opportunity found", "Fixture starting", "Live trigger", "Goal event",
  "Exchange entry", "Market drift", "Bet settled", "System alert",
];

// ============================================================
// SHARED HELPERS
// ============================================================
function confidenceLabel(score) {
  if (score >= 80) return { label: "High", tone: c.green };
  if (score >= 60) return { label: "Medium", tone: c.orange };
  return { label: "Low", tone: c.textSecondary };
}

// FTA status traffic light:
//   red    -- laid team currently winning (real risk still live)
//   yellow -- 2UP triggered, not winning, still in play (reusing
//             Warning Orange since the palette has no true yellow)
//   green  -- full-time reached and they failed to win (settled)
function getFtaStatus(m) {
  const notWinning = m.home_score <= m.away_score;
  if (!notWinning) return { tone: c.red, label: "Team winning" };
  if (m.status === "finished") return { tone: c.green, label: "FTA confirmed" };
  if (m.earlyPayoutTriggered) return { tone: c.orange, label: "2UP triggered – pending" };
  return { tone: c.textSecondary, label: "Awaiting qualifying lead" };
}

// Matches stay visible in Live Monitor's "Live" tab for 5 minutes after
// full-time, then only exist in My Bets.
function isVisibleLive(m) {
  if (m.status === "live") return true;
  if (m.status === "finished") return (m.finishedMinutesAgo ?? Infinity) < 5;
  return false;
}

function resultTone(result) {
  if (result === "FTA win") return c.green;
  if (result === "Book win") return c.red;
  return c.textSecondary;
}

// "What would this bet settle as if the match ended right now" --
// still winning implies the qualifying-loss branch; level or behind
// implies the FTA-payout branch. Powers the Dashboard's Live P/L.
function liveImpliedPL(b) {
  const layStake = calcLayStake(b.backOdds, b.layOdds, b.stake, b.commission);
  const stillWinning = b.homeScore > b.awayScore;
  return stillWinning
    ? calcQualifyingLoss(b.backOdds, b.layOdds, b.stake, layStake)
    : calcFtaProfit(b.stake, b.backOdds, layStake, b.commission);
}

const bestEv = Math.max(...opportunities.map((o) => o.ev));
const avgEv = opportunities.reduce((sum, o) => sum + o.ev, 0) / opportunities.length;

const leagueAverages = {};
opportunities.forEach((o) => {
  if (!leagueAverages[o.league]) leagueAverages[o.league] = [];
  leagueAverages[o.league].push(o.ev);
});
const topLeague = Object.entries(leagueAverages)
  .map(([league, evs]) => ({ league, avg: evs.reduce((a, b) => a + b, 0) / evs.length }))
  .sort((a, b) => b.avg - a.avg)[0].league;
const highestEvOpportunity = opportunities.reduce((best, o) => (o.ev > best.ev ? o : best));
const avgMarketEdge = opportunities.reduce((sum, o) => sum + o.market_edge, 0) / opportunities.length;

const equityData = [
  { v: 2100 }, { v: 2180 }, { v: 2150 }, { v: 2260 }, { v: 2340 },
  { v: 2300 }, { v: 2410 }, { v: 2388 }, { v: 2530 },
];

// ============================================================
// SHARED LAYOUT -- one header, one page shell, one bottom nav.
// This is the part that makes navigation real: BottomNav now
// calls onNavigate instead of doing nothing.
// ============================================================
function PageHeader({ onNavigate, unreadCount }) {
  return (
    <div className="flex items-center justify-between mb-6">
      <button onClick={() => onNavigate("dashboard")} className="flex items-center gap-2">
        <img src={LOGO_SRC} alt="TurnaroundIQ logo" className="h-6 w-auto" />
        <span className="text-base font-medium">
          <span style={{ color: c.text }}>Turnaround</span>
          <span style={{ color: c.green }}>IQ</span>
        </span>
      </button>
      <button aria-label="Notifications" onClick={() => onNavigate("alerts")} className="relative">
        <Bell size={20} style={{ color: c.textSecondary }} />
        {unreadCount > 0 && (
          <span
            style={{ background: c.red, border: "1.5px solid " + c.bg }}
            className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full"
          />
        )}
      </button>
    </div>
  );
}

function BottomNav({ activeTab, onNavigate, unreadCount }) {
  const [open, setOpen] = useState(false);

  const navItems = [
    { key: "dashboard", icon: Home },
    { key: "opportunities", icon: Rocket },
    { key: "live", icon: RadioTower },
    { key: "bets", icon: Wallet },
  ];

  const flyoutItems = [
    { key: "model-testing", icon: FlaskConical, label: "Model Testing (dev)", tone: c.cyan },
    { key: "early-goal-hunter", icon: Crosshair, label: "Early Goal Hunter", tone: c.orange },
    { key: "chaos-factor", icon: Flame, label: "Chaos Factor", tone: c.red },
    { key: "calculator", icon: Calculator, label: "Calculator", tone: c.cyan },
    { key: "alerts", icon: Bell, label: "Alerts", tone: c.orange, badge: unreadCount },
    { key: "settings", icon: Settings, label: "Settings", tone: c.textSecondary },
  ];

  const go = (key) => {
    setOpen(false);
    onNavigate(key);
  };

  return (
    <div className="fixed bottom-0 left-0 right-0 flex justify-center pb-4 px-4">
      <div className="w-full max-w-[420px]">
        {open && (
          <div
            style={{ background: c.cardAlt, border: "1px solid " + c.border }}
            className="rounded-2xl p-2 mb-2"
          >
            {flyoutItems.map(({ key, icon: Icon, label, tone, badge }) => (
              <button
                key={key}
                onClick={() => go(key)}
                className="w-full flex items-center gap-3 px-3 py-3 text-left"
              >
                <Icon size={20} style={{ color: tone }} />
                <span style={{ color: c.text }} className="text-sm">{label}</span>
                {!!badge && (
                  <span
                    style={{ background: c.red, color: c.text }}
                    className="ml-auto text-xs font-medium px-2 py-0.5 rounded-full"
                  >
                    {badge}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}

        <div
          style={{ background: c.card, border: "1px solid " + c.border }}
          className="rounded-2xl flex items-center justify-between px-7 py-4"
        >
          {navItems.map(({ key, icon: Icon }) => (
            <button key={key} aria-label={key} onClick={() => go(key)}>
              <Icon size={22} style={{ color: !open && key === activeTab ? c.green : c.textSecondary }} />
            </button>
          ))}
          <button
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen(!open)}
            className="relative"
          >
            {open ? (
              <X size={22} style={{ color: c.green }} />
            ) : (
              <>
                <Menu size={22} style={{ color: !open && activeTab === "menu" ? c.green : c.textSecondary }} />
                {unreadCount > 0 && (
                  <span
                    style={{ background: c.red, border: "1.5px solid " + c.card }}
                    className="absolute -top-0.5 -right-1 w-2 h-2 rounded-full"
                  />
                )}
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function PageShell({ children, activeTab, onNavigate, unreadCount }) {
  return (
    <div style={{ background: c.bg, minHeight: "100vh" }} className="pb-32">
      <div className="max-w-[420px] mx-auto px-4 pt-6">{children}</div>
      <BottomNav activeTab={activeTab} onNavigate={onNavigate} unreadCount={unreadCount} />
    </div>
  );
}

// ============================================================
// SHARED SMALL COMPONENTS
// ============================================================
function KpiCard({ label, value, tone }) {
  return (
    <div style={{ background: c.card, border: "1px solid " + c.border }} className="flex-shrink-0 rounded-xl px-4 py-3 min-w-[110px]">
      <p style={{ color: c.textSecondary }} className="text-xs mb-1">{label}</p>
      <p style={{ color: tone }} className="text-lg font-medium">{value}</p>
    </div>
  );
}

function OpportunityCard({ o, onClick }) {
  const conf = confidenceLabel(o.confidence_score);
  return (
    <button
      onClick={() => onClick(o)}
      style={{ background: c.card, border: "1px solid " + c.border, textAlign: "left" }}
      className="rounded-xl p-4 flex flex-col gap-3 w-[260px] flex-shrink-0"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p style={{ color: c.textSecondary }} className="text-xs mb-1 truncate">{o.kickoff} · {o.league}</p>
          <p style={{ color: c.text }} className="text-sm font-medium leading-snug truncate" title={o.home_team}>{o.home_team}</p>
          <p style={{ color: c.textSecondary }} className="text-sm leading-snug truncate" title={o.away_team}>vs {o.away_team}</p>
        </div>
        <div className="text-right flex-shrink-0">
          <p style={{ color: c.green }} className="text-lg font-medium">{o.ev}%</p>
          <p style={{ color: c.textSecondary }} className="text-xs">EV</p>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div><p style={{ color: c.textSecondary }} className="text-xs">Book</p><p style={{ color: c.text }} className="text-sm font-medium">{o.book_odds}</p></div>
        <div><p style={{ color: c.textSecondary }} className="text-xs">Lay</p><p style={{ color: c.cyan }} className="text-sm font-medium">{o.lay_odds}</p></div>
        <div><p style={{ color: c.textSecondary }} className="text-xs">Combined</p><p style={{ color: c.text }} className="text-sm font-medium">{(o.combined_probability * 100).toFixed(1)}%</p></div>
      </div>
      <div className="flex items-center justify-between">
        <span style={{ color: conf.tone }} className="text-xs font-medium">{conf.label} confidence</span>
        <span style={{ color: c.cyan }} className="flex items-center gap-1 text-xs font-medium">Analysis <ChevronRight size={14} /></span>
      </div>
    </button>
  );
}

function OpportunityRow({ o, onClick }) {
  const conf = confidenceLabel(o.confidence_score);
  return (
    <button
      onClick={() => onClick(o)}
      style={{ background: c.card, border: "1px solid " + c.border, textAlign: "left" }}
      className="rounded-xl p-4 flex flex-col gap-3 w-full"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p style={{ color: c.textSecondary }} className="text-xs mb-1 truncate">{o.kickoff} · {o.league}</p>
          <p style={{ color: c.text }} className="text-sm font-medium leading-snug truncate" title={o.home_team}>{o.home_team}</p>
          <p style={{ color: c.textSecondary }} className="text-sm leading-snug truncate" title={o.away_team}>vs {o.away_team}</p>
        </div>
        <div className="text-right flex-shrink-0">
          <p style={{ color: c.green }} className="text-lg font-medium">{o.ev}%</p>
          <p style={{ color: c.textSecondary }} className="text-xs">EV</p>
        </div>
      </div>
      <div className="grid grid-cols-4 gap-2 text-center">
        <div><p style={{ color: c.textSecondary }} className="text-xs">Book</p><p style={{ color: c.text }} className="text-sm font-medium">{o.book_odds}</p></div>
        <div><p style={{ color: c.textSecondary }} className="text-xs">Lay</p><p style={{ color: c.cyan }} className="text-sm font-medium">{o.lay_odds}</p></div>
        <div><p style={{ color: c.textSecondary }} className="text-xs">Combined</p><p style={{ color: c.text }} className="text-sm font-medium">{(o.combined_probability * 100).toFixed(1)}%</p></div>
        <div><p style={{ color: c.textSecondary }} className="text-xs">TQ score</p><p style={{ color: c.text }} className="text-sm font-medium">{o.tq_score}</p></div>
      </div>
      <div className="flex items-center justify-between">
        <span style={{ color: conf.tone }} className="text-xs font-medium">{conf.label} confidence</span>
        <span style={{ color: c.cyan }} className="flex items-center gap-1 text-xs font-medium">Analysis <ChevronRight size={14} /></span>
      </div>
    </button>
  );
}

function OpportunityDetailModal({ opportunity, onClose }) {
  const [stake, setStake] = useState("100");
  const [backOdds, setBackOdds] = useState(opportunity ? String(opportunity.book_odds) : "");
  const [layOdds, setLayOdds] = useState(opportunity ? String(opportunity.lay_odds) : "");
  const [commission, setCommission] = useState(opportunity ? String(opportunity.commission) : "");
  const [lastId, setLastId] = useState(opportunity ? opportunity.fixture_id : null);

  if (opportunity && opportunity.fixture_id !== lastId) {
    setLastId(opportunity.fixture_id);
    setBackOdds(String(opportunity.book_odds));
    setLayOdds(String(opportunity.lay_odds));
    setCommission(String(opportunity.commission));
    setStake("100");
  }

  if (!opportunity) return null;
  const o = opportunity;
  const conf = confidenceLabel(o.confidence_score);

  const stakeNum = parseFloat(stake) || 0;
  const backOddsNum = parseFloat(backOdds) || 0;
  const layOddsNum = parseFloat(layOdds) || 0;
  const commissionNum = parseFloat(commission) || 0;

  const layStake = calcLayStake(backOddsNum, layOddsNum, stakeNum, commissionNum);
  const qualifyingLoss = calcQualifyingLoss(backOddsNum, layOddsNum, stakeNum, layStake);
  const ftaProfit = calcFtaProfit(stakeNum, backOddsNum, layStake, commissionNum);

  return (
    <div style={{ background: "rgba(0,0,0,0.6)", cursor: "pointer" }} className="fixed inset-0 z-50 flex items-end justify-center" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: c.bg, border: "1px solid " + c.border, cursor: "default" }} className="w-full max-w-[420px] max-h-[80vh] overflow-y-auto rounded-t-2xl p-5">
        <div className="flex justify-center mb-3" onClick={onClose} style={{ cursor: "pointer" }}>
          <div style={{ background: c.border }} className="w-10 h-1 rounded-full" />
        </div>
        <div className="flex justify-end mb-1">
          <button aria-label="Close" onClick={onClose} style={{ background: c.card, border: "1px solid " + c.border }} className="w-8 h-8 rounded-full flex items-center justify-center">
            <X size={16} style={{ color: c.textSecondary }} />
          </button>
        </div>

        <div className="flex items-center justify-between mb-4">
          <span style={{ color: c.textSecondary }} className="text-sm">{o.kickoff}</span>
          <span style={{ color: c.textSecondary }} className="text-sm">{o.league}</span>
        </div>

        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2 min-w-0">
            <span style={{ color: c.text }} className="text-sm font-medium truncate">{o.home_team}</span>
            <span style={{ color: c.textSecondary }} className="text-sm">vs</span>
            <span style={{ color: c.text }} className="text-sm font-medium truncate">{o.away_team}</span>
          </div>
          <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl px-3 py-2 text-center flex-shrink-0 ml-2">
            <p style={{ color: c.green }} className="text-lg font-medium leading-none">{o.ev}%</p>
            <p style={{ color: c.textSecondary }} className="text-xs mt-1">EV</p>
          </div>
        </div>

        <div style={{ borderTop: "1px solid " + c.border }} className="pt-4 mb-4 flex items-center justify-between">
          <span style={{ color: conf.tone }} className="text-sm font-medium">{conf.label} confidence</span>
          <div className="text-right">
            <p style={{ color: c.textSecondary }} className="text-xs">Model edge</p>
            <p style={{ color: c.green }} className="text-sm font-medium">+{o.market_edge}%</p>
          </div>
        </div>

        <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide mb-2">Model probabilities</p>
        <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-3 grid grid-cols-3 gap-2 text-center mb-4">
          <div><p style={{ color: c.textSecondary }} className="text-xs mb-1">2+ goal lead</p><p style={{ color: c.text }} className="text-base font-medium">{(o.probability_qualification * 100).toFixed(1)}%</p></div>
          <div><p style={{ color: c.textSecondary }} className="text-xs mb-1">Lead then fail</p><p style={{ color: c.text }} className="text-base font-medium">{(o.probability_turnaround * 100).toFixed(1)}%</p></div>
          <div><p style={{ color: c.textSecondary }} className="text-xs mb-1">Combined</p><p style={{ color: c.text }} className="text-base font-medium">{(o.combined_probability * 100).toFixed(1)}%</p></div>
        </div>

        <div className="flex items-center justify-between mb-2">
          <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide">Market odds</p>
          <span style={{ color: c.textSecondary }} className="text-xs italic">editable</span>
        </div>
        <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-3 grid grid-cols-3 gap-2 text-center mb-4">
          <div>
            <p style={{ color: c.textSecondary }} className="text-xs mb-1">Back (bookie)</p>
            <input type="number" step="0.01" value={backOdds} placeholder="0" onChange={(e) => setBackOdds(e.target.value)} style={{ background: "transparent", color: c.green, width: "100%" }} className="text-base font-medium text-center" />
          </div>
          <div>
            <p style={{ color: c.textSecondary }} className="text-xs mb-1">Lay (exchange)</p>
            <input type="number" step="0.01" value={layOdds} placeholder="0" onChange={(e) => setLayOdds(e.target.value)} style={{ background: "transparent", color: c.cyan, width: "100%" }} className="text-base font-medium text-center" />
          </div>
          <div>
            <p style={{ color: c.textSecondary }} className="text-xs mb-1">Commission %</p>
            <input type="number" step="0.1" value={commission} placeholder="0" onChange={(e) => setCommission(e.target.value)} style={{ background: "transparent", color: c.text, width: "100%" }} className="text-base font-medium text-center" />
          </div>
        </div>

        <div style={{ background: c.cardAlt, border: "1px solid " + c.border }} className="rounded-xl p-3 grid grid-cols-2 gap-2 text-center mb-4">
          <div><p style={{ color: c.textSecondary }} className="text-xs mb-1">Lay stake needed</p><p style={{ color: c.cyan }} className="text-base font-medium">£{layStake.toFixed(2)}</p></div>
          <div><p style={{ color: c.textSecondary }} className="text-xs mb-1">Liability</p><p style={{ color: c.orange }} className="text-base font-medium">£{calcLiability(layOddsNum, layStake).toFixed(2)}</p></div>
        </div>

        <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide mb-2">Stake calculator</p>
        <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-3 flex items-center justify-between mb-4">
          <span style={{ color: c.textSecondary }} className="text-xs">Stake</span>
          <div className="flex items-center gap-2">
            <span style={{ color: c.text }} className="text-base font-medium">£</span>
            <input type="number" step="1" value={stake} placeholder="0" onChange={(e) => setStake(e.target.value)} style={{ background: "transparent", color: c.text, width: 70 }} className="text-base font-medium text-right" />
          </div>
        </div>

        <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide mb-2">Outcomes</p>
        <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-3 mb-4 flex flex-col gap-3">
          <div className="flex items-center justify-between"><span style={{ color: c.textSecondary }} className="text-sm">2UP early payout</span><span style={{ color: c.green }} className="text-sm font-medium">£{ftaProfit.toFixed(2)}</span></div>
          <div className="flex items-center justify-between"><span style={{ color: c.textSecondary }} className="text-sm">Win (no 2UP)</span><span style={{ color: qualifyingLoss >= 0 ? c.green : c.red }} className="text-sm font-medium">{qualifyingLoss >= 0 ? "£" : "-£"}{Math.abs(qualifyingLoss).toFixed(2)}</span></div>
          <div className="flex items-center justify-between"><span style={{ color: c.textSecondary }} className="text-sm">Lose / draw</span><span style={{ color: qualifyingLoss >= 0 ? c.green : c.red }} className="text-sm font-medium">{qualifyingLoss >= 0 ? "£" : "-£"}{Math.abs(qualifyingLoss).toFixed(2)}</span></div>
        </div>

        <div className="flex items-center justify-between mb-4">
          <div>
            <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide">FTA payout</p>
            <p style={{ color: c.green }} className="text-xl font-medium">£{ftaProfit.toFixed(2)}</p>
          </div>
          <p style={{ color: c.textSecondary }} className="text-xs">if qualifying lead then fails to win</p>
        </div>

        <button style={{ background: c.green, color: c.greenDark }} className="w-full rounded-xl py-3 flex items-center justify-center gap-2 text-sm font-medium">
          <Bookmark size={16} /> Track bet
        </button>
        <p style={{ color: c.textSecondary }} className="text-xs text-center mt-2">
          Tracking isn't wired to My Bets yet -- stub button.
        </p>
      </div>
    </div>
  );
}

function StatusPill({ text, tone }) {
  return (
    <span style={{ color: tone, border: "1px solid " + tone }} className="text-xs font-medium px-3 py-1 rounded-full">{text}</span>
  );
}

function LiveMatchCard({ m }) {
  const fta = getFtaStatus(m);
  return (
    <div style={{ background: c.card, border: "1px solid " + (fta.tone === c.green ? c.green : c.border) }} className="rounded-2xl p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <span style={{ background: c.greenDark, color: c.green }} className="text-xs font-medium px-3 py-1 rounded-full">{m.minute}</span>
        {m.twoUpActive && <StatusPill text="2UP active" tone={c.green} />}
      </div>
      <div className="flex items-center justify-center gap-3">
        <span style={{ color: c.text }} className="text-base font-medium">{m.home_team}</span>
        <span style={{ color: c.text }} className="text-lg font-medium">{m.home_score} - {m.away_score}</span>
        <span style={{ color: c.text }} className="text-base font-medium">{m.away_team}</span>
      </div>
      <div style={{ background: c.cardAlt, border: "1px solid " + c.border }} className="rounded-xl px-3 py-2 flex items-center justify-between">
        <span style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide">FTA status</span>
        <span style={{ color: fta.tone }} className="text-xs font-medium flex items-center gap-2"><Circle size={9} fill={fta.tone} stroke="none" /> {fta.label}</span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div style={{ background: c.cardAlt, border: "1px solid " + c.border }} className="rounded-xl p-3 text-center">
          <p style={{ color: c.textSecondary }} className="text-xs mb-1">Back (2UP)</p>
          <p style={{ color: c.text }} className="text-lg font-medium">{m.backOdds2up ? m.backOdds2up.toFixed(2) : "—"}</p>
        </div>
        <div style={{ background: c.cardAlt, border: "1px solid " + c.border }} className="rounded-xl p-3 text-center">
          <p style={{ color: c.textSecondary }} className="text-xs mb-1">Lay</p>
          <p style={{ color: c.cyan }} className="text-lg font-medium">{m.layOdds.toFixed(2)}</p>
        </div>
      </div>
      {m.timeline.length > 0 && (
        <div style={{ background: c.cardAlt, border: "1px solid " + c.border }} className="rounded-xl p-3 flex flex-col gap-2">
          {m.timeline.map((ev, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <span style={{ color: c.textSecondary, width: 32 }}>{ev.minute}</span>
              <span style={{ color: c.text }} className="flex-1">{ev.team}</span>
              <span aria-hidden="true">⚽</span>
              <span style={{ color: c.text }}>{ev.score}</span>
              {ev.tag && <span style={{ color: c.green }} className="text-xs font-medium">({ev.tag})</span>}
            </div>
          ))}
        </div>
      )}
      <button
        style={{ background: c.cardAlt, border: "1px solid " + c.border, color: c.text }}
        className="w-full rounded-xl py-3 text-sm font-medium"
        title="Live match detail view isn't built yet -- stub button"
      >
        View match details
      </button>
    </div>
  );
}

function UpcomingMatchCard({ m }) {
  return (
    <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-2xl p-4 flex items-center justify-between">
      <div className="min-w-0">
        <p style={{ color: c.textSecondary }} className="text-xs mb-1">{m.league}</p>
        <p style={{ color: c.text }} className="text-sm font-medium truncate">{m.home_team} vs {m.away_team}</p>
      </div>
      <div className="text-right flex-shrink-0">
        <p style={{ color: c.textSecondary }} className="text-xs">Starts in {m.kickoffIn}</p>
        <p style={{ color: c.cyan }} className="text-sm font-medium">Lay {m.layOdds.toFixed(2)}</p>
      </div>
    </div>
  );
}

function DashboardLiveCard({ m, onNavigate }) {
  const fta = getFtaStatus(m);
  return (
    <button
      onClick={() => onNavigate("live")}
      style={{ background: c.card, border: "1px solid " + (fta.tone === c.green ? c.green : c.border), textAlign: "left" }}
      className="rounded-2xl p-4 w-full"
    >
      <div className="flex items-center justify-between mb-3">
        <span style={{ color: c.green }} className="text-xs font-medium flex items-center gap-1"><Circle size={8} fill={c.green} /> Live</span>
        <span style={{ color: c.textSecondary }} className="text-xs">{m.minute}</span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <div>
          <p style={{ color: c.text }} className="text-sm font-medium mb-2">{m.home_team} {m.home_score} - {m.away_score} {m.away_team}</p>
          <span style={{ color: fta.tone }} className="text-xs font-medium flex items-center gap-2"><Circle size={8} fill={fta.tone} stroke="none" /> {fta.label}</span>
        </div>
        <div style={{ background: c.cardAlt, border: "1px solid " + c.border }} className="rounded-xl px-3 py-2 text-center flex-shrink-0">
          <p style={{ color: c.textSecondary }} className="text-xs mb-1">Potential profit</p>
          <p style={{ color: c.green }} className="text-lg font-medium">£{m.potentialProfit.toFixed(2)}</p>
        </div>
      </div>
    </button>
  );
}

function BetRow({ b }) {
  const openBet = b.status === "Open";
  return (
    <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p style={{ color: c.textSecondary }} className="text-xs mb-1 truncate">{b.league}</p>
          <p style={{ color: c.text }} className="text-sm font-medium truncate">{b.match}</p>
        </div>
        <span style={{ color: openBet ? c.cyan : resultTone(b.result), border: "1px solid " + (openBet ? c.cyan : resultTone(b.result)) }} className="text-xs font-medium px-2 py-0.5 rounded-full flex-shrink-0">
          {openBet ? "Open" : b.result}
        </span>
      </div>
      <div className="flex items-center justify-between text-sm">
        <span style={{ color: c.textSecondary }}>Stake £{b.stake.toFixed(2)}</span>
        <span style={{ color: openBet ? c.textSecondary : resultTone(b.result) }} className="font-medium">
          {openBet ? "Exp. £" + b.expected_profit.toFixed(2) : (b.actual_profit >= 0 ? "+£" : "-£") + Math.abs(b.actual_profit).toFixed(2)}
        </span>
      </div>
      <p style={{ color: c.textSecondary }} className="text-xs">{openBet ? "Opened " + b.opened : "Settled " + b.settled}</p>
    </div>
  );
}

function AlertRow({ a }) {
  const meta = ALERT_TYPES[a.type];
  const Icon = meta.icon;
  return (
    <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4 flex items-start gap-3">
      <div style={{ background: c.cardAlt, color: meta.tone }} className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0">
        <Icon size={16} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <p style={{ color: c.text }} className="text-sm font-medium truncate">{a.title}</p>
          {a.unread && <span style={{ background: c.cyan }} className="w-2 h-2 rounded-full flex-shrink-0" />}
        </div>
        <p style={{ color: c.textSecondary }} className="text-xs mt-0.5 truncate">{a.detail}</p>
        <p style={{ color: c.textSecondary }} className="text-xs mt-1">{a.time}</p>
      </div>
    </div>
  );
}

function Toggle({ on, onChange }) {
  return (
    <button onClick={() => onChange(!on)} style={{ background: on ? c.green : c.cardAlt, border: "1px solid " + (on ? c.green : c.border) }} className="w-11 h-6 rounded-full relative flex-shrink-0">
      <span style={{ background: on ? c.greenDark : c.textSecondary, left: on ? 22 : 2 }} className="absolute top-0.5 w-4 h-4 rounded-full transition-all" />
    </button>
  );
}

function SettingsRow({ icon: Icon, label, value, tone, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{ borderBottom: "1px solid " + c.border }}
      className="w-full flex items-center gap-3 py-3 text-left"
      title={onClick ? undefined : "Not wired to a destination yet -- stub row"}
    >
      <Icon size={18} style={{ color: tone || c.textSecondary }} />
      <span style={{ color: c.text }} className="text-sm flex-1">{label}</span>
      {value && <span style={{ color: c.textSecondary }} className="text-sm">{value}</span>}
      <ChevronRight size={16} style={{ color: c.textSecondary }} />
    </button>
  );
}

/*
  REVENUECAT INTEGRATION NOTES
  ============================
  Backend contract (from app.py / revenuecat.py / README.md), already built:
    GET  /me                -> { entitled, entitlement, status, expires_at, prefs }
    GET  /opportunities     -> 402 SUBSCRIPTION_REQUIRED if not entitled (require_pro)
    POST /webhooks/revenuecat -> keeps the subscribers table current server-side

  What's genuinely missing (not in any file shared so far): the actual
  client-side purchase flow. There's no Purchases SDK configured
  anywhere -- no Purchases.configure(), no purchasePackage() call, no
  Web Billing / Stripe checkout trigger. That has to come from whichever
  RevenueCat client SDK targets this platform (native SDK for iOS/
  Android, RevenueCat Web Billing or Stripe for the web build) --
  distinct from this REST contract, which only reports entitlement
  status, it doesn't sell anything.

  Real integration, once that SDK exists:
    1. On app load: call GET /me with `Authorization: Bearer <Purchases.appUserID>`,
       store `entitled` in state (exactly what `entitled` below simulates).
    2. Gate Pro-only screens on that state -- currently just Opportunities,
       matching require_pro() in app.py exactly. Don't gate more than the
       backend actually enforces.
    3. "Upgrade to Pro" triggers the platform SDK's purchase flow, not a
       direct API call -- the API never takes payment, RevenueCat/the
       store does.
    4. After a successful purchase, call GET /me again (mirrors
       is_entitled(user_id, refresh=True) server-side) to unlock
       immediately rather than waiting for the webhook to land.

  The toggle below is a DEMO STAND-IN for step 1 only, so the paywall
  can actually be seen and tested here. It is not the real entitlement
  check and must not ship as-is.
*/
function subscriptionStatusText(sub) {
  if (!sub.status || sub.status === "free") {
    return { text: "No active subscription", tone: c.textSecondary };
  }
  const dateStr = sub.expires_at
    ? new Date(sub.expires_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })
    : null;
  switch (sub.status) {
    case "active":
      return { text: "Renews " + dateStr, tone: c.green };
    case "cancelled":
      return { text: "Cancelled — access until " + dateStr, tone: c.orange };
    case "billing_issue":
      return { text: "Payment failed — update your card", tone: c.red };
    case "expired":
      return { text: "Expired — upgrade to unlock Pro", tone: c.red };
    case "refund":
    case "revoke":
      return { text: "Subscription revoked", tone: c.red };
    default:
      return { text: "Status unknown — contact support", tone: c.textSecondary };
  }
}

function Paywall({ onSimulateUpgrade }) {
  return (
    <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-2xl p-6 text-center mt-4">
      <div style={{ background: c.greenDark }} className="w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-4">
        <Lock size={20} style={{ color: c.green }} />
      </div>
      <p style={{ color: c.text }} className="text-base font-medium mb-2">Opportunities is a Pro feature</p>
      <p style={{ color: c.textSecondary }} className="text-sm mb-5">
        Upgrade to see live-ranked FTA opportunities, full EV breakdowns, and the reactive stake calculator.
      </p>
      <button
        onClick={onSimulateUpgrade}
        style={{ background: c.green, color: c.greenDark }}
        className="w-full rounded-xl py-3 text-sm font-medium mb-2"
      >
        Upgrade to Pro
      </button>
      <p style={{ color: c.textSecondary }} className="text-xs">
        (Demo only -- no purchase SDK wired in yet)
      </p>
    </div>
  );
}


function CalcField({ label, value, onChange, tone, prefix }) {
  return (
    <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-3">
      <p style={{ color: c.textSecondary }} className="text-xs mb-1">{label}</p>
      <div className="flex items-center gap-1">
        {prefix && <span style={{ color: tone || c.text }} className="text-lg font-medium">{prefix}</span>}
        <input type="number" step="0.01" value={value} placeholder="0" onChange={(e) => onChange(e.target.value)} style={{ background: "transparent", color: tone || c.text, width: "100%" }} className="text-lg font-medium" />
      </div>
    </div>
  );
}

function OutputRow({ label, value, tone }) {
  return (
    <div className="flex items-center justify-between py-2">
      <span style={{ color: c.textSecondary }} className="text-sm">{label}</span>
      <span style={{ color: tone || c.text }} className="text-sm font-medium">{value}</span>
    </div>
  );
}

// ============================================================
// PAGES
// ============================================================
function DashboardPage({ onNavigate, onOpenOpportunity, unreadCount }) {
  const kpis = [
    { label: "Best EV", value: bestEv.toFixed(1) + "%", tone: c.green },
    { label: "Average EV", value: avgEv.toFixed(1) + "%", tone: c.cyan },
    { label: "Opportunities", value: String(opportunities.length), tone: c.text },
    { label: "Win rate", value: "—", tone: c.textSecondary },
    { label: "Live now", value: "—", tone: c.textSecondary },
  ];

  const trackedLiveMatch = liveMatches[1]; // Leverkusen vs Mainz, 2-2

  const totalProfit = bets.filter((b) => b.status === "Settled").reduce((sum, b) => sum + b.actual_profit, 0);
  const exposure = bets.filter((b) => b.status === "Open").reduce((sum, b) => sum + b.stake, 0);
  const settledStake = bets.filter((b) => b.status === "Settled").reduce((sum, b) => sum + b.stake, 0);
  const roi = settledStake > 0 ? (totalProfit / settledStake) * 100 : 0;
  const livePL = bets.filter((b) => b.status === "Open").reduce((sum, b) => sum + liveImpliedPL(b), 0);

  return (
    <PageShell activeTab="dashboard" onNavigate={onNavigate} unreadCount={unreadCount}>
      <PageHeader onNavigate={onNavigate} unreadCount={unreadCount} />

      <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-2xl p-5 mb-6">
        <p style={{ color: c.textSecondary }} className="text-xs mb-1">Total profit</p>
        <div className="flex items-end justify-between mb-4">
          <p style={{ color: totalProfit >= 0 ? c.text : c.red }} className="text-3xl font-medium">{totalProfit >= 0 ? "£" : "-£"}{Math.abs(totalProfit).toFixed(2)}</p>
          <div className="w-24 h-10">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={equityData}>
                <Line type="monotone" dataKey="v" stroke={c.green} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <p style={{ color: c.textSecondary }} className="text-xs">Live P/L</p>
            <p style={{ color: livePL >= 0 ? c.green : c.red }} className="text-sm font-medium flex items-center gap-1">
              {livePL >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
              {livePL >= 0 ? "£" : "-£"}{Math.abs(livePL).toFixed(2)}
            </p>
          </div>
          <div><p style={{ color: c.textSecondary }} className="text-xs">Exposure</p><p style={{ color: c.text }} className="text-sm font-medium">£{exposure.toFixed(2)}</p></div>
          <div><p style={{ color: c.textSecondary }} className="text-xs">ROI</p><p style={{ color: roi >= 0 ? c.green : c.red }} className="text-sm font-medium">{roi.toFixed(1)}%</p></div>
        </div>
      </div>

      <div className="flex gap-3 overflow-x-auto mb-6 -mx-1 px-1">
        {kpis.map((k) => <KpiCard key={k.label} {...k} />)}
      </div>

      <div className="flex items-center justify-between mb-3">
        <p style={{ color: c.text }} className="text-base font-medium">Top opportunities</p>
        <button onClick={() => onNavigate("opportunities")} style={{ color: c.cyan }} className="text-xs font-medium">View all</button>
      </div>
      <div className="flex gap-3 overflow-x-auto mb-6 -mx-1 px-1">
        {opportunities.slice(0, 4).map((o) => <OpportunityCard key={o.fixture_id} o={o} onClick={onOpenOpportunity} />)}
      </div>

      <div className="flex items-center justify-between mb-3">
        <p style={{ color: c.text }} className="text-base font-medium">Live monitoring</p>
        <button onClick={() => onNavigate("live")} style={{ color: c.cyan }} className="text-xs font-medium">View all</button>
      </div>
      <div className="mb-6">
        <DashboardLiveCard m={trackedLiveMatch} onNavigate={onNavigate} />
      </div>

      <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-2xl p-5">
        <p style={{ color: c.text }} className="text-sm font-medium mb-4">Analytics snapshot</p>
        <div className="grid grid-cols-2 gap-4">
          <div><p style={{ color: c.textSecondary }} className="text-xs">Top league</p><p style={{ color: c.text }} className="text-sm font-medium">{topLeague}</p></div>
          <div><p style={{ color: c.textSecondary }} className="text-xs">Highest EV team</p><p style={{ color: c.text }} className="text-sm font-medium">{highestEvOpportunity.home_team}</p></div>
          <div><p style={{ color: c.textSecondary }} className="text-xs">Avg market edge</p><p style={{ color: c.text }} className="text-sm font-medium">+{avgMarketEdge.toFixed(1)}%</p></div>
          <div><p style={{ color: c.textSecondary }} className="text-xs">ROI (settled bets)</p><p style={{ color: roi >= 0 ? c.green : c.red }} className="text-sm font-medium">{roi.toFixed(1)}%</p></div>
        </div>
      </div>
    </PageShell>
  );
}

function OpportunitiesPage({ onNavigate, onOpenOpportunity, unreadCount, entitled, onSimulateUpgrade }) {
  const [leagueFilter, setLeagueFilter] = useState("All leagues");
  const leagues = ["All leagues", "Premier League", "Ekstraklasa", "Ligue 1", "Bundesliga"];
  const filtered = opportunities.filter((o) => leagueFilter === "All leagues" || o.league === leagueFilter);

  const kpis = [
    { label: "Best EV", value: bestEv.toFixed(1) + "%", tone: c.green },
    { label: "Average EV", value: avgEv.toFixed(1) + "%", tone: c.cyan },
    { label: "Opportunities", value: String(opportunities.length), tone: c.text },
  ];

  return (
    <PageShell activeTab="opportunities" onNavigate={onNavigate} unreadCount={unreadCount}>
      <PageHeader onNavigate={onNavigate} unreadCount={unreadCount} />
      <p style={{ color: c.text }} className="text-xl font-medium mb-1">Opportunities</p>

      {!entitled ? (
        <>
          <p style={{ color: c.textSecondary }} className="text-sm mb-4">
            Mirrors the real 402 SUBSCRIPTION_REQUIRED response from GET /opportunities
          </p>
          <Paywall onSimulateUpgrade={onSimulateUpgrade} />
        </>
      ) : (
        <>
          <p style={{ color: c.textSecondary }} className="text-sm mb-4">{filtered.length} live {filtered.length === 1 ? "opportunity" : "opportunities"}</p>

          <div className="flex gap-2 overflow-x-auto mb-5 -mx-1 px-1">
            {kpis.map((k) => (
              <div key={k.label} style={{ background: c.card, border: "1px solid " + c.border }} className="flex-shrink-0 rounded-xl px-3 py-2 min-w-[90px]">
                <p style={{ color: c.textSecondary }} className="text-xs mb-0.5">{k.label}</p>
                <p style={{ color: k.tone }} className="text-sm font-medium">{k.value}</p>
              </div>
            ))}
          </div>

          <div className="flex gap-2 overflow-x-auto mb-5 -mx-1 px-1">
            {leagues.map((lg) => {
              const active = lg === leagueFilter;
              return (
                <button key={lg} onClick={() => setLeagueFilter(lg)} style={{ background: active ? c.green : c.card, border: "1px solid " + (active ? c.green : c.border), color: active ? c.greenDark : c.textSecondary }} className="flex-shrink-0 text-xs font-medium px-3 py-2 rounded-full whitespace-nowrap">
                  {lg}
                </button>
              );
            })}
          </div>

          <div className="flex flex-col gap-3">
            {filtered.map((o) => <OpportunityRow key={o.fixture_id} o={o} onClick={onOpenOpportunity} />)}
            {filtered.length === 0 && <p style={{ color: c.textSecondary }} className="text-sm text-center py-10">No opportunities match this filter right now.</p>}
          </div>
        </>
      )}
    </PageShell>
  );
}

// ============================================================
// EARLY GOAL HUNTER -- separate scoring engine (early_goal_hunter.py),
// separate fixture pool from FTA Opportunities. Ranked by hunter_score.
// ============================================================
function hunterTone(score) {
  if (score >= 80) return c.green;
  if (score >= 55) return c.orange;
  return c.textSecondary;
}

function EarlyGoalHunterRow({ f }) {
  return (
    <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4 flex flex-col gap-3 w-full">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p style={{ color: c.textSecondary }} className="text-xs mb-1 truncate">{f.kickoff} · {f.league}</p>
          <p style={{ color: c.text }} className="text-sm font-medium truncate">{f.home_team}</p>
          <p style={{ color: c.textSecondary }} className="text-sm truncate">vs {f.away_team}</p>
        </div>
        <div className="text-right flex-shrink-0">
          <p style={{ color: hunterTone(f.hunter_score) }} className="text-lg font-medium">{f.hunter_score.toFixed(0)}</p>
          <p style={{ color: c.textSecondary }} className="text-xs">Hunter score</p>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <p style={{ color: c.textSecondary }} className="text-xs">1H goal</p>
          <p style={{ color: c.text }} className="text-sm font-medium">{(f.p_first_half_goal * 100).toFixed(0)}%</p>
        </div>
        <div>
          <p style={{ color: c.textSecondary }} className="text-xs">Home scores 1st</p>
          <p style={{ color: c.cyan }} className="text-sm font-medium">{(f.p_home_scores_first * 100).toFixed(0)}%</p>
        </div>
        <div>
          <p style={{ color: c.textSecondary }} className="text-xs">Away scores 1st</p>
          <p style={{ color: c.blue }} className="text-sm font-medium">{(f.p_away_scores_first * 100).toFixed(0)}%</p>
        </div>
      </div>
    </div>
  );
}

function EarlyGoalHunterPage({ onNavigate, unreadCount }) {
  const ranked = [...otherFixtures].sort((a, b) => b.hunter_score - a.hunter_score);
  return (
    <PageShell activeTab="early-goal-hunter" onNavigate={onNavigate} unreadCount={unreadCount}>
      <PageHeader onNavigate={onNavigate} unreadCount={unreadCount} />
      <p style={{ color: c.text }} className="text-xl font-medium mb-1">Early Goal Hunter</p>
      <p style={{ color: c.textSecondary }} className="text-sm mb-4">
        Fixtures ranked by likelihood of an early goal — a separate signal from FTA opportunities, not a filtered view of them.
      </p>
      <div className="flex flex-col gap-3">
        {ranked.map((f) => <EarlyGoalHunterRow key={f.fixture_id} f={f} />)}
      </div>
    </PageShell>
  );
}

// ============================================================
// CHAOS FACTOR -- separate scoring engine (chaos_index.py), same
// fixture pool as Early Goal Hunter (different lens), own pie
// breakdown per fixture: O2.5 / BTTS / early goal / instability.
// ============================================================
const CHAOS_COLORS = { o2_5: c.cyan, btts: c.blue, early_goal: c.orange, instability: c.red };
const CHAOS_LABELS = { o2_5: "O2.5", btts: "BTTS", early_goal: "Early goal", instability: "Instability" };

function chaosLabelTone(label) {
  if (label === "high") return c.red;
  if (label === "medium") return c.orange;
  return c.cyan;
}

function ChaosFixtureCard({ f }) {
  const pieData = Object.entries(f.chaos_components).map(([key, value]) => ({
    name: CHAOS_LABELS[key], value, key,
  }));
  return (
    <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4 flex flex-col gap-3 w-full">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p style={{ color: c.textSecondary }} className="text-xs mb-1 truncate">{f.kickoff} · {f.league}</p>
          <p style={{ color: c.text }} className="text-sm font-medium truncate">{f.home_team}</p>
          <p style={{ color: c.textSecondary }} className="text-sm truncate">vs {f.away_team}</p>
        </div>
        <div className="text-right flex-shrink-0">
          <p style={{ color: chaosLabelTone(f.chaos_label) }} className="text-lg font-medium">{f.chaos_index.toFixed(0)}</p>
          <p style={{ color: chaosLabelTone(f.chaos_label) }} className="text-xs uppercase font-medium">{f.chaos_label}</p>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div style={{ width: 90, height: 90 }} className="flex-shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={22} outerRadius={40} paddingAngle={2}>
                {pieData.map((entry) => <Cell key={entry.key} fill={CHAOS_COLORS[entry.key]} stroke="none" />)}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-col gap-1 flex-1">
          {pieData.map((entry) => (
            <div key={entry.key} className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-1.5" style={{ color: c.textSecondary }}>
                <span style={{ background: CHAOS_COLORS[entry.key], width: 7, height: 7, borderRadius: "50%", display: "inline-block" }} />
                {entry.name}
              </span>
              <span style={{ color: c.text }} className="font-medium">{entry.value}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ChaosFactorPage({ onNavigate, unreadCount }) {
  const ranked = [...otherFixtures].sort((a, b) => b.chaos_index - a.chaos_index);
  return (
    <PageShell activeTab="chaos-factor" onNavigate={onNavigate} unreadCount={unreadCount}>
      <PageHeader onNavigate={onNavigate} unreadCount={unreadCount} />
      <p style={{ color: c.text }} className="text-xl font-medium mb-1">Chaos Factor</p>
      <p style={{ color: c.textSecondary }} className="text-sm mb-4">
        Fixtures ranked by unpredictability — O2.5, BTTS, early goals, and instability combined. A separate signal, not FTA-filtered.
      </p>
      <div className="flex flex-col gap-3">
        {ranked.map((f) => <ChaosFixtureCard key={f.fixture_id} f={f} />)}
      </div>
    </PageShell>
  );
}

// ============================================================
// MODEL TESTING -- the first genuinely network-connected page in this
// app. Everything else in app.jsx is mock data; this one makes a real
// fetch() to GET /model/runs on your actual FastAPI backend. Needs a
// real loading/error/empty state, unlike the mock pages, because a
// real network call can genuinely fail.
//
// API_BASE reads from an env var rather than a hardcoded IP -- set
// NEXT_PUBLIC_API_URL in your real Next.js deployment. Falls back to
// localhost for local dev against `uvicorn api.app:app`.
// CORS_ORIGINS on the backend must include wherever this page is
// actually served from, or the browser will block the request even
// though the server itself is reachable.
//
// This page is NOT gated by `entitled` -- it's a dev/testing tool for
// you, not a subscriber feature, matching the /model/runs endpoint
// itself (any authenticated user, not Pro-only). Worth hiding this
// from the flyout menu before a real public launch.
const API_BASE =
  (typeof process !== "undefined" && process.env && process.env.NEXT_PUBLIC_API_URL) ||
  "http://localhost:8080";

function ModelTestingPage({ onNavigate, unreadCount }) {
  const [token, setToken] = useState("");
  const [runs, setRuns] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchRuns = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(API_BASE + "/model/runs", {
        headers: { Authorization: "Bearer " + (token || "test_user_1") },
      });
      if (!res.ok) {
        throw new Error("HTTP " + res.status + " -- check the token and that CORS_ORIGINS allows this origin");
      }
      const data = await res.json();
      setRuns(data.runs || []);
    } catch (e) {
      setError(e.message || "Request failed");
      setRuns(null);
    } finally {
      setLoading(false);
    }
  };

  const chartData = (runs || [])
    .slice()
    .reverse()
    .map((r, i) => ({
      index: i + 1,
      brier: r.brier_score,
      roc_auc: r.roc_auc,
    }));

  return (
    <PageShell activeTab="model-testing" onNavigate={onNavigate} unreadCount={unreadCount}>
      <PageHeader onNavigate={onNavigate} unreadCount={unreadCount} />
      <p style={{ color: c.text }} className="text-xl font-medium mb-1">Model testing</p>
      <p style={{ color: c.textSecondary }} className="text-sm mb-4">
        Real training runs from your model_runs table — no odds involved, no mock data.
      </p>

      <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-3 mb-4 flex gap-2">
        <input
          type="text"
          value={token}
          placeholder="Bearer token (Purchases.appUserID)"
          onChange={(e) => setToken(e.target.value)}
          style={{ background: c.cardAlt, color: c.text, border: "1px solid " + c.border }}
          className="flex-1 text-sm rounded-lg px-3 py-2"
        />
        <button
          onClick={fetchRuns}
          style={{ background: c.green, color: c.greenDark }}
          className="text-sm font-medium px-4 py-2 rounded-lg flex-shrink-0"
        >
          Fetch
        </button>
      </div>

      {loading && <p style={{ color: c.textSecondary }} className="text-sm text-center py-6">Loading…</p>}

      {error && (
        <div style={{ background: c.card, border: "1px solid " + c.red }} className="rounded-xl p-4 mb-4">
          <p style={{ color: c.red }} className="text-sm font-medium mb-1">Request failed</p>
          <p style={{ color: c.textSecondary }} className="text-xs">{error}</p>
          <p style={{ color: c.textSecondary }} className="text-xs mt-2">
            API_BASE is currently: {API_BASE}
          </p>
        </div>
      )}

      {!loading && !error && runs === null && (
        <p style={{ color: c.textSecondary }} className="text-sm text-center py-10">
          Enter a token and tap Fetch to pull real training runs from {API_BASE}.
        </p>
      )}

      {!loading && !error && runs !== null && runs.length === 0 && (
        <p style={{ color: c.textSecondary }} className="text-sm text-center py-10">
          No training runs logged yet — run retrain_model.py at least once.
        </p>
      )}

      {!loading && !error && runs && runs.length > 0 && (
        <>
          <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-3 mb-4">
            <div style={{ height: 180 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 5, right: 8, left: -20, bottom: 0 }}>
                  <CartesianGrid stroke={c.border} strokeDasharray="3 3" />
                  <XAxis dataKey="index" stroke={c.textSecondary} tick={{ fontSize: 11 }} label={{ value: "Run", position: "insideBottom", offset: -2, fill: c.textSecondary, fontSize: 11 }} />
                  <YAxis stroke={c.textSecondary} tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: c.cardAlt, border: "1px solid " + c.border, borderRadius: 8 }} labelStyle={{ color: c.text }} />
                  <Legend wrapperStyle={{ fontSize: 12, color: c.textSecondary }} />
                  <Line type="monotone" dataKey="brier" name="Brier score" stroke={c.orange} strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="roc_auc" name="ROC AUC" stroke={c.cyan} strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="flex flex-col gap-3">
            {runs.map((r) => (
              <div key={r.id} style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <p style={{ color: c.text }} className="text-sm font-medium">{r.model_name} {r.version}</p>
                  <p style={{ color: c.textSecondary }} className="text-xs">{r.trained_at}</p>
                </div>
                <div className="grid grid-cols-4 gap-2 text-center">
                  <div><p style={{ color: c.textSecondary }} className="text-xs">Rows</p><p style={{ color: c.text }} className="text-sm font-medium">{r.training_rows}</p></div>
                  <div><p style={{ color: c.textSecondary }} className="text-xs">Brier</p><p style={{ color: c.orange }} className="text-sm font-medium">{r.brier_score?.toFixed(4)}</p></div>
                  <div><p style={{ color: c.textSecondary }} className="text-xs">Log loss</p><p style={{ color: c.text }} className="text-sm font-medium">{r.log_loss?.toFixed(4)}</p></div>
                  <div><p style={{ color: c.textSecondary }} className="text-xs">ROC AUC</p><p style={{ color: c.cyan }} className="text-sm font-medium">{r.roc_auc?.toFixed(4)}</p></div>
                </div>
                {r.notes && <p style={{ color: c.textSecondary }} className="text-xs mt-2">{r.notes}</p>}
              </div>
            ))}
          </div>
        </>
      )}
    </PageShell>
  );
}

function LiveMonitorPage({ onNavigate, unreadCount }) {
  const [tab, setTab] = useState("live");
  return (
    <PageShell activeTab="live" onNavigate={onNavigate} unreadCount={unreadCount}>
      <PageHeader onNavigate={onNavigate} unreadCount={unreadCount} />
      <div className="flex items-center justify-between mb-5">
        <p style={{ color: c.text }} className="text-xl font-medium">Live monitoring</p>
        <span style={{ background: c.greenDark, color: c.green }} className="text-xs font-medium px-3 py-1 rounded-full flex items-center gap-1"><Circle size={8} fill={c.green} /> Live</span>
      </div>
      <div style={{ background: c.card, border: "1px solid " + c.border }} className="flex rounded-xl p-1 mb-5">
        <button onClick={() => setTab("live")} style={{ background: tab === "live" ? c.cardAlt : "transparent", color: tab === "live" ? c.text : c.textSecondary }} className="flex-1 text-sm font-medium py-2 rounded-lg">Live</button>
        <button onClick={() => setTab("upcoming")} style={{ background: tab === "upcoming" ? c.cardAlt : "transparent", color: tab === "upcoming" ? c.text : c.textSecondary }} className="flex-1 text-sm font-medium py-2 rounded-lg">Upcoming ({upcomingMatches.length})</button>
      </div>
      <div className="flex flex-col gap-4">
        {tab === "live"
          ? liveMatches.filter(isVisibleLive).map((m) => <LiveMatchCard key={m.fixture_id} m={m} />)
          : upcomingMatches.map((m) => <UpcomingMatchCard key={m.fixture_id} m={m} />)}
      </div>
    </PageShell>
  );
}

function MyBetsPage({ onNavigate, unreadCount }) {
  const [tab, setTab] = useState("open");
  const [showGraph, setShowGraph] = useState(false);

  const openBets = bets.filter((b) => b.status === "Open");
  const settledBets = bets.filter((b) => b.status === "Settled");

  const totalBets = bets.length;
  const totalProfit = settledBets.reduce((sum, b) => sum + b.actual_profit, 0);
  const totalEv = bets.reduce((sum, b) => sum + b.expected_profit, 0);
  const pending = openBets.reduce((sum, b) => sum + b.stake, 0);
  const avgEvHere = totalBets > 0 ? totalEv / totalBets : 0;

  const chronological = [bets[4], bets[3], bets[2], bets[1], bets[0]];
  let runningProfit = 0;
  let runningEv = 0;
  const chartData = chronological.map((b, i) => {
    runningEv += b.expected_profit;
    if (b.status === "Settled") runningProfit += b.actual_profit;
    return { index: i + 1, profit: Number(runningProfit.toFixed(2)), ev: Number(runningEv.toFixed(2)) };
  });

  return (
    <PageShell activeTab="bets" onNavigate={onNavigate} unreadCount={unreadCount}>
      <PageHeader onNavigate={onNavigate} unreadCount={unreadCount} />
      <p style={{ color: c.text }} className="text-xl font-medium mb-4">My bets</p>

      <div className="flex flex-col gap-3 mb-6">
        <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl px-4 py-3 flex items-center justify-between">
          <span style={{ color: c.text }} className="text-sm font-medium">Total bets</span>
          <span style={{ color: c.text }} className="text-lg font-medium">{totalBets}</span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl px-4 py-3 flex items-center justify-between">
            <span style={{ color: c.text }} className="text-sm font-medium">Total profit</span>
            <span style={{ color: totalProfit >= 0 ? c.green : c.red }} className="text-lg font-medium">{totalProfit >= 0 ? "£" : "-£"}{Math.abs(totalProfit).toFixed(2)}</span>
          </div>
          <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl px-4 py-3 flex items-center justify-between">
            <span style={{ color: c.text }} className="text-sm font-medium">Total EV</span>
            <span style={{ color: c.cyan }} className="text-lg font-medium">£{totalEv.toFixed(2)}</span>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl px-4 py-3 flex items-center justify-between">
            <span style={{ color: c.text }} className="text-sm font-medium">Pending</span>
            <span style={{ color: c.text }} className="text-lg font-medium">£{pending.toFixed(2)}</span>
          </div>
          <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl px-4 py-3 flex items-center justify-between">
            <span style={{ color: c.text }} className="text-sm font-medium">Avg EV</span>
            <span style={{ color: c.cyan }} className="text-lg font-medium">£{avgEvHere.toFixed(2)}</span>
          </div>
        </div>
        <button onClick={() => setShowGraph(!showGraph)} style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl px-4 py-3 flex items-center justify-between">
          <span style={{ color: c.text }} className="text-sm font-medium">Graph</span>
          <ChevronRight size={18} style={{ color: c.textSecondary, transform: showGraph ? "rotate(90deg)" : "none" }} />
        </button>
        {showGraph && (
          <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-3">
            <div style={{ height: 220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 5, right: 8, left: -20, bottom: 0 }}>
                  <CartesianGrid stroke={c.border} strokeDasharray="3 3" />
                  <XAxis dataKey="index" stroke={c.textSecondary} tick={{ fontSize: 11 }} label={{ value: "Bets", position: "insideBottom", offset: -2, fill: c.textSecondary, fontSize: 11 }} />
                  <YAxis stroke={c.textSecondary} tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: c.cardAlt, border: "1px solid " + c.border, borderRadius: 8 }} labelStyle={{ color: c.text }} formatter={(value, name) => ["£" + value.toFixed(2), name === "profit" ? "Profit" : "EV"]} />
                  <Legend wrapperStyle={{ fontSize: 12, color: c.textSecondary }} />
                  <Line type="monotone" dataKey="profit" name="£ Profit" stroke={c.green} strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="ev" name="£ EV" stroke={c.cyan} strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>

      <div style={{ background: c.card, border: "1px solid " + c.border }} className="flex rounded-xl p-1 mb-5">
        <button onClick={() => setTab("open")} style={{ background: tab === "open" ? c.cardAlt : "transparent", color: tab === "open" ? c.text : c.textSecondary }} className="flex-1 text-sm font-medium py-2 rounded-lg">Open ({openBets.length})</button>
        <button onClick={() => setTab("settled")} style={{ background: tab === "settled" ? c.cardAlt : "transparent", color: tab === "settled" ? c.text : c.textSecondary }} className="flex-1 text-sm font-medium py-2 rounded-lg">Settled ({settledBets.length})</button>
      </div>

      <div className="flex flex-col gap-3">
        {(tab === "open" ? openBets : settledBets).map((b) => <BetRow key={b.id} b={b} />)}
      </div>
    </PageShell>
  );
}

const CALC_DEFAULTS = { bankroll: "2530.45", stake: "100", backOdds: "2.70", layOdds: "2.82", commission: "2", ftaPct: "25" };
const CALC_MODES = [
  { key: "qualifying", label: "Qualifying bet" },
  { key: "snr", label: "Free bet (SNR)" },
  { key: "sr", label: "Free bet (SR)" },
];

function CalculatorPage({ onNavigate, unreadCount }) {
  const [mode, setMode] = useState("qualifying");
  const [bankroll, setBankroll] = useState(CALC_DEFAULTS.bankroll);
  const [stake, setStake] = useState(CALC_DEFAULTS.stake);
  const [backOdds, setBackOdds] = useState(CALC_DEFAULTS.backOdds);
  const [layOdds, setLayOdds] = useState(CALC_DEFAULTS.layOdds);
  const [commission, setCommission] = useState(CALC_DEFAULTS.commission);
  const [ftaPct, setFtaPct] = useState(CALC_DEFAULTS.ftaPct);

  const reset = () => {
    setBankroll(CALC_DEFAULTS.bankroll);
    setStake(CALC_DEFAULTS.stake);
    setBackOdds(CALC_DEFAULTS.backOdds);
    setLayOdds(CALC_DEFAULTS.layOdds);
    setCommission(CALC_DEFAULTS.commission);
    setFtaPct(CALC_DEFAULTS.ftaPct);
  };

  const bankrollNum = parseFloat(bankroll) || 0;
  const stakeNum = parseFloat(stake) || 0;
  const backOddsNum = parseFloat(backOdds) || 0;
  const layOddsNum = parseFloat(layOdds) || 0;
  const commissionNum = parseFloat(commission) || 0;
  const ftaPctNum = parseFloat(ftaPct) || 0;
  const riskPercent = bankrollNum > 0 ? (stakeNum / bankrollNum) * 100 : 0;

  let content;
  if (mode === "qualifying") {
    const layStake = calcLayStake(backOddsNum, layOddsNum, stakeNum, commissionNum);
    const liability = calcLiability(layOddsNum, layStake);
    const qualifyingLoss = calcQualifyingLoss(backOddsNum, layOddsNum, stakeNum, layStake);
    const ftaProfit = calcFtaProfit(stakeNum, backOddsNum, layStake, commissionNum);
    const expectedProfit = calcExpectedProfit(ftaProfit, qualifyingLoss, ftaPctNum);
    const evPercent = calcEvPercent(expectedProfit, qualifyingLoss);
    content = (
      <>
        <div className="grid grid-cols-2 gap-3 mb-3">
          <CalcField label="Commission %" value={commission} onChange={setCommission} />
          <CalcField label="Estimated FTA %" value={ftaPct} onChange={setFtaPct} />
        </div>
        <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide mb-2">Results</p>
        <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4 mb-4">
          <OutputRow label="Lay stake needed" value={"£" + layStake.toFixed(2)} tone={c.cyan} />
          <div style={{ borderTop: "1px solid " + c.border }} />
          <OutputRow label="Liability" value={"£" + liability.toFixed(2)} tone={c.orange} />
          <div style={{ borderTop: "1px solid " + c.border }} />
          <OutputRow label="Qualifying loss" value={(qualifyingLoss >= 0 ? "£" : "-£") + Math.abs(qualifyingLoss).toFixed(2)} tone={qualifyingLoss >= 0 ? c.green : c.red} />
        </div>
        <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4">
          <OutputRow label="FTA payout (if triggered)" value={"£" + ftaProfit.toFixed(2)} tone={c.green} />
          <div style={{ borderTop: "1px solid " + c.border }} />
          <OutputRow label="Expected profit" value={(expectedProfit >= 0 ? "£" : "-£") + Math.abs(expectedProfit).toFixed(2)} tone={expectedProfit >= 0 ? c.green : c.red} />
          <div style={{ borderTop: "1px solid " + c.border }} />
          <OutputRow label="Expected value" value={evPercent.toFixed(1) + "%"} tone={evPercent >= 0 ? c.green : c.red} />
        </div>
      </>
    );
  } else if (mode === "snr") {
    const layStake = calcLayStakeSNR(backOddsNum, layOddsNum, stakeNum, commissionNum);
    const liability = calcLiability(layOddsNum, layStake);
    const ifBackWins = (backOddsNum - 1) * stakeNum - liability;
    const ifLayWins = layStake * (1 - commissionNum / 100);
    content = (
      <>
        <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide mb-2">Results</p>
        <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4 mb-4">
          <OutputRow label="Lay stake needed" value={"£" + layStake.toFixed(2)} tone={c.cyan} />
          <div style={{ borderTop: "1px solid " + c.border }} />
          <OutputRow label="Liability" value={"£" + liability.toFixed(2)} tone={c.orange} />
        </div>
        <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4">
          <OutputRow label="If back bet wins" value={(ifBackWins >= 0 ? "£" : "-£") + Math.abs(ifBackWins).toFixed(2)} tone={ifBackWins >= 0 ? c.green : c.red} />
          <div style={{ borderTop: "1px solid " + c.border }} />
          <OutputRow label="If lay bet wins" value={(ifLayWins >= 0 ? "£" : "-£") + Math.abs(ifLayWins).toFixed(2)} tone={ifLayWins >= 0 ? c.green : c.red} />
        </div>
      </>
    );
  } else {
    const layStake = calcLayStakeSR(backOddsNum, layOddsNum, stakeNum, commissionNum);
    const liability = calcLiability(layOddsNum, layStake);
    const ifBackWins = backOddsNum * stakeNum - liability;
    const ifLayWins = layStake * (1 - commissionNum / 100);
    content = (
      <>
        <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide mb-2">Results</p>
        <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4 mb-4">
          <OutputRow label="Lay stake needed" value={"£" + layStake.toFixed(2)} tone={c.cyan} />
          <div style={{ borderTop: "1px solid " + c.border }} />
          <OutputRow label="Liability" value={"£" + liability.toFixed(2)} tone={c.orange} />
        </div>
        <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4">
          <OutputRow label="If back bet wins" value={(ifBackWins >= 0 ? "£" : "-£") + Math.abs(ifBackWins).toFixed(2)} tone={ifBackWins >= 0 ? c.green : c.red} />
          <div style={{ borderTop: "1px solid " + c.border }} />
          <OutputRow label="If lay bet wins" value={(ifLayWins >= 0 ? "£" : "-£") + Math.abs(ifLayWins).toFixed(2)} tone={ifLayWins >= 0 ? c.green : c.red} />
        </div>
      </>
    );
  }

  return (
    <PageShell activeTab="menu" onNavigate={onNavigate} unreadCount={unreadCount}>
      <PageHeader onNavigate={onNavigate} unreadCount={unreadCount} />
      <div className="flex items-center justify-between mb-4">
        <p style={{ color: c.text }} className="text-xl font-medium">Calculator</p>
        <button onClick={reset} style={{ color: c.textSecondary }} className="flex items-center gap-1 text-xs font-medium"><RotateCcw size={14} /> Reset</button>
      </div>
      <div className="flex gap-2 overflow-x-auto mb-5 -mx-1 px-1">
        {CALC_MODES.map((m) => {
          const active = m.key === mode;
          return (
            <button key={m.key} onClick={() => setMode(m.key)} style={{ background: active ? c.green : c.card, border: "1px solid " + (active ? c.green : c.border), color: active ? c.greenDark : c.textSecondary }} className="flex-shrink-0 text-xs font-medium px-3 py-2 rounded-full whitespace-nowrap">
              {m.label}
            </button>
          );
        })}
      </div>
      <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide mb-2">{mode === "qualifying" ? "Inputs" : "Free bet inputs"}</p>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <CalcField label="Bankroll" value={bankroll} onChange={setBankroll} prefix="£" />
        <CalcField label={mode === "qualifying" ? "Back stake" : "Free bet amount"} value={stake} onChange={setStake} prefix="£" />
      </div>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <CalcField label="Back odds (bookie)" value={backOdds} onChange={setBackOdds} tone={c.green} />
        <CalcField label="Lay odds (exchange)" value={layOdds} onChange={setLayOdds} tone={c.cyan} />
      </div>
      {mode !== "qualifying" && (
        <div className="mb-3"><CalcField label="Commission %" value={commission} onChange={setCommission} /></div>
      )}
      {content}
      <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4 mt-4">
        <OutputRow label="Stake as % of bankroll" value={riskPercent.toFixed(1) + "%"} tone={riskPercent > 5 ? c.orange : c.text} />
      </div>
    </PageShell>
  );
}

function AlertsPage({ onNavigate, alerts, onMarkAllRead }) {
  const [filter, setFilter] = useState("all");
  const unreadCount = alerts.filter((a) => a.unread).length;
  const filtered = filter === "unread" ? alerts.filter((a) => a.unread) : alerts;

  return (
    <PageShell activeTab="menu" onNavigate={onNavigate} unreadCount={unreadCount}>
      <PageHeader onNavigate={onNavigate} unreadCount={unreadCount} />
      <div className="flex items-center justify-between mb-5">
        <p style={{ color: c.text }} className="text-xl font-medium">Alerts</p>
        <button onClick={onMarkAllRead} style={{ color: c.cyan }} className="text-xs font-medium">Mark all as read</button>
      </div>
      <div style={{ background: c.card, border: "1px solid " + c.border }} className="flex rounded-xl p-1 mb-5">
        <button onClick={() => setFilter("all")} style={{ background: filter === "all" ? c.cardAlt : "transparent", color: filter === "all" ? c.text : c.textSecondary }} className="flex-1 text-sm font-medium py-2 rounded-lg">All ({alerts.length})</button>
        <button onClick={() => setFilter("unread")} style={{ background: filter === "unread" ? c.cardAlt : "transparent", color: filter === "unread" ? c.text : c.textSecondary }} className="flex-1 text-sm font-medium py-2 rounded-lg">Unread ({unreadCount})</button>
      </div>
      <div className="flex flex-col gap-3">
        {filtered.map((a) => <AlertRow key={a.id} a={a} />)}
        {filtered.length === 0 && <p style={{ color: c.textSecondary }} className="text-sm text-center py-10">Nothing to show here.</p>}
      </div>
    </PageShell>
  );
}

function SettingsPage({ onNavigate, unreadCount, entitled, subscription, onSimulateUpgrade, onSimulateDowngrade, onSimulateStatus }) {
  const [defaultStake, setDefaultStake] = useState("100");
  const [defaultCommission, setDefaultCommission] = useState("2");
  const [riskThreshold, setRiskThreshold] = useState("5");
  const [alertPrefs, setAlertPrefs] = useState(ALERT_PREFS.reduce((acc, label) => ({ ...acc, [label]: true }), {}));

  return (
    <PageShell activeTab="menu" onNavigate={onNavigate} unreadCount={unreadCount}>
      <PageHeader onNavigate={onNavigate} unreadCount={unreadCount} />
      <p style={{ color: c.text }} className="text-xl font-medium mb-5">Settings</p>

      <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-2xl p-4 mb-5 flex items-center gap-3">
        <div style={{ background: c.cardAlt, border: "1px solid " + c.border }} className="w-11 h-11 rounded-full flex items-center justify-center flex-shrink-0">
          <span style={{ color: c.textSecondary }} className="text-sm">JD</span>
        </div>
        <div className="flex-1 min-w-0">
          <p style={{ color: c.text }} className="text-sm font-medium truncate">John Doe</p>
          <p style={{ color: c.textSecondary }} className="text-xs truncate">john@example.com</p>
        </div>
        <span
          style={{ background: entitled ? c.greenDark : c.cardAlt, color: entitled ? c.green : c.textSecondary, border: entitled ? "none" : "1px solid " + c.border }}
          className="text-xs font-medium px-2 py-1 rounded-full flex-shrink-0"
        >
          {entitled ? "Pro" : "Free"}
        </span>
      </div>

      <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide mb-2">Account</p>
      <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl px-4 mb-5">
        <SettingsRow icon={User} label="Profile" />
        <SettingsRow
          icon={CreditCard}
          label="Manage subscription"
          value={entitled ? "Pro" : "Free"}
          tone={entitled ? c.green : c.textSecondary}
          onClick={entitled ? onSimulateDowngrade : onSimulateUpgrade}
        />
        <div className="px-1 pb-3 pt-1">
          <p style={{ color: subscriptionStatusText(subscription).tone }} className="text-xs">
            {subscriptionStatusText(subscription).text}
          </p>
        </div>
        <div className="px-1 pb-3">
          <p style={{ color: c.textSecondary }} className="text-xs mb-2">Simulate status (demo only):</p>
          <div className="flex gap-2 flex-wrap">
            {["active", "cancelled", "billing_issue", "expired"].map((s) => (
              <button
                key={s}
                onClick={() => onSimulateStatus(s)}
                style={{ background: c.cardAlt, border: "1px solid " + c.border, color: c.textSecondary }}
                className="text-xs px-2 py-1 rounded-full"
              >
                {s.replace("_", " ")}
              </button>
            ))}
          </div>
        </div>
        <SettingsRow icon={Shield} label="Privacy & security" />
      </div>

      <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide mb-2">Trading preferences</p>
      <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4 mb-5 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <span style={{ color: c.text }} className="text-sm">Default stake</span>
          <div className="flex items-center gap-1">
            <span style={{ color: c.textSecondary }} className="text-sm">£</span>
            <input type="number" value={defaultStake} placeholder="0" onChange={(e) => setDefaultStake(e.target.value)} style={{ background: "transparent", color: c.text, width: 60 }} className="text-sm text-right" />
          </div>
        </div>
        <div className="flex items-center justify-between">
          <span style={{ color: c.text }} className="text-sm">Default commission</span>
          <div className="flex items-center gap-1">
            <input type="number" value={defaultCommission} placeholder="0" onChange={(e) => setDefaultCommission(e.target.value)} style={{ background: "transparent", color: c.text, width: 40 }} className="text-sm text-right" />
            <span style={{ color: c.textSecondary }} className="text-sm">%</span>
          </div>
        </div>
        <div className="flex items-center justify-between">
          <span style={{ color: c.text }} className="text-sm">Risk warning threshold</span>
          <div className="flex items-center gap-1">
            <input type="number" value={riskThreshold} placeholder="0" onChange={(e) => setRiskThreshold(e.target.value)} style={{ background: "transparent", color: c.text, width: 40 }} className="text-sm text-right" />
            <span style={{ color: c.textSecondary }} className="text-sm">% of bankroll</span>
          </div>
        </div>
      </div>

      <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide mb-2">Notifications</p>
      <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4 mb-5 flex flex-col gap-4">
        {ALERT_PREFS.map((label) => (
          <div key={label} className="flex items-center justify-between">
            <span style={{ color: c.text }} className="text-sm">{label}</span>
            <Toggle on={alertPrefs[label]} onChange={(val) => setAlertPrefs({ ...alertPrefs, [label]: val })} />
          </div>
        ))}
      </div>

      <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl px-4 mb-5">
        <SettingsRow icon={LogOut} label="Log out" tone={c.red} />
      </div>

      <p style={{ color: c.textSecondary }} className="text-xs text-center">TurnaroundIQ v1.0.0</p>
    </PageShell>
  );
}

// ============================================================
// APP ROOT -- owns navigation state and the single modal instance
// ============================================================
export default function App() {
  const [page, setPage] = useState("dashboard");
  const [selectedOpportunity, setSelectedOpportunity] = useState(null);
  const [alerts, setAlerts] = useState(INITIAL_ALERTS);

  // Stands in for the real `entitled` field from GET /me. In production
  // this is set once on app load from that call, then refreshed after
  // any purchase -- never toggled directly by the UI like this. See the
  // REVENUECAT INTEGRATION NOTES comment above the Paywall component.
  // Mirrors the real subscribers row shape from get_subscriber_row() in
  // revenuecat.py: { entitled, entitlement, status, expires_at,
  // product_id, environment }. Status values match apply_webhook()
  // exactly: active, expired, cancelled, billing_issue, refund, revoke,
  // unknown. In production this is set once from GET /me and refreshed
  // after any purchase -- never simulated like this. See the
  // REVENUECAT INTEGRATION NOTES comment above the Paywall component.
  const [subscription, setSubscription] = useState({
    entitled: true,
    entitlement: "pro",
    status: "active",
    expires_at: "2026-10-15T00:00:00Z",
    product_id: "pro_monthly",
  });
  const entitled = subscription.entitled;
  const simulateUpgrade = () =>
    setSubscription({ entitled: true, entitlement: "pro", status: "active", expires_at: "2026-10-15T00:00:00Z", product_id: "pro_monthly" });
  const simulateDowngrade = () =>
    setSubscription({ entitled: false, entitlement: null, status: "expired", expires_at: null, product_id: null });
  const simulateStatus = (status) => {
    // Cancelled/billing_issue stay entitled until expiry, matching
    // apply_webhook(): entitled = _not_expired(expires_at) for these.
    const entitledStates = { active: true, cancelled: true, billing_issue: true, expired: false, refund: false, revoke: false };
    setSubscription({
      entitled: entitledStates[status],
      entitlement: entitledStates[status] ? "pro" : null,
      status,
      expires_at: entitledStates[status] ? "2026-10-15T00:00:00Z" : null,
      product_id: entitledStates[status] ? "pro_monthly" : null,
    });
  };

  const unreadCount = alerts.filter((a) => a.unread).length;
  const markAllRead = () => setAlerts(alerts.map((a) => ({ ...a, unread: false })));

  const pages = {
    dashboard: <DashboardPage onNavigate={setPage} onOpenOpportunity={setSelectedOpportunity} unreadCount={unreadCount} />,
    opportunities: <OpportunitiesPage onNavigate={setPage} onOpenOpportunity={setSelectedOpportunity} unreadCount={unreadCount} entitled={entitled} onSimulateUpgrade={simulateUpgrade} />,
    "early-goal-hunter": <EarlyGoalHunterPage onNavigate={setPage} unreadCount={unreadCount} />,
    "chaos-factor": <ChaosFactorPage onNavigate={setPage} unreadCount={unreadCount} />,
    "model-testing": <ModelTestingPage onNavigate={setPage} unreadCount={unreadCount} />,
    live: <LiveMonitorPage onNavigate={setPage} unreadCount={unreadCount} />,
    bets: <MyBetsPage onNavigate={setPage} unreadCount={unreadCount} />,
    calculator: <CalculatorPage onNavigate={setPage} unreadCount={unreadCount} />,
    alerts: <AlertsPage onNavigate={setPage} alerts={alerts} onMarkAllRead={markAllRead} />,
    settings: <SettingsPage onNavigate={setPage} unreadCount={unreadCount} entitled={entitled} subscription={subscription} onSimulateUpgrade={simulateUpgrade} onSimulateDowngrade={simulateDowngrade} onSimulateStatus={simulateStatus} />,
  };

  return (
    <>
      {pages[page]}
      <OpportunityDetailModal opportunity={selectedOpportunity} onClose={() => setSelectedOpportunity(null)} />
    </>
  );
}
