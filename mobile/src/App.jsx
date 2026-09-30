import React, { useCallback, useEffect, useMemo, useState } from "react";
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
  ChevronRight,
  Home,
  Rocket,
  RadioTower,
  Wallet,
  Menu,
  X,
  Calculator,
  Settings,
  Bookmark,
  ArrowUpRight,
  ArrowDownRight,
  RotateCcw,
  User,
  CreditCard,
  Shield,
  Lock,
  Crosshair,
  Flame,
  FlaskConical,
  RefreshCw,
  Info,
} from "lucide-react";

import { LOGO_SRC } from "./logo";
import { api, API_BASE, ApiError } from "./lib/api";
import {
  getPackages,
  initPurchases,
  manageSubscription,
  onCustomerInfoChange,
  purchase,
  purchasesAvailable,
  restore,
} from "./lib/purchases";

const SHOW_DEV_TOOLS = import.meta.env.VITE_SHOW_DEV_TOOLS === "true";
const TERMS_URL = import.meta.env.VITE_TERMS_URL || "";
const PRIVACY_URL = import.meta.env.VITE_PRIVACY_URL || "";

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

// ============================================================
// SHARED CALCULATIONS -- ported 1:1 from calculations.py.
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
  return stake * (backOdds - 1) - (layOdds - 1) * layStake;
}
function calcFtaProfit(stake, backOdds, layStake, commission) {
  return stake * backOdds + layStake * (1 - commission / 100) - stake;
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
function calcLayStakeSNR(backOdds, layOdds, freeBetStake, commission) {
  const denom = layOdds - commission / 100;
  if (denom <= 0) return 0;
  return ((backOdds - 1) * freeBetStake) / denom;
}
function calcLayStakeSR(backOdds, layOdds, freeBetStake, commission) {
  return calcLayStake(backOdds, layOdds, freeBetStake, commission);
}

// ============================================================
// DATA HOOK -- loading / error / paywall states for every API call
// ============================================================
function useApi(loader, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null, needsPro: false });
  const load = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null, needsPro: false }));
    try {
      setState({ data: await loader(), loading: false, error: null, needsPro: false });
    } catch (e) {
      const needsPro = e instanceof ApiError && e.needsPro;
      setState({ data: null, loading: false, error: needsPro ? null : e.message, needsPro });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => {
    load();
  }, [load]);
  return { ...state, reload: load };
}

// ============================================================
// HELPERS
// ============================================================
function ordinalSuffix(day) {
  if (day >= 11 && day <= 13) return "th";
  switch (day % 10) {
    case 1: return "st";
    case 2: return "nd";
    case 3: return "rd";
    default: return "th";
  }
}
function formatKickoff(iso) {
  if (!iso) return "TBC";
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(iso);
  const d = dateOnly ? new Date(iso + "T12:00:00") : new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const day = d.getDate();
  const month = d.toLocaleString("en-GB", { month: "long" });
  if (dateOnly) return day + ordinalSuffix(day) + " " + month;
  const hours = d.getHours() % 12 || 12;
  const minutes = String(d.getMinutes()).padStart(2, "0");
  return day + ordinalSuffix(day) + " " + month + " - " + hours + ":" + minutes;
}
const pct = (v, dp = 1) => (v == null || isNaN(v) ? "—" : Number(v).toFixed(dp) + "%");
const money = (v) => (v == null || isNaN(v) ? "—" : (v >= 0 ? "£" : "-£") + Math.abs(v).toFixed(2));
const oppKey = (o) => `${o.match}|${o.team}`;

// confidence = how much match history backs the pick (0-100), not a probability
function depthLabel(score) {
  if (score >= 80) return { label: "Deep data", tone: c.green };
  if (score >= 60) return { label: "Good data", tone: c.orange };
  return { label: "Thin data", tone: c.textSecondary };
}

function resultTone(result) {
  if (result === "fta" || result === "won") return c.green;
  if (result === "no_fta" || result === "lost") return c.red;
  return c.textSecondary;
}
function resultLabel(result) {
  const labels = { fta: "FTA hit", no_fta: "No FTA", won: "Hit", lost: "Miss", void: "Void" };
  return labels[result] || result || "Open";
}

// ============================================================
// LAYOUT
// ============================================================
function PageHeader({ onNavigate, entitled }) {
  return (
    <div className="flex items-center justify-between mb-6">
      <button onClick={() => onNavigate("dashboard")} className="flex items-center gap-2">
        <img src={LOGO_SRC} alt="TurnaroundIQ logo" className="h-6 w-auto" />
        <span className="text-base font-medium">
          <span style={{ color: c.text }}>Turnaround</span>
          <span style={{ color: c.green }}>IQ</span>
        </span>
      </button>
      <span
        style={{
          background: entitled ? c.greenDark : c.cardAlt,
          color: entitled ? c.green : c.textSecondary,
          border: entitled ? "none" : "1px solid " + c.border,
        }}
        className="text-xs font-medium px-2 py-1 rounded-full"
      >
        {entitled ? "Pro" : "Free"}
      </span>
    </div>
  );
}

function BottomNav({ activeTab, onNavigate }) {
  const [open, setOpen] = useState(false);
  const navItems = [
    { key: "dashboard", icon: Home },
    { key: "opportunities", icon: Rocket },
    { key: "live", icon: RadioTower },
    { key: "bets", icon: Wallet },
  ];
  const flyoutItems = [
    ...(SHOW_DEV_TOOLS ? [{ key: "model-testing", icon: FlaskConical, label: "Model Testing (dev)", tone: c.cyan }] : []),
    { key: "early-goal-hunter", icon: Crosshair, label: "Early Goal Hunter", tone: c.orange },
    { key: "chaos-factor", icon: Flame, label: "Chaos Factor", tone: c.red },
    { key: "calculator", icon: Calculator, label: "Calculator", tone: c.cyan },
    { key: "settings", icon: Settings, label: "Settings", tone: c.textSecondary },
  ];
  const go = (key) => {
    setOpen(false);
    onNavigate(key);
  };
  return (
    <div className="fixed bottom-0 left-0 right-0 flex justify-center pb-4 px-4" style={{ paddingBottom: "calc(1rem + env(safe-area-inset-bottom))" }}>
      <div className="w-full max-w-[420px]">
        {open && (
          <div style={{ background: c.cardAlt, border: "1px solid " + c.border }} className="rounded-2xl p-2 mb-2">
            {flyoutItems.map(({ key, icon: Icon, label, tone }) => (
              <button key={key} onClick={() => go(key)} className="w-full flex items-center gap-3 px-3 py-3 text-left">
                <Icon size={20} style={{ color: tone }} />
                <span style={{ color: c.text }} className="text-sm">{label}</span>
              </button>
            ))}
          </div>
        )}
        <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-2xl flex items-center justify-between px-7 py-4">
          {navItems.map(({ key, icon: Icon }) => (
            <button key={key} aria-label={key} onClick={() => go(key)}>
              <Icon size={22} style={{ color: !open && key === activeTab ? c.green : c.textSecondary }} />
            </button>
          ))}
          <button aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen(!open)}>
            {open ? <X size={22} style={{ color: c.green }} /> : <Menu size={22} style={{ color: activeTab === "menu" ? c.green : c.textSecondary }} />}
          </button>
        </div>
      </div>
    </div>
  );
}

function PageShell({ children, activeTab, onNavigate, entitled }) {
  return (
    <div style={{ background: c.bg, minHeight: "100vh" }} className="pb-32">
      <div className="max-w-[420px] mx-auto px-4 pt-6">
        <PageHeader onNavigate={onNavigate} entitled={entitled} />
        {children}
      </div>
      <BottomNav activeTab={activeTab} onNavigate={onNavigate} />
    </div>
  );
}

// ============================================================
// SMALL COMPONENTS
// ============================================================
function Disclaimer() {
  return (
    <p style={{ color: c.textSecondary }} className="text-[11px] leading-snug text-center mt-6">
      TurnaroundIQ is a football intelligence tool. Percentages are estimates from historical
      data — not predictions, tips or guaranteed profit. Betting involves risk; only stake what you
      can afford to lose. 18+ · BeGambleAware.org
    </p>
  );
}

function Loading() {
  return <p style={{ color: c.textSecondary }} className="text-sm text-center py-8">Loading…</p>;
}

function ErrorBox({ error, onRetry }) {
  return (
    <div style={{ background: c.card, border: "1px solid " + c.red }} className="rounded-xl p-4 mb-4">
      <p style={{ color: c.red }} className="text-sm font-medium mb-1">Couldn't load this</p>
      <p style={{ color: c.textSecondary }} className="text-xs">{error}</p>
      {onRetry && (
        <button onClick={onRetry} style={{ color: c.cyan }} className="text-xs font-medium mt-2 flex items-center gap-1">
          <RefreshCw size={12} /> Try again
        </button>
      )}
    </div>
  );
}

function Empty({ children }) {
  return <p style={{ color: c.textSecondary }} className="text-sm text-center py-10">{children}</p>;
}

function KpiCard({ label, value, tone }) {
  return (
    <div style={{ background: c.card, border: "1px solid " + c.border }} className="flex-shrink-0 rounded-xl px-4 py-3 min-w-[110px]">
      <p style={{ color: c.textSecondary }} className="text-xs mb-1">{label}</p>
      <p style={{ color: tone }} className="text-lg font-medium">{value}</p>
    </div>
  );
}

function StatBox({ label, value, tone }) {
  return (
    <div>
      <p style={{ color: c.textSecondary }} className="text-xs">{label}</p>
      <p style={{ color: tone || c.text }} className="text-sm font-medium">{value}</p>
    </div>
  );
}

// ============================================================
// PAYWALL -- real App Store / Play purchase via RevenueCat
// ============================================================
function Paywall({ title, onPurchased }) {
  const [packages, setPackages] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    getPackages().then(setPackages).catch(() => setPackages([]));
  }, []);

  const buy = async (pkg) => {
    setBusy(true);
    setMessage(null);
    try {
      if (await purchase(pkg)) await onPurchased();
    } catch (e) {
      setMessage(e.message || "Purchase failed");
    } finally {
      setBusy(false);
    }
  };
  const doRestore = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const pro = await restore();
      await onPurchased();
      if (!pro) setMessage("No active subscription found for this Apple / Google account.");
    } catch (e) {
      setMessage(e.message || "Restore failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-2xl p-6 text-center mt-4">
      <div style={{ background: c.greenDark }} className="w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-4">
        <Lock size={20} style={{ color: c.green }} />
      </div>
      <p style={{ color: c.text }} className="text-base font-medium mb-2">{title || "This is a Pro feature"}</p>
      <p style={{ color: c.textSecondary }} className="text-sm mb-5">
        Pro unlocks ranked FTA opportunities, Early Goal Hunter, Chaos Factor and your paper-tracking log.
      </p>

      {!purchasesAvailable && (
        <p style={{ color: c.textSecondary }} className="text-xs mb-3">
          Subscriptions are available in the iOS and Android app.
        </p>
      )}
      {purchasesAvailable && packages === null && <Loading />}
      {purchasesAvailable && packages && packages.length === 0 && (
        <p style={{ color: c.textSecondary }} className="text-xs mb-3">No subscription options available right now.</p>
      )}
      {packages &&
        packages.map((pkg) => (
          <button
            key={pkg.identifier}
            disabled={busy}
            onClick={() => buy(pkg)}
            style={{ background: c.green, color: c.greenDark, opacity: busy ? 0.6 : 1 }}
            className="w-full rounded-xl py-3 text-sm font-medium mb-2"
          >
            {pkg.product?.title || "Upgrade to Pro"} — {pkg.product?.priceString}
          </button>
        ))}
      {purchasesAvailable && (
        <button disabled={busy} onClick={doRestore} style={{ color: c.cyan }} className="text-xs font-medium mt-1">
          Restore purchases
        </button>
      )}
      {message && <p style={{ color: c.orange }} className="text-xs mt-3">{message}</p>}
      <p style={{ color: c.textSecondary }} className="text-[11px] mt-4">
        Subscriptions renew automatically until cancelled in your App Store / Google Play settings.
        {TERMS_URL && <> · <a href={TERMS_URL} style={{ color: c.cyan }}>Terms</a></>}
        {PRIVACY_URL && <> · <a href={PRIVACY_URL} style={{ color: c.cyan }}>Privacy</a></>}
      </p>
    </div>
  );
}

// ============================================================
// OPPORTUNITIES (FTA)
// fta_pct = chance the team goes 2 up AND fails to win (full event)
// ============================================================
function OpportunityCard({ o, onClick, wide }) {
  const depth = depthLabel(o.confidence);
  return (
    <button
      onClick={() => onClick(o)}
      style={{ background: c.card, border: "1px solid " + c.border, textAlign: "left" }}
      className={"rounded-xl p-4 flex flex-col gap-3 " + (wide ? "w-full" : "w-[260px] flex-shrink-0")}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p style={{ color: c.textSecondary }} className="text-xs mb-1 truncate">
            {formatKickoff(o.kickoff)}{wide ? " · " + o.league : ""}
          </p>
          <p style={{ color: c.text }} className="text-sm font-medium leading-snug truncate">{o.home_team}</p>
          <p style={{ color: c.textSecondary }} className="text-sm leading-snug truncate">vs {o.away_team}</p>
          <p style={{ color: c.cyan }} className="text-xs mt-1 truncate">Team: {o.team}</p>
        </div>
        <div className="text-right flex-shrink-0">
          <p style={{ color: c.green }} className="text-lg font-medium">{pct(o.fta_pct, 2)}</p>
          <p style={{ color: c.textSecondary }} className="text-xs">FTA chance</p>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div><p style={{ color: c.textSecondary }} className="text-xs">Goes 2 up</p><p style={{ color: c.text }} className="text-sm font-medium">{pct(o.two_up_pct, 0)}</p></div>
        <div><p style={{ color: c.textSecondary }} className="text-xs">Then fails</p><p style={{ color: c.text }} className="text-sm font-medium">{pct(o.fail_given_2up_pct ?? o.turnaround_pct, 1)}</p></div>
        <div><p style={{ color: c.textSecondary }} className="text-xs">Usual 2-up</p><p style={{ color: c.text }} className="text-sm font-medium">{o.usual_2up_minute ? Math.round(o.usual_2up_minute) + "'" : "—"}</p></div>
      </div>
      <div className="flex items-center justify-between">
        <span style={{ color: depth.tone }} className="text-xs font-medium">{depth.label}</span>
        <span style={{ color: c.cyan }} className="flex items-center gap-1 text-xs font-medium">Analysis <ChevronRight size={14} /></span>
      </div>
    </button>
  );
}

function OpportunityDetailModal({ opportunity, onClose, prefs }) {
  const [stake, setStake] = useState("");
  const [backOdds, setBackOdds] = useState("");
  const [layOdds, setLayOdds] = useState("");
  const [commission, setCommission] = useState("");
  const [lastKey, setLastKey] = useState(null);
  const [trackState, setTrackState] = useState(null);

  if (opportunity && oppKey(opportunity) !== lastKey) {
    setLastKey(oppKey(opportunity));
    setBackOdds(String(opportunity.back_odds ?? ""));
    setLayOdds(String(opportunity.lay_odds ?? ""));
    setCommission(String(prefs?.default_commission ?? opportunity.commission ?? 2));
    setStake(String(prefs?.default_stake ?? 40));
    setTrackState(null);
  }
  if (!opportunity) return null;
  const o = opportunity;
  const depth = depthLabel(o.confidence);

  const stakeNum = parseFloat(stake) || 0;
  const backNum = parseFloat(backOdds) || 0;
  const layNum = parseFloat(layOdds) || 0;
  const commNum = parseFloat(commission) || 0;
  const layStake = calcLayStake(backNum, layNum, stakeNum, commNum);
  const ql = calcQualifyingLoss(backNum, layNum, stakeNum, layStake);
  const ftaProfit = calcFtaProfit(stakeNum, backNum, layStake, commNum);
  const expected = calcExpectedProfit(ftaProfit, ql, o.fta_pct);
  const ev = calcEvPercent(expected, ql);
  const pricesEdited = String(o.back_odds) !== backOdds || String(o.lay_odds) !== layOdds;
  const estimated = o.odds_estimated && !pricesEdited;

  const track = async () => {
    setTrackState("saving");
    try {
      await api.track({
        match_id: o.match_id, league: o.league, kickoff: o.kickoff,
        home_team: o.home_team, away_team: o.away_team, team: o.team,
        is_home: o.team === o.home_team, bookmaker: o.bookmaker || "Paper",
        back_odds: backNum, lay_odds: layNum, stake: stakeNum, commission: commNum,
        lay_stake: Number(layStake.toFixed(2)), liability: Number(calcLiability(layNum, layStake).toFixed(2)),
        fta_pct: o.fta_pct, score_with_model: false, paper: true, product: "fta",
      });
      setTrackState("saved");
    } catch (e) {
      setTrackState(e.message || "Couldn't save");
    }
  };

  return (
    <div style={{ background: "rgba(0,0,0,0.6)" }} className="fixed inset-0 z-50 flex items-end justify-center" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: c.bg, border: "1px solid " + c.border }} className="w-full max-w-[420px] max-h-[85vh] overflow-y-auto rounded-t-2xl p-5">
        <div className="flex justify-between items-center mb-3">
          <div style={{ background: c.border }} className="w-10 h-1 rounded-full mx-auto" />
          <button aria-label="Close" onClick={onClose} style={{ background: c.card, border: "1px solid " + c.border }} className="w-8 h-8 rounded-full flex items-center justify-center">
            <X size={16} style={{ color: c.textSecondary }} />
          </button>
        </div>

        <div className="flex items-center justify-between mb-3">
          <span style={{ color: c.textSecondary }} className="text-sm">{formatKickoff(o.kickoff)}</span>
          <span style={{ color: c.textSecondary }} className="text-sm">{o.league}</span>
        </div>
        <p style={{ color: c.text }} className="text-sm font-medium">{o.home_team} <span style={{ color: c.textSecondary }}>vs</span> {o.away_team}</p>
        <p style={{ color: c.cyan }} className="text-xs mb-4">Team to go 2 up: {o.team}</p>

        <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide mb-2">Model probabilities</p>
        <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-3 grid grid-cols-3 gap-2 text-center mb-2">
          <div><p style={{ color: c.textSecondary }} className="text-xs mb-1">Goes 2 up</p><p style={{ color: c.text }} className="text-base font-medium">{pct(o.two_up_pct)}</p></div>
          <div><p style={{ color: c.textSecondary }} className="text-xs mb-1">Then fails to win</p><p style={{ color: c.text }} className="text-base font-medium">{pct(o.fail_given_2up_pct ?? o.turnaround_pct)}</p></div>
          <div><p style={{ color: c.textSecondary }} className="text-xs mb-1">FTA (both)</p><p style={{ color: c.green }} className="text-base font-medium">{pct(o.fta_pct, 2)}</p></div>
        </div>
        <p style={{ color: depth.tone }} className="text-xs mb-4">{depth.label} — how much match history backs these numbers</p>

        <div className="flex items-center justify-between mb-2">
          <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide">Your prices</p>
          <span style={{ color: estimated ? c.orange : c.textSecondary }} className="text-xs">
            {estimated ? "estimated — enter real odds" : "editable"}
          </span>
        </div>
        <div style={{ background: c.card, border: "1px solid " + (estimated ? c.orange : c.border) }} className="rounded-xl p-3 grid grid-cols-3 gap-2 text-center mb-4">
          <div>
            <p style={{ color: c.textSecondary }} className="text-xs mb-1">Back (bookie)</p>
            <input type="number" inputMode="decimal" step="0.01" value={backOdds} onChange={(e) => setBackOdds(e.target.value)} style={{ background: "transparent", color: c.green, width: "100%" }} className="text-base font-medium text-center" />
          </div>
          <div>
            <p style={{ color: c.textSecondary }} className="text-xs mb-1">Lay (exchange)</p>
            <input type="number" inputMode="decimal" step="0.01" value={layOdds} onChange={(e) => setLayOdds(e.target.value)} style={{ background: "transparent", color: c.cyan, width: "100%" }} className="text-base font-medium text-center" />
          </div>
          <div>
            <p style={{ color: c.textSecondary }} className="text-xs mb-1">Commission %</p>
            <input type="number" inputMode="decimal" step="0.1" value={commission} onChange={(e) => setCommission(e.target.value)} style={{ background: "transparent", color: c.text, width: "100%" }} className="text-base font-medium text-center" />
          </div>
        </div>

        <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-3 flex items-center justify-between mb-4">
          <span style={{ color: c.textSecondary }} className="text-xs">Stake</span>
          <div className="flex items-center gap-2">
            <span style={{ color: c.text }} className="text-base font-medium">£</span>
            <input type="number" inputMode="decimal" step="1" value={stake} onChange={(e) => setStake(e.target.value)} style={{ background: "transparent", color: c.text, width: 70 }} className="text-base font-medium text-right" />
          </div>
        </div>

        <div style={{ background: c.cardAlt, border: "1px solid " + c.border }} className="rounded-xl p-3 grid grid-cols-2 gap-2 text-center mb-4">
          <div><p style={{ color: c.textSecondary }} className="text-xs mb-1">Lay stake</p><p style={{ color: c.cyan }} className="text-base font-medium">£{layStake.toFixed(2)}</p></div>
          <div><p style={{ color: c.textSecondary }} className="text-xs mb-1">Liability</p><p style={{ color: c.orange }} className="text-base font-medium">£{calcLiability(layNum, layStake).toFixed(2)}</p></div>
        </div>

        <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide mb-2">Outcomes</p>
        <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-3 mb-4 flex flex-col gap-3">
          <div className="flex items-center justify-between"><span style={{ color: c.textSecondary }} className="text-sm">Goes 2 up, then fails to win</span><span style={{ color: c.green }} className="text-sm font-medium">{money(ftaProfit)}</span></div>
          <div className="flex items-center justify-between"><span style={{ color: c.textSecondary }} className="text-sm">Any other result</span><span style={{ color: ql >= 0 ? c.green : c.red }} className="text-sm font-medium">{money(ql)}</span></div>
          <div style={{ borderTop: "1px solid " + c.border }} />
          <div className="flex items-center justify-between"><span style={{ color: c.textSecondary }} className="text-sm">Expected profit</span><span style={{ color: expected >= 0 ? c.green : c.red }} className="text-sm font-medium">{money(expected)} ({ev.toFixed(0)}% of risk)</span></div>
        </div>
        {estimated && (
          <p style={{ color: c.orange }} className="text-xs mb-3">
            These odds are placeholders — expected profit only means something with the real prices from your bookmaker and exchange.
          </p>
        )}

        <button disabled={trackState === "saving" || trackState === "saved"} onClick={track} style={{ background: c.green, color: c.greenDark, opacity: trackState === "saved" ? 0.6 : 1 }} className="w-full rounded-xl py-3 flex items-center justify-center gap-2 text-sm font-medium">
          <Bookmark size={16} /> {trackState === "saved" ? "Tracked in My Bets" : trackState === "saving" ? "Saving…" : "Track (paper)"}
        </button>
        {trackState && !["saving", "saved"].includes(trackState) && <p style={{ color: c.red }} className="text-xs text-center mt-2">{trackState}</p>}
        <Disclaimer />
      </div>
    </div>
  );
}

// ============================================================
// PAGES
// ============================================================
function DashboardPage({ nav, entitled, me, opps, onOpen, onPurchased }) {
  const paper = me?.paper || null;
  const list = opps.data?.opportunities || [];
  const top = list[0];
  const avgFta = list.length ? list.reduce((s, o) => s + (o.fta_pct || 0), 0) / list.length : null;
  const leagues = {};
  list.forEach((o) => {
    (leagues[o.league] = leagues[o.league] || []).push(o.fta_pct || 0);
  });
  const topLeague = Object.entries(leagues)
    .map(([lg, v]) => [lg, v.reduce((a, b) => a + b, 0) / v.length])
    .sort((a, b) => b[1] - a[1])[0];

  if (!entitled) {
    return (
      <PageShell activeTab="dashboard" onNavigate={nav} entitled={entitled}>
        <p style={{ color: c.text }} className="text-xl font-medium mb-1">Welcome to TurnaroundIQ</p>
        <p style={{ color: c.textSecondary }} className="text-sm">
          Football intelligence for 2-up offers: the chance a team goes two goals up and still fails to win,
          plus early-goal and chaos signals across 25 leagues.
        </p>
        <Paywall title="Unlock TurnaroundIQ Pro" onPurchased={onPurchased} />
        <Disclaimer />
      </PageShell>
    );
  }

  return (
    <PageShell activeTab="dashboard" onNavigate={nav} entitled={entitled}>
      <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-2xl p-5 mb-6">
        <p style={{ color: c.textSecondary }} className="text-xs mb-1">Paper profit (tracked bets)</p>
        <p style={{ color: (paper?.total_profit || 0) >= 0 ? c.text : c.red }} className="text-3xl font-medium mb-4">{money(paper?.total_profit || 0)}</p>
        <div className="grid grid-cols-3 gap-3">
          <StatBox label="Open" value={String(paper?.open ?? 0)} />
          <StatBox label="Settled" value={String(paper?.settled ?? 0)} />
          <StatBox label="ROI" value={paper?.roi_pct == null ? "—" : pct(paper.roi_pct)} tone={(paper?.roi_pct || 0) >= 0 ? c.green : c.red} />
        </div>
      </div>

      <div className="flex gap-3 overflow-x-auto mb-6 -mx-1 px-1">
        <KpiCard label="Top FTA" value={top ? pct(top.fta_pct, 2) : "—"} tone={c.green} />
        <KpiCard label="Average FTA" value={avgFta == null ? "—" : pct(avgFta, 2)} tone={c.cyan} />
        <KpiCard label="Opportunities" value={String(list.length)} tone={c.text} />
      </div>

      <div className="flex items-center justify-between mb-3">
        <p style={{ color: c.text }} className="text-base font-medium">Top opportunities</p>
        <button onClick={() => nav("opportunities")} style={{ color: c.cyan }} className="text-xs font-medium">View all</button>
      </div>
      {opps.loading && <Loading />}
      {opps.error && <ErrorBox error={opps.error} onRetry={opps.reload} />}
      {!opps.loading && !opps.error && list.length === 0 && <Empty>No upcoming fixtures right now.</Empty>}
      <div className="flex gap-3 overflow-x-auto mb-6 -mx-1 px-1">
        {list.slice(0, 4).map((o) => <OpportunityCard key={oppKey(o)} o={o} onClick={onOpen} />)}
      </div>

      <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-2xl p-5">
        <p style={{ color: c.text }} className="text-sm font-medium mb-4">Snapshot</p>
        <div className="grid grid-cols-2 gap-4">
          <StatBox label="Highest-rated league" value={topLeague ? topLeague[0] : "—"} />
          <StatBox label="Top pick" value={top ? top.team : "—"} />
          <StatBox label="Paper staked" value={money(paper?.staked || 0)} />
          <StatBox label="FTA hits (paper)" value={String(paper?.fta_hits ?? 0)} tone={c.green} />
        </div>
      </div>
      <Disclaimer />
    </PageShell>
  );
}

function OpportunitiesPage({ nav, entitled, opps, onOpen, onPurchased }) {
  const [league, setLeague] = useState("All leagues");
  const list = opps.data?.opportunities || [];
  const leagues = ["All leagues", ...Array.from(new Set(list.map((o) => o.league).filter(Boolean))).sort()];
  const filtered = list.filter((o) => league === "All leagues" || o.league === league);

  return (
    <PageShell activeTab="opportunities" onNavigate={nav} entitled={entitled}>
      <p style={{ color: c.text }} className="text-xl font-medium mb-1">Opportunities</p>
      <p style={{ color: c.textSecondary }} className="text-sm mb-4">
        Ranked by FTA chance: the team goes 2 goals up <i>and</i> fails to win. Average is about 2%.
      </p>
      {(opps.needsPro || !entitled) && <Paywall title="Opportunities is a Pro feature" onPurchased={onPurchased} />}
      {entitled && opps.loading && <Loading />}
      {entitled && opps.error && <ErrorBox error={opps.error} onRetry={opps.reload} />}
      {entitled && opps.data && (
        <>
          <div className="flex gap-2 overflow-x-auto mb-5 -mx-1 px-1">
            {leagues.map((lg) => {
              const active = lg === league;
              return (
                <button key={lg} onClick={() => setLeague(lg)} style={{ background: active ? c.green : c.card, border: "1px solid " + (active ? c.green : c.border), color: active ? c.greenDark : c.textSecondary }} className="flex-shrink-0 text-xs font-medium px-3 py-2 rounded-full whitespace-nowrap">
                  {lg}
                </button>
              );
            })}
          </div>
          <div className="flex flex-col gap-3">
            {filtered.map((o) => <OpportunityCard key={oppKey(o)} o={o} onClick={onOpen} wide />)}
            {filtered.length === 0 && <Empty>No opportunities match this filter right now.</Empty>}
          </div>
        </>
      )}
      <Disclaimer />
    </PageShell>
  );
}

function hunterTone(score) {
  if (score >= 80) return c.green;
  if (score >= 55) return c.orange;
  return c.textSecondary;
}

function EarlyGoalHunterPage({ nav, entitled, onPurchased }) {
  const q = useApi(() => api.earlyGoal(), [entitled]);
  const ranked = [...(q.data?.matches || [])].sort((a, b) => b.hunter_score - a.hunter_score);
  return (
    <PageShell activeTab="menu" onNavigate={nav} entitled={entitled}>
      <p style={{ color: c.text }} className="text-xl font-medium mb-1">Early Goal Hunter</p>
      <p style={{ color: c.textSecondary }} className="text-sm mb-4">Fixtures most likely to see an early goal. A separate signal from FTA.</p>
      {q.needsPro && <Paywall onPurchased={onPurchased} />}
      {q.loading && <Loading />}
      {q.error && <ErrorBox error={q.error} onRetry={q.reload} />}
      {q.data && ranked.length === 0 && <Empty>No fixtures right now.</Empty>}
      <div className="flex flex-col gap-3">
        {ranked.map((f) => (
          <div key={f.match_id || f.match} style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4 flex flex-col gap-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p style={{ color: c.textSecondary }} className="text-xs mb-1 truncate">{formatKickoff(f.kickoff)} · {f.league}</p>
                <p style={{ color: c.text }} className="text-sm font-medium truncate">{f.home_team}</p>
                <p style={{ color: c.textSecondary }} className="text-sm truncate">vs {f.away_team}</p>
              </div>
              <div className="text-right flex-shrink-0">
                <p style={{ color: hunterTone(f.hunter_score) }} className="text-lg font-medium">{Number(f.hunter_score).toFixed(0)}</p>
                <p style={{ color: c.textSecondary }} className="text-xs">Hunter score</p>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2 text-center">
              <div><p style={{ color: c.textSecondary }} className="text-xs">1H goal</p><p style={{ color: c.text }} className="text-sm font-medium">{(f.p_first_half_goal * 100).toFixed(0)}%</p></div>
              <div><p style={{ color: c.textSecondary }} className="text-xs">Home scores 1st</p><p style={{ color: c.cyan }} className="text-sm font-medium">{(f.p_home_scores_first * 100).toFixed(0)}%</p></div>
              <div><p style={{ color: c.textSecondary }} className="text-xs">Away scores 1st</p><p style={{ color: c.blue }} className="text-sm font-medium">{(f.p_away_scores_first * 100).toFixed(0)}%</p></div>
            </div>
          </div>
        ))}
      </div>
      <Disclaimer />
    </PageShell>
  );
}

const CHAOS_COLORS = { o2_5: c.cyan, btts: c.blue, early_goal: c.orange, instability: c.red };
const CHAOS_LABELS = { o2_5: "O2.5", btts: "BTTS", early_goal: "Early goal", instability: "Instability" };
function chaosLabelTone(label) {
  if (label === "high") return c.red;
  if (label === "medium") return c.orange;
  return c.cyan;
}

function ChaosFactorPage({ nav, entitled, onPurchased }) {
  const q = useApi(() => api.chaos(), [entitled]);
  const ranked = [...(q.data?.matches || [])].sort((a, b) => b.chaos_index - a.chaos_index);
  return (
    <PageShell activeTab="menu" onNavigate={nav} entitled={entitled}>
      <p style={{ color: c.text }} className="text-xl font-medium mb-1">Chaos Factor</p>
      <p style={{ color: c.textSecondary }} className="text-sm mb-4">Unpredictability: O2.5, BTTS, early goals and instability combined.</p>
      {q.needsPro && <Paywall onPurchased={onPurchased} />}
      {q.loading && <Loading />}
      {q.error && <ErrorBox error={q.error} onRetry={q.reload} />}
      {q.data && ranked.length === 0 && <Empty>No fixtures right now.</Empty>}
      <div className="flex flex-col gap-3">
        {ranked.map((f) => {
          const pieData = Object.entries(f.pie || f.components || {}).map(([key, value]) => ({ name: CHAOS_LABELS[key] || key, value, key }));
          return (
            <div key={f.match_id || f.match} style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4 flex flex-col gap-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p style={{ color: c.textSecondary }} className="text-xs mb-1 truncate">{formatKickoff(f.kickoff)} · {f.league}</p>
                  <p style={{ color: c.text }} className="text-sm font-medium truncate">{f.home_team}</p>
                  <p style={{ color: c.textSecondary }} className="text-sm truncate">vs {f.away_team}</p>
                </div>
                <div className="text-right flex-shrink-0">
                  <p style={{ color: chaosLabelTone(f.chaos_label) }} className="text-lg font-medium">{Number(f.chaos_index).toFixed(0)}</p>
                  <p style={{ color: chaosLabelTone(f.chaos_label) }} className="text-xs uppercase font-medium">{f.chaos_label}</p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div style={{ width: 90, height: 90 }} className="flex-shrink-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={22} outerRadius={40} paddingAngle={2}>
                        {pieData.map((e) => <Cell key={e.key} fill={CHAOS_COLORS[e.key] || c.textSecondary} stroke="none" />)}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="flex flex-col gap-1 flex-1">
                  {pieData.map((e) => (
                    <div key={e.key} className="flex items-center justify-between text-xs">
                      <span className="flex items-center gap-1.5" style={{ color: c.textSecondary }}>
                        <span style={{ background: CHAOS_COLORS[e.key] || c.textSecondary, width: 7, height: 7, borderRadius: "50%", display: "inline-block" }} />
                        {e.name}
                      </span>
                      <span style={{ color: c.text }} className="font-medium">{e.value}%</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <Disclaimer />
    </PageShell>
  );
}

function LiveMonitorPage({ nav, entitled }) {
  return (
    <PageShell activeTab="live" onNavigate={nav} entitled={entitled}>
      <p style={{ color: c.text }} className="text-xl font-medium mb-4">Live monitoring</p>
      <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-2xl p-6 text-center">
        <RadioTower size={28} style={{ color: c.cyan }} className="mx-auto mb-3" />
        <p style={{ color: c.text }} className="text-base font-medium mb-2">Coming soon</p>
        <p style={{ color: c.textSecondary }} className="text-sm">
          In-play tracking of your 2-up bets (live score, 2-up trigger, FTA status) is on the way.
          Your tracked bets settle automatically after full time in My Bets.
        </p>
      </div>
    </PageShell>
  );
}

function MyBetsPage({ nav, entitled, onPurchased, reloadMe }) {
  const [tab, setTab] = useState("open");
  const [showGraph, setShowGraph] = useState(false);
  const [settling, setSettling] = useState(false);
  const q = useApi(() => api.tracked(), [entitled]);
  const bets = q.data?.bets || [];
  const summary = q.data?.summary || {};
  const open = bets.filter((b) => b.status === "open");
  const settled = bets.filter((b) => b.status === "settled");

  const chartData = useMemo(() => {
    let run = 0;
    return [...settled]
      .sort((a, b) => String(a.settled_at).localeCompare(String(b.settled_at)))
      .map((b, i) => {
        run += Number(b.actual_profit || 0);
        return { index: i + 1, profit: Number(run.toFixed(2)) };
      });
  }, [settled]);

  const settleNow = async () => {
    setSettling(true);
    try {
      await api.autoSettle();
      await q.reload();
      reloadMe();
    } finally {
      setSettling(false);
    }
  };

  return (
    <PageShell activeTab="bets" onNavigate={nav} entitled={entitled}>
      <div className="flex items-center justify-between mb-4">
        <p style={{ color: c.text }} className="text-xl font-medium">My bets (paper)</p>
        {entitled && (
          <button onClick={settleNow} disabled={settling} style={{ color: c.cyan }} className="text-xs font-medium flex items-center gap-1">
            <RefreshCw size={12} /> {settling ? "Settling…" : "Settle finished"}
          </button>
        )}
      </div>
      {q.needsPro && <Paywall title="Paper tracking is a Pro feature" onPurchased={onPurchased} />}
      {q.loading && <Loading />}
      {q.error && <ErrorBox error={q.error} onRetry={q.reload} />}
      {q.data && (
        <>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <KpiCard label="Paper profit" value={money(summary.total_profit || 0)} tone={(summary.total_profit || 0) >= 0 ? c.green : c.red} />
            <KpiCard label="ROI" value={summary.roi_pct == null ? "—" : pct(summary.roi_pct)} tone={c.cyan} />
            <KpiCard label="Bets" value={String(summary.total ?? bets.length)} tone={c.text} />
            <KpiCard label="FTA hits" value={String(summary.fta_hits ?? 0)} tone={c.green} />
          </div>
          <button onClick={() => setShowGraph(!showGraph)} style={{ background: c.card, border: "1px solid " + c.border }} className="w-full rounded-xl px-4 py-3 flex items-center justify-between mb-3">
            <span style={{ color: c.text }} className="text-sm font-medium">Profit graph</span>
            <ChevronRight size={18} style={{ color: c.textSecondary, transform: showGraph ? "rotate(90deg)" : "none" }} />
          </button>
          {showGraph && (
            <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-3 mb-3">
              {chartData.length === 0 ? (
                <Empty>No settled bets yet.</Empty>
              ) : (
                <div style={{ height: 220 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 5, right: 8, left: -20, bottom: 0 }}>
                      <CartesianGrid stroke={c.border} strokeDasharray="3 3" />
                      <XAxis dataKey="index" stroke={c.textSecondary} tick={{ fontSize: 11 }} />
                      <YAxis stroke={c.textSecondary} tick={{ fontSize: 11 }} />
                      <Tooltip contentStyle={{ background: c.cardAlt, border: "1px solid " + c.border, borderRadius: 8 }} labelStyle={{ color: c.text }} formatter={(v) => ["£" + v.toFixed(2), "Profit"]} />
                      <Line type="monotone" dataKey="profit" stroke={c.green} strokeWidth={2} dot={{ r: 3 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          )}

          <div style={{ background: c.card, border: "1px solid " + c.border }} className="flex rounded-xl p-1 mb-5">
            <button onClick={() => setTab("open")} style={{ background: tab === "open" ? c.cardAlt : "transparent", color: tab === "open" ? c.text : c.textSecondary }} className="flex-1 text-sm font-medium py-2 rounded-lg">Open ({open.length})</button>
            <button onClick={() => setTab("settled")} style={{ background: tab === "settled" ? c.cardAlt : "transparent", color: tab === "settled" ? c.text : c.textSecondary }} className="flex-1 text-sm font-medium py-2 rounded-lg">Settled ({settled.length})</button>
          </div>
          <div className="flex flex-col gap-3">
            {(tab === "open" ? open : settled).map((b) => <BetRow key={b.id} b={b} />)}
            {(tab === "open" ? open : settled).length === 0 && (
              <Empty>{tab === "open" ? "No open bets. Track one from an opportunity." : "Nothing settled yet."}</Empty>
            )}
          </div>
        </>
      )}
      <Disclaimer />
    </PageShell>
  );
}

function BetRow({ b }) {
  const isOpen = b.status === "open";
  const tone = isOpen ? c.cyan : resultTone(b.result);
  const dateStr = (iso) => (iso ? new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");
  return (
    <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p style={{ color: c.textSecondary }} className="text-xs mb-1 truncate">{b.league || "—"} · {b.product === "fta" ? "FTA" : b.product}</p>
          <p style={{ color: c.text }} className="text-sm font-medium truncate">{b.match || `${b.home_team} vs ${b.away_team}`}</p>
          <p style={{ color: c.textSecondary }} className="text-xs truncate">Team: {b.team}</p>
        </div>
        <span style={{ color: tone, border: "1px solid " + tone }} className="text-xs font-medium px-2 py-0.5 rounded-full flex-shrink-0">{isOpen ? "Open" : resultLabel(b.result)}</span>
      </div>
      <div className="flex items-center justify-between text-sm">
        <span style={{ color: c.textSecondary }}>Stake £{Number(b.stake || 0).toFixed(2)} @ {b.back_odds ?? "—"}</span>
        <span style={{ color: isOpen ? c.textSecondary : tone }} className="font-medium">
          {isOpen ? (b.expected_profit != null ? "Exp. " + money(b.expected_profit) : "—") : money(Number(b.actual_profit || 0))}
        </span>
      </div>
      <p style={{ color: c.textSecondary }} className="text-xs">{isOpen ? "Opened " + dateStr(b.created_at) : "Settled " + dateStr(b.settled_at)}</p>
    </div>
  );
}

const CALC_MODES = [
  { key: "qualifying", label: "2UP bet" },
  { key: "snr", label: "Free bet (SNR)" },
  { key: "sr", label: "Free bet (SR)" },
];

function CalcField({ label, value, onChange, tone, prefix }) {
  return (
    <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-3">
      <p style={{ color: c.textSecondary }} className="text-xs mb-1">{label}</p>
      <div className="flex items-center gap-1">
        {prefix && <span style={{ color: tone || c.text }} className="text-lg font-medium">{prefix}</span>}
        <input type="number" inputMode="decimal" step="0.01" value={value} placeholder="0" onChange={(e) => onChange(e.target.value)} style={{ background: "transparent", color: tone || c.text, width: "100%" }} className="text-lg font-medium" />
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

function CalculatorPage({ nav, entitled, prefs }) {
  const defaults = {
    stake: String(prefs?.default_stake ?? 40), backOdds: "2.10", layOdds: "2.20",
    commission: String(prefs?.default_commission ?? 2), ftaPct: "2",
  };
  const [mode, setMode] = useState("qualifying");
  const [stake, setStake] = useState(defaults.stake);
  const [backOdds, setBackOdds] = useState(defaults.backOdds);
  const [layOdds, setLayOdds] = useState(defaults.layOdds);
  const [commission, setCommission] = useState(defaults.commission);
  const [ftaPct, setFtaPct] = useState(defaults.ftaPct);
  const reset = () => {
    setStake(defaults.stake); setBackOdds(defaults.backOdds); setLayOdds(defaults.layOdds);
    setCommission(defaults.commission); setFtaPct(defaults.ftaPct);
  };
  const s = parseFloat(stake) || 0, b = parseFloat(backOdds) || 0, l = parseFloat(layOdds) || 0;
  const cm = parseFloat(commission) || 0, f = parseFloat(ftaPct) || 0;

  let content;
  if (mode === "qualifying") {
    const ls = calcLayStake(b, l, s, cm);
    const ql = calcQualifyingLoss(b, l, s, ls);
    const fp = calcFtaProfit(s, b, ls, cm);
    const ep = calcExpectedProfit(fp, ql, f);
    content = (
      <>
        <div className="grid grid-cols-2 gap-3 mb-3">
          <CalcField label="Commission %" value={commission} onChange={setCommission} />
          <CalcField label="FTA chance %" value={ftaPct} onChange={setFtaPct} />
        </div>
        <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4 mb-4">
          <OutputRow label="Lay stake" value={"£" + ls.toFixed(2)} tone={c.cyan} />
          <OutputRow label="Liability" value={"£" + calcLiability(l, ls).toFixed(2)} tone={c.orange} />
          <OutputRow label="Qualifying loss" value={money(ql)} tone={ql >= 0 ? c.green : c.red} />
        </div>
        <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4">
          <OutputRow label="FTA profit (2 up, then fails)" value={money(fp)} tone={c.green} />
          <OutputRow label="Expected profit" value={money(ep)} tone={ep >= 0 ? c.green : c.red} />
          <OutputRow label="Expected value (of risk)" value={calcEvPercent(ep, ql).toFixed(1) + "%"} tone={ep >= 0 ? c.green : c.red} />
        </div>
      </>
    );
  } else {
    const ls = mode === "snr" ? calcLayStakeSNR(b, l, s, cm) : calcLayStakeSR(b, l, s, cm);
    const liab = calcLiability(l, ls);
    const ifBack = (mode === "snr" ? (b - 1) * s : b * s) - liab;
    const ifLay = ls * (1 - cm / 100);
    content = (
      <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4">
        <OutputRow label="Lay stake" value={"£" + ls.toFixed(2)} tone={c.cyan} />
        <OutputRow label="Liability" value={"£" + liab.toFixed(2)} tone={c.orange} />
        <OutputRow label="If back bet wins" value={money(ifBack)} tone={ifBack >= 0 ? c.green : c.red} />
        <OutputRow label="If lay bet wins" value={money(ifLay)} tone={ifLay >= 0 ? c.green : c.red} />
      </div>
    );
  }

  return (
    <PageShell activeTab="menu" onNavigate={nav} entitled={entitled}>
      <div className="flex items-center justify-between mb-4">
        <p style={{ color: c.text }} className="text-xl font-medium">Calculator</p>
        <button onClick={reset} style={{ color: c.textSecondary }} className="flex items-center gap-1 text-xs font-medium"><RotateCcw size={14} /> Reset</button>
      </div>
      <div className="flex gap-2 overflow-x-auto mb-5 -mx-1 px-1">
        {CALC_MODES.map((m) => {
          const active = m.key === mode;
          return (
            <button key={m.key} onClick={() => setMode(m.key)} style={{ background: active ? c.green : c.card, border: "1px solid " + (active ? c.green : c.border), color: active ? c.greenDark : c.textSecondary }} className="flex-shrink-0 text-xs font-medium px-3 py-2 rounded-full whitespace-nowrap">{m.label}</button>
          );
        })}
      </div>
      <div className="grid grid-cols-1 gap-3 mb-3">
        <CalcField label={mode === "qualifying" ? "Back stake" : "Free bet amount"} value={stake} onChange={setStake} prefix="£" />
      </div>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <CalcField label="Back odds (bookie)" value={backOdds} onChange={setBackOdds} tone={c.green} />
        <CalcField label="Lay odds (exchange)" value={layOdds} onChange={setLayOdds} tone={c.cyan} />
      </div>
      {mode !== "qualifying" && <div className="mb-3"><CalcField label="Commission %" value={commission} onChange={setCommission} /></div>}
      {content}
      <Disclaimer />
    </PageShell>
  );
}

function subscriptionStatusText(me) {
  const status = me?.status;
  if (!status || status === "free") return { text: "No active subscription", tone: c.textSecondary };
  const dateStr = me.expires_at ? new Date(me.expires_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : null;
  switch (status) {
    case "active": return { text: dateStr ? "Renews " + dateStr : "Active", tone: c.green };
    case "cancelled": return { text: "Cancelled — access until " + dateStr, tone: c.orange };
    case "billing_issue": return { text: "Payment problem — update it in your store account", tone: c.red };
    case "expired": return { text: "Expired", tone: c.red };
    case "refund":
    case "revoke": return { text: "Subscription revoked", tone: c.red };
    default: return { text: "Status unknown — contact support", tone: c.textSecondary };
  }
}

function SettingsPage({ nav, entitled, me, userId, onPurchased, reloadMe }) {
  const prefs = me?.prefs || {};
  const [stake, setStake] = useState(String(prefs.default_stake ?? 40));
  const [commission, setCommission] = useState(String(prefs.default_commission ?? 2));
  const [risk, setRisk] = useState(String(prefs.risk_warning_pct ?? 5));
  const [saved, setSaved] = useState(null);
  const [busy, setBusy] = useState(false);
  const status = subscriptionStatusText(me);

  const save = async () => {
    setSaved(null);
    try {
      await api.patchPrefs({
        default_stake: parseFloat(stake) || 0,
        default_commission: parseFloat(commission) || 0,
        risk_warning_pct: parseFloat(risk) || 0,
      });
      await reloadMe();
      setSaved("Saved");
    } catch (e) {
      setSaved(e.message || "Couldn't save");
    }
  };
  const doRestore = async () => {
    setBusy(true);
    try {
      await restore();
      await onPurchased();
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageShell activeTab="menu" onNavigate={nav} entitled={entitled}>
      <p style={{ color: c.text }} className="text-xl font-medium mb-5">Settings</p>

      <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-2xl p-4 mb-5 flex items-center gap-3">
        <div style={{ background: c.cardAlt, border: "1px solid " + c.border }} className="w-11 h-11 rounded-full flex items-center justify-center flex-shrink-0">
          <User size={18} style={{ color: c.textSecondary }} />
        </div>
        <div className="flex-1 min-w-0">
          <p style={{ color: c.text }} className="text-sm font-medium">{entitled ? "TurnaroundIQ Pro" : "Free account"}</p>
          <p style={{ color: status.tone }} className="text-xs truncate">{status.text}</p>
        </div>
      </div>

      <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide mb-2">Subscription</p>
      <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl px-4 mb-5">
        {entitled ? (
          <button onClick={manageSubscription} style={{ borderBottom: "1px solid " + c.border }} className="w-full flex items-center gap-3 py-3 text-left">
            <CreditCard size={18} style={{ color: c.green }} />
            <span style={{ color: c.text }} className="text-sm flex-1">Manage subscription</span>
            <ChevronRight size={16} style={{ color: c.textSecondary }} />
          </button>
        ) : (
          <button onClick={() => nav("opportunities")} style={{ borderBottom: "1px solid " + c.border }} className="w-full flex items-center gap-3 py-3 text-left">
            <CreditCard size={18} style={{ color: c.green }} />
            <span style={{ color: c.text }} className="text-sm flex-1">Upgrade to Pro</span>
            <ChevronRight size={16} style={{ color: c.textSecondary }} />
          </button>
        )}
        {purchasesAvailable && (
          <button disabled={busy} onClick={doRestore} className="w-full flex items-center gap-3 py-3 text-left">
            <RotateCcw size={18} style={{ color: c.textSecondary }} />
            <span style={{ color: c.text }} className="text-sm flex-1">{busy ? "Restoring…" : "Restore purchases"}</span>
          </button>
        )}
      </div>

      <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide mb-2">Trading preferences</p>
      <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4 mb-5 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <span style={{ color: c.text }} className="text-sm">Default stake</span>
          <div className="flex items-center gap-1"><span style={{ color: c.textSecondary }} className="text-sm">£</span>
            <input type="number" inputMode="decimal" value={stake} onChange={(e) => setStake(e.target.value)} style={{ background: "transparent", color: c.text, width: 60 }} className="text-sm text-right" /></div>
        </div>
        <div className="flex items-center justify-between">
          <span style={{ color: c.text }} className="text-sm">Default commission</span>
          <div className="flex items-center gap-1">
            <input type="number" inputMode="decimal" value={commission} onChange={(e) => setCommission(e.target.value)} style={{ background: "transparent", color: c.text, width: 40 }} className="text-sm text-right" />
            <span style={{ color: c.textSecondary }} className="text-sm">%</span></div>
        </div>
        <div className="flex items-center justify-between">
          <span style={{ color: c.text }} className="text-sm">Risk warning</span>
          <div className="flex items-center gap-1">
            <input type="number" inputMode="decimal" value={risk} onChange={(e) => setRisk(e.target.value)} style={{ background: "transparent", color: c.text, width: 40 }} className="text-sm text-right" />
            <span style={{ color: c.textSecondary }} className="text-sm">% of bankroll</span></div>
        </div>
        <button onClick={save} style={{ background: c.green, color: c.greenDark }} className="rounded-xl py-2 text-sm font-medium">Save preferences</button>
        {saved && <p style={{ color: saved === "Saved" ? c.green : c.red }} className="text-xs text-center">{saved}</p>}
      </div>

      <p style={{ color: c.textSecondary }} className="text-xs uppercase tracking-wide mb-2">About</p>
      <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-4 mb-5 flex flex-col gap-2">
        <p style={{ color: c.text }} className="text-sm flex items-center gap-2"><Info size={14} /> How FTA% works</p>
        <p style={{ color: c.textSecondary }} className="text-xs">
          FTA% is the chance the team goes two goals up and then fails to win, from a model trained on
          five seasons across 25 leagues and tested on seasons it never saw. Across the average fixture it's
          about 2%; top-ranked picks have happened about 1.5× as often as average in testing.
        </p>
        {(TERMS_URL || PRIVACY_URL) && (
          <p className="text-xs flex items-center gap-2">
            <Shield size={14} style={{ color: c.textSecondary }} />
            {TERMS_URL && <a href={TERMS_URL} style={{ color: c.cyan }}>Terms</a>}
            {PRIVACY_URL && <a href={PRIVACY_URL} style={{ color: c.cyan }}>Privacy</a>}
          </p>
        )}
        <p style={{ color: c.textSecondary }} className="text-[11px] break-all">Support ID: {userId || "—"}</p>
      </div>

      <Disclaimer />
      <p style={{ color: c.textSecondary }} className="text-xs text-center mt-2">TurnaroundIQ v1.0.0</p>
    </PageShell>
  );
}

function ModelTestingPage({ nav, entitled }) {
  const q = useApi(() => api.modelRuns(), []);
  const runs = q.data?.runs || [];
  const chartData = runs.slice().reverse().map((r, i) => ({ index: i + 1, brier: r.brier_score, roc_auc: r.roc_auc }));
  return (
    <PageShell activeTab="menu" onNavigate={nav} entitled={entitled}>
      <p style={{ color: c.text }} className="text-xl font-medium mb-1">Model testing (dev)</p>
      <p style={{ color: c.textSecondary }} className="text-sm mb-4">Training runs from {API_BASE}. Only ADMIN_USER_IDS can see this.</p>
      {q.loading && <Loading />}
      {(q.error || q.needsPro) && <ErrorBox error={q.error || "Not authorised — add your Support ID to ADMIN_USER_IDS on the server."} onRetry={q.reload} />}
      {q.data && runs.length === 0 && <Empty>No training runs logged yet.</Empty>}
      {runs.length > 0 && (
        <>
          <div style={{ background: c.card, border: "1px solid " + c.border }} className="rounded-xl p-3 mb-4">
            <div style={{ height: 180 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 5, right: 8, left: -20, bottom: 0 }}>
                  <CartesianGrid stroke={c.border} strokeDasharray="3 3" />
                  <XAxis dataKey="index" stroke={c.textSecondary} tick={{ fontSize: 11 }} />
                  <YAxis stroke={c.textSecondary} tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: c.cardAlt, border: "1px solid " + c.border, borderRadius: 8 }} labelStyle={{ color: c.text }} />
                  <Legend wrapperStyle={{ fontSize: 12, color: c.textSecondary }} />
                  <Line type="monotone" dataKey="brier" name="Brier" stroke={c.orange} strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="roc_auc" name="AUC" stroke={c.cyan} strokeWidth={2} dot={{ r: 3 }} />
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
                  <StatBox label="Rows" value={String(r.training_rows)} />
                  <StatBox label="Brier" value={r.brier_score?.toFixed(4)} tone={c.orange} />
                  <StatBox label="Log loss" value={r.log_loss?.toFixed(4)} />
                  <StatBox label="AUC" value={r.roc_auc?.toFixed(3)} tone={c.cyan} />
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

// ============================================================
// APP ROOT
// ============================================================
export default function App() {
  const [page, setPage] = useState("dashboard");
  const [userId, setUserIdState] = useState(null);
  const [booted, setBooted] = useState(false);
  const [selected, setSelected] = useState(null);
  const [me, setMe] = useState(null);

  const loadMe = useCallback(async () => {
    try {
      setMe(await api.me());
    } catch {
      setMe(null); // no user id yet (browser without dev id) or offline -> Free
    }
  }, []);

  useEffect(() => {
    let cleanup = () => {};
    initPurchases()
      .then(async (id) => {
        setUserIdState(id);
        await loadMe();
        cleanup = await onCustomerInfoChange(() => loadMe());
      })
      .catch(() => {})
      .finally(() => setBooted(true));
    return () => cleanup();
  }, [loadMe]);

  const entitled = Boolean(me?.entitled);
  const opps = useApi(() => (entitled ? api.opportunities() : Promise.resolve(null)), [entitled]);

  if (!booted) {
    return (
      <div style={{ background: c.bg, minHeight: "100vh" }} className="flex items-center justify-center">
        <img src={LOGO_SRC} alt="TurnaroundIQ" className="h-10 w-auto opacity-80" />
      </div>
    );
  }

  const common = { nav: setPage, entitled, onPurchased: loadMe };
  const pages = {
    dashboard: <DashboardPage {...common} me={me} opps={opps} onOpen={setSelected} />,
    opportunities: <OpportunitiesPage {...common} opps={opps} onOpen={setSelected} />,
    "early-goal-hunter": <EarlyGoalHunterPage {...common} />,
    "chaos-factor": <ChaosFactorPage {...common} />,
    live: <LiveMonitorPage {...common} />,
    bets: <MyBetsPage {...common} reloadMe={loadMe} />,
    calculator: <CalculatorPage {...common} prefs={me?.prefs} />,
    settings: <SettingsPage {...common} me={me} userId={userId} reloadMe={loadMe} />,
    ...(SHOW_DEV_TOOLS ? { "model-testing": <ModelTestingPage {...common} /> } : {}),
  };

  return (
    <>
      {pages[page] || pages.dashboard}
      <OpportunityDetailModal opportunity={selected} onClose={() => setSelected(null)} prefs={me?.prefs} />
    </>
  );
}
