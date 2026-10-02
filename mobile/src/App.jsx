import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
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
  LogOut,
  Mail,
  ChevronDown,
  Check,
  Sparkles,
  Medal,
} from "lucide-react";

import { LOGO_SRC } from "./logo";
import StablesPage from "./stables/StablesPage";
import { api, API_BASE, ApiError, MIN_FTA, MIN_SCORE } from "./lib/api";
import {
  clearSession,
  finishSignIn,
  getPackages,
  getSession,
  initPurchases,
  isNative,
  manageSubscription,
  onCustomerInfoChange,
  openWebCheckout,
  purchase,
  restore,
  signOut,
  startSignIn,
} from "./lib/purchases";

// { me, reloadMe } for components deep in the tree (paywall, settings)
const Account = createContext({ me: null, reloadMe: async () => {} });

const SHOW_DEV_TOOLS = import.meta.env.VITE_SHOW_DEV_TOOLS === "true";
const TERMS_URL = import.meta.env.VITE_TERMS_URL || "terms.html";
const PRIVACY_URL = import.meta.env.VITE_PRIVACY_URL || "privacy.html";
const PRO_PRICE = import.meta.env.VITE_PRO_PRICE || "£9.99";

// ---- Brand tokens (locked palette) ----
const c = {
  bg: "#05080F",
  card: "#0A0F1C",
  cardAlt: "#0D1424",
  border: "#151E33",
  green: "#36E98F",
  greenDark: "#04140C",
  cyan: "#4BC7FF",
  blue: "#4B6FFF",
  orange: "#FF9C42",
  red: "#FF5252",
  text: "#F5F7FA",
  textSecondary: "#9AA3BC",
  textMuted: "#5F6A87",
  line: "rgba(54,233,143,0.22)",
};

// Premium dark surfaces: near-black panels, hairline borders, one glowing accent.
const card = {
  background: "linear-gradient(180deg, #0B1120 0%, #080C17 100%)",
  border: "1px solid " + c.border,
  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
};
const heroCard = {
  background: "radial-gradient(90% 120% at 100% 0%, rgba(54,233,143,0.14) 0%, rgba(54,233,143,0) 55%), linear-gradient(180deg, #0B1322 0%, #070B15 100%)",
  border: "1px solid rgba(54,233,143,0.38)",
  boxShadow: "0 0 0 1px rgba(54,233,143,0.05), 0 0 42px rgba(54,233,143,0.13), inset 0 1px 0 rgba(255,255,255,0.05)",
};
const accentCard = {
  ...card,
  border: "1px solid rgba(54,233,143,0.30)",
  boxShadow: "0 0 28px rgba(54,233,143,0.08), inset 0 1px 0 rgba(255,255,255,0.03)",
};
const primaryBtn = {
  background: "linear-gradient(180deg, #43F09A 0%, #2BD47F 100%)",
  color: "#03140B",
  boxShadow: "0 0 24px rgba(54,233,143,0.30), inset 0 1px 0 rgba(255,255,255,0.35)",
};
const chip = (active) => ({
  background: active ? "rgba(54,233,143,0.10)" : "transparent",
  border: "1px solid " + (active ? "rgba(54,233,143,0.45)" : c.border),
  color: active ? c.green : c.textSecondary,
});

// FTA% vs the ~2% base rate: colour + "x average" label
function ftaTone(v) {
  if (v == null) return c.textSecondary;
  if (v >= 3) return c.green;
  if (v >= 2) return c.cyan;
  return c.textSecondary;
}
function vsAverage(v) {
  if (v == null || !isFinite(v)) return null;
  return (v / 2).toFixed(1) + "× avg";
}

function Wordmark({ size = "md", tagline = false }) {
  const t = { sm: "text-[13px]", header: "text-[16px]", md: "text-[15px]", lg: "text-2xl" }[size];
  return (
    <span className="inline-flex flex-col leading-none">
      <span className={t + " font-bold uppercase"} style={{ letterSpacing: "0.09em" }}>
        <span style={{ color: c.text }}>Turnaround</span><span style={{ color: c.green, marginLeft: "0.12em" }}>IQ</span>
      </span>
      {tagline && (
        <span style={{ color: c.green, letterSpacing: size === "lg" ? "0.32em" : "0.2em" }} className={(size === "lg" ? "text-[10px] mt-2.5" : "text-[8px] mt-1.5") + " font-semibold uppercase whitespace-nowrap"}>
          Data. Intelligence. Edge.
        </span>
      )}
    </span>
  );
}

function Logo({ size = 28, glow = false }) {
  return (
    <img src={LOGO_SRC} alt="" style={{ height: size, width: "auto", filter: glow ? "drop-shadow(0 0 10px rgba(54,233,143,0.55))" : "drop-shadow(0 0 6px rgba(54,233,143,0.25))" }} />
  );
}

function SectionLabel({ children, action, onAction }) {
  return (
    <div className="flex items-center justify-between mb-3 mt-1">
      <p style={{ color: c.textMuted, letterSpacing: "0.14em" }} className="text-[11px] font-semibold uppercase">{children}</p>
      {action && <button onClick={onAction} style={{ color: c.green }} className="text-xs font-medium">{action}</button>}
    </div>
  );
}

function PageTitle({ title, subtitle, right }) {
  return (
    <div className="mb-5">
      <div className="flex items-start justify-between gap-3">
        <h1 style={{ color: c.text }} className="text-[26px] lg:text-3xl font-bold tracking-tight leading-tight">{title}</h1>
        {right}
      </div>
      {subtitle && <p style={{ color: c.textSecondary }} className="text-sm mt-1.5 max-w-[640px]">{subtitle}</p>}
    </div>
  );
}

// Big figure with a smaller unit, e.g. 3.40 %
function BigNum({ value, unit = "%", dp = 2, tone = c.text, size = "text-2xl" }) {
  if (value == null || isNaN(value)) return <span style={{ color: c.textMuted }} className={size + " font-bold"}>—</span>;
  return (
    <span style={{ color: tone }} className={"num font-bold leading-none " + size}>
      {Number(value).toFixed(dp)}<span className="text-[0.55em] font-semibold ml-0.5 opacity-80">{unit}</span>
    </span>
  );
}

// Data-depth as signal bars (history behind the numbers, not a probability)
function DepthBars({ score }) {
  const d = depthLabel(score);
  const lit = score >= 80 ? 3 : score >= 60 ? 2 : 1;
  return (
    <span className="flex items-center gap-1.5 text-xs font-medium" style={{ color: d.tone }}>
      <span className="flex items-end gap-[2px]">
        {[6, 9, 12].map((h, i) => (
          <span key={h} style={{ height: h, width: 3, borderRadius: 1, background: i < lit ? d.tone : c.border }} />
        ))}
      </span>
      {d.label}
    </span>
  );
}

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
// Highest lay price at which the model's expected profit is still >= 0 (null if none)
function breakEvenLay(backOdds, stake, commission, ftaPct) {
  if (!(backOdds > 1) || !(stake > 0) || !(ftaPct > 0)) return null;
  let best = null;
  for (let lay = Math.max(1.01, backOdds); lay <= backOdds * 2 + 1; lay = Math.round((lay + 0.01) * 100) / 100) {
    const ls = calcLayStake(backOdds, lay, stake, commission);
    const ev = calcExpectedProfit(calcFtaProfit(stake, backOdds, ls, commission), calcQualifyingLoss(backOdds, lay, stake, ls), ftaPct);
    if (ev >= 0) best = lay;
    else break;
  }
  return best;
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
  const month = d.toLocaleString("en-GB", { month: "short" });
  const today = new Date();
  const tomorrow = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
  const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  const label = sameDay(d, today) ? "Today" : sameDay(d, tomorrow) ? "Tomorrow"
    : d.toLocaleString("en-GB", { weekday: "short" }) + " " + day + ordinalSuffix(day) + " " + month;
  if (dateOnly) return label;
  return label + " · " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}
const pct = (v, dp = 1) => (v == null || isNaN(v) ? "—" : Number(v).toFixed(dp) + "%");
const money = (v) => (v == null || isNaN(v) ? "—" : (v >= 0 ? "£" : "-£") + Math.abs(v).toFixed(2));
const oppKey = (o) => `${o.match}|${o.team}`;

// confidence = how much match history backs the pick (0-100), not a probability
function depthLabel(score) {
  if (score >= 80) return { label: "Deep data", tone: c.green };
  if (score >= 60) return { label: "Good data", tone: c.cyan };
  return { label: "Thin data", tone: c.textMuted };
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
const NAV_MAIN = [
  { key: "dashboard", icon: Home, label: "Home", side: "Dashboard" },
  { key: "opportunities", icon: Rocket, label: "Picks", side: "Opportunities" },
  { key: "live", icon: RadioTower, label: "Live", side: "Live monitor" },
  { key: "bets", icon: Wallet, label: "Bets", side: "My bets" },
];
const NAV_MORE = [
  ...(SHOW_DEV_TOOLS ? [{ key: "model-testing", icon: FlaskConical, label: "Model Testing (dev)" }] : []),
  { key: "early-goal-hunter", icon: Crosshair, label: "Early Goal Hunter" },
  { key: "chaos-factor", icon: Flame, label: "Chaos Factor" },
  { key: "stables", icon: Medal, label: "The Stables" },
  { key: "calculator", icon: Calculator, label: "Calculator" },
  { key: "settings", icon: Settings, label: "Settings" },
];

function isBeta(me) {
  return Boolean(me?.beta?.active && !me?.paid);
}

function betaDate(me) {
  const d = me?.beta?.until;
  return d ? new Date(d + "T12:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "";
}

// Shown to beta users who haven't subscribed: when the beta ends + how to keep access.
function BetaBanner({ compact }) {
  const { me } = useContext(Account);
  if (!isBeta(me)) return null;
  const founder = me.beta.founder_price;
  return (
    <div style={{ ...accentCard }} className={"rounded-2xl p-4 " + (compact ? "" : "mb-5 lg:mb-6")}>
      <div className="flex items-start gap-3">
        <Sparkles size={18} style={{ color: c.green, flexShrink: 0, marginTop: 2 }} />
        <div className="flex-1 min-w-0">
          <p style={{ color: c.green, letterSpacing: "0.14em" }} className="text-[11px] font-bold uppercase">Free beta · until {betaDate(me)}</p>
          <p style={{ color: c.text }} className="text-sm mt-1">
            {founder
              ? <>Everything is unlocked. Subscribe before the beta ends to lock in the founding-member price of <span className="num font-semibold">{founder}</span>/month for as long as you stay subscribed.</>
              : <>Everything is unlocked. Pro is {PRO_PRICE}/month after the beta.</>}
          </p>
          {me.purchase_url && (
            <button onClick={() => openWebCheckout(me.purchase_url)} style={primaryBtn} className="rounded-xl px-4 py-2 text-xs font-semibold mt-3">
              {founder ? "Lock in " + founder + "/month" : "Subscribe"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function ProBadge({ entitled }) {
  const { me } = useContext(Account);
  const beta = entitled && isBeta(me);
  return (
    <span
      style={{
        color: entitled ? c.green : c.textSecondary,
        border: "1px solid " + (entitled ? "rgba(54,233,143,0.45)" : c.border),
        background: entitled ? "rgba(54,233,143,0.08)" : "transparent",
        letterSpacing: "0.12em",
      }}
      className="text-[11px] font-bold uppercase px-3 py-1.5 rounded-lg"
    >
      {beta ? "Beta" : entitled ? "Pro" : "Free"}
    </span>
  );
}

function PageHeader({ onNavigate, entitled }) {
  return (
    <div className="flex items-center justify-between mb-6 lg:hidden">
      <button onClick={() => onNavigate("dashboard")} className="flex items-center gap-3">
        <Logo size={31} glow />
        <Wordmark size="header" />
      </button>
      <ProBadge entitled={entitled} />
    </div>
  );
}

// Desktop: fixed left rail with every section (replaces the bottom bar)
function Sidebar({ activeTab, onNavigate, entitled }) {
  const { me } = useContext(Account);
  const item = ({ key, icon: Icon, label, side }) => {
    const active = key === activeTab;
    return (
      <button key={key} onClick={() => onNavigate(key)} style={{ background: active ? "rgba(54,233,143,0.08)" : "transparent", color: active ? c.green : c.textSecondary, borderLeft: "2px solid " + (active ? c.green : "transparent") }} className="w-full flex items-center gap-3 px-4 py-2.5 rounded-r-lg text-sm font-medium text-left">
        <Icon size={18} /> {side || label}
      </button>
    );
  };
  const paper = me?.paper;
  return (
    <aside style={{ background: "linear-gradient(180deg, #070B15 0%, #05080F 100%)", borderRight: "1px solid " + c.border }} className="hidden lg:flex fixed left-0 top-0 bottom-0 w-64 flex-col px-3 py-6 z-40">
      <button onClick={() => onNavigate("dashboard")} className="flex items-center gap-2.5 px-3 mb-8">
        <Logo size={30} glow />
        <Wordmark size="sm" tagline />
      </button>
      <nav className="flex flex-col gap-1">{NAV_MAIN.map(item)}</nav>
      <p style={{ color: c.textMuted, letterSpacing: "0.14em" }} className="text-[10px] font-semibold uppercase px-4 mt-6 mb-2">Tools</p>
      <nav className="flex flex-col gap-1">{NAV_MORE.map(item)}</nav>
      <div className="mt-auto px-1">
        {paper && (
          <div style={card} className="rounded-xl p-4 mb-3">
            <p style={{ color: c.textMuted, letterSpacing: "0.12em" }} className="text-[10px] font-semibold uppercase mb-1">Paper P/L</p>
            <p style={{ color: (paper.total_profit || 0) >= 0 ? c.green : c.red }} className="num text-xl font-bold">{money(paper.total_profit || 0)}</p>
          </div>
        )}
        <div className="flex items-center justify-between px-2">
          <span style={{ color: c.textMuted }} className="text-xs truncate">{me?.email || ""}</span>
          <ProBadge entitled={entitled} />
        </div>
      </div>
    </aside>
  );
}

function BottomNav({ activeTab, onNavigate }) {
  const [open, setOpen] = useState(false);
  const go = (key) => {
    setOpen(false);
    onNavigate(key);
  };
  const glass = { background: "rgba(8,12,23,0.86)", border: "1px solid " + c.border, backdropFilter: "blur(18px)", WebkitBackdropFilter: "blur(18px)" };
  return (
    <div className="fixed bottom-0 left-0 right-0 flex justify-center pb-4 px-4 lg:hidden" style={{ paddingBottom: "calc(1rem + env(safe-area-inset-bottom))" }}>
      <div className="w-full max-w-[420px]">
        {open && (
          <div style={{ ...glass, boxShadow: "0 18px 50px rgba(0,0,0,0.6)" }} className="rounded-2xl p-2 mb-2">
            {NAV_MORE.map(({ key, icon: Icon, label }) => (
              <button key={key} onClick={() => go(key)} className="w-full flex items-center gap-3 px-3 py-3 text-left rounded-xl">
                <Icon size={18} style={{ color: key === activeTab ? c.green : c.textSecondary }} />
                <span style={{ color: key === activeTab ? c.green : c.text }} className="text-sm font-medium">{label}</span>
                <ChevronRight size={16} style={{ color: c.textMuted, marginLeft: "auto" }} />
              </button>
            ))}
          </div>
        )}
        <div style={{ ...glass, boxShadow: "0 14px 36px rgba(0,0,0,0.55)" }} className="rounded-2xl flex items-center justify-between px-1.5 py-1.5">
          {NAV_MAIN.map(({ key, icon: Icon, label }) => {
            const active = !open && key === activeTab;
            return (
              <button key={key} aria-label={key} onClick={() => go(key)} className="flex-1 flex flex-col items-center gap-1 py-2 relative">
                {active && <span style={{ background: c.green, boxShadow: "0 0 10px " + c.green }} className="absolute top-0 w-6 h-[2px] rounded-full" />}
                <Icon size={20} style={{ color: active ? c.green : c.textMuted }} />
                <span style={{ color: active ? c.green : c.textMuted }} className="text-[10px] font-semibold">{label}</span>
              </button>
            );
          })}
          <button aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen(!open)} className="flex-1 flex flex-col items-center gap-1 py-2">
            {open ? <X size={20} style={{ color: c.green }} /> : <Menu size={20} style={{ color: c.textMuted }} />}
            <span style={{ color: open ? c.green : c.textMuted }} className="text-[10px] font-semibold">More</span>
          </button>
        </div>
      </div>
    </div>
  );
}

function PageShell({ children, activeTab, onNavigate, entitled }) {
  return (
    <div style={{ background: "radial-gradient(1000px 420px at 50% -200px, rgba(54,233,143,0.09), transparent 70%), " + c.bg, minHeight: "100vh" }} className="pb-36 lg:pb-12">
      <Sidebar activeTab={activeTab} onNavigate={onNavigate} entitled={entitled} />
      <div className="lg:pl-64">
        <div className="max-w-[440px] lg:max-w-[1120px] mx-auto px-4 lg:px-10 pt-5 lg:pt-10">
          <PageHeader onNavigate={onNavigate} entitled={entitled} />
          {children}
        </div>
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
    <div style={card} className="flex-shrink-0 rounded-xl px-4 py-3 min-w-[110px]">
      <p style={{ color: c.textSecondary }} className="text-xs mb-1">{label}</p>
      <p style={{ color: tone }} className="num text-xl font-semibold">{value}</p>
    </div>
  );
}

function StatBox({ label, value, tone }) {
  return (
    <div>
      <p style={{ color: c.textSecondary }} className="text-xs">{label}</p>
      <p style={{ color: tone || c.text }} className="num text-base font-semibold">{value}</p>
    </div>
  );
}

// ============================================================
// PAYWALL -- real App Store / Play purchase via RevenueCat
// ============================================================
function Paywall({ title, onPurchased }) {
  const { me } = useContext(Account);
  const [packages, setPackages] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    if (isNative) getPackages().then(setPackages).catch(() => setPackages([]));
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
  const checkAgain = async () => {
    setBusy(true);
    await onPurchased();
    setBusy(false);
  };

  return (
    <div style={heroCard} className="rounded-2xl p-6 mt-4 max-w-[520px]">
      <p style={{ color: c.green, letterSpacing: "0.16em" }} className="text-[11px] font-bold uppercase mb-3 flex items-center gap-2">
        <Lock size={13} /> {title || "This is a Pro feature"}
      </p>
      <div className="flex items-end gap-2 mb-1">
        <span style={{ color: c.text }} className="num text-5xl font-bold tracking-tight leading-none">{PRO_PRICE}</span>
        <span style={{ color: c.textSecondary }} className="text-sm mb-1">/ month</span>
      </div>
      <p style={{ color: c.textSecondary }} className="text-xs mb-5">Cancel anytime.</p>
      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 mb-6 text-left">
        {["Ranked FTA picks, next 24h", "Best UK prices + est. lay", "Early Goal Hunter", "Chaos Factor", "Paper-bet tracker", "2-up & free-bet calculator"].map((f) => (
          <li key={f} className="flex items-center gap-2 text-sm" style={{ color: c.text }}>
            <Check size={15} style={{ color: c.green, flexShrink: 0 }} /> {f}
          </li>
        ))}
      </ul>

      {isNative ? (
        <>
          {packages === null && <Loading />}
          {packages && packages.length === 0 && (
            <p style={{ color: c.textSecondary }} className="text-xs mb-3">No subscription options available right now.</p>
          )}
          {(packages || []).map((pkg) => (
            <button key={pkg.identifier} disabled={busy} onClick={() => buy(pkg)} style={{ ...primaryBtn, opacity: busy ? 0.6 : 1 }} className="w-full rounded-xl py-3 text-sm font-medium mb-2">
              {pkg.product?.title || "Upgrade to Pro"} — {pkg.product?.priceString}
            </button>
          ))}
          <button disabled={busy} onClick={doRestore} style={{ color: c.cyan }} className="text-xs font-medium mt-1">Restore purchases</button>
        </>
      ) : me?.purchase_url ? (
        <>
          <p style={{ color: c.textSecondary }} className="text-[11px] mb-3">
            By subscribing you agree to the <a href={TERMS_URL} style={{ color: c.cyan }}>Terms</a> and ask us to
            start Pro immediately, so the 14-day cancellation right ends once access begins. Cancel any time.
          </p>
          <button disabled={busy} onClick={() => openWebCheckout(me.purchase_url)} style={primaryBtn} className="w-full rounded-xl py-3 text-sm font-semibold mb-2">
            Start Pro — {PRO_PRICE}/month
          </button>
          <button disabled={busy} onClick={checkAgain} style={{ color: c.cyan }} className="text-xs font-medium mt-1">
            {busy ? "Checking…" : "Already paid? Check again"}
          </button>
          <p style={{ color: c.textSecondary }} className="text-[11px] mt-3">
            Secure checkout by Stripe via RevenueCat. Your subscription is linked to {me.email || "this account"}.
          </p>
        </>
      ) : (
        <p style={{ color: c.textSecondary }} className="text-xs mb-3">Subscriptions open soon.</p>
      )}
      {message && <p style={{ color: c.orange }} className="text-xs mt-3">{message}</p>}
      <p style={{ color: c.textSecondary }} className="text-[11px] mt-4">
        Subscriptions renew automatically until cancelled.
        {TERMS_URL && <> · <a href={TERMS_URL} style={{ color: c.cyan }}>Terms</a></>}
        {PRIVACY_URL && <> · <a href={PRIVACY_URL} style={{ color: c.cyan }}>Privacy</a></>}
      </p>
    </div>
  );
}

// ============================================================
// SIGN IN (web) -- email + 6-digit code, no passwords
// ============================================================
function SignInPage({ onSignedIn }) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState("email");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const send = async (e) => {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await startSignIn(email.trim());
      setStep("code");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  const verify = async (e) => {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await finishSignIn(email.trim(), code.trim());
      await onSignedIn();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  const inputStyle = { background: c.cardAlt, color: c.text, border: "1px solid " + c.border };

  return (
    <div style={{ background: "radial-gradient(700px 420px at 50% 18%, rgba(54,233,143,0.14), rgba(75,199,255,0.05) 45%, transparent 70%), " + c.bg, minHeight: "100vh" }} className="flex flex-col justify-center px-6">
      <div className="max-w-[380px] w-full mx-auto">
        <div className="flex flex-col items-center mb-9 text-center">
          <Logo size={64} glow />
          <div className="mt-5"><Wordmark size="lg" tagline /></div>
          <p style={{ color: c.textSecondary }} className="text-sm mt-5">Find football's most <span style={{ color: c.green }}>fragile leads.</span></p>
        </div>
        <div style={card} className="rounded-2xl p-6">
          {step === "email" ? (
            <form onSubmit={send} className="flex flex-col gap-3">
              <p style={{ color: c.text }} className="text-xl font-bold tracking-tight">Sign in</p>
              <p style={{ color: c.textSecondary }} className="text-sm">We'll email you a 6-digit code. No password needed.</p>
              <input type="email" autoComplete="email" inputMode="email" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} style={inputStyle} className="rounded-xl px-4 py-3 text-base" />
              <button type="submit" disabled={busy || !email} style={{ ...primaryBtn, opacity: busy || !email ? 0.55 : 1 }} className="rounded-xl py-3 text-sm font-medium flex items-center justify-center gap-2">
                <Mail size={16} /> {busy ? "Sending…" : "Email me a code"}
              </button>
            </form>
          ) : (
            <form onSubmit={verify} className="flex flex-col gap-3">
              <p style={{ color: c.text }} className="text-base font-medium">Check your email</p>
              <p style={{ color: c.textSecondary }} className="text-sm">Enter the code sent to {email}.</p>
              <input autoComplete="one-time-code" inputMode="numeric" maxLength={6} placeholder="123456" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} style={{ ...inputStyle, letterSpacing: "0.4em" }} className="rounded-xl px-4 py-3 text-xl text-center" />
              <button type="submit" disabled={busy || code.length !== 6} style={{ ...primaryBtn, opacity: busy || code.length !== 6 ? 0.55 : 1 }} className="rounded-xl py-3 text-sm font-medium">
                {busy ? "Checking…" : "Sign in"}
              </button>
              <button type="button" onClick={() => { setStep("email"); setCode(""); }} style={{ color: c.cyan }} className="text-xs font-medium">Use a different email / resend</button>
            </form>
          )}
          {error && <p style={{ color: c.red }} className="text-xs mt-3">{error}</p>}
        </div>
        <p style={{ color: c.textSecondary }} className="text-[11px] text-center mt-4">
          By continuing you agree to our <a href={TERMS_URL} style={{ color: c.cyan }}>Terms</a> and{" "}
          <a href={PRIVACY_URL} style={{ color: c.cyan }}>Privacy Policy</a>. 18+ only.
        </p>
        <Disclaimer />
      </div>
    </div>
  );
}

// ============================================================
// OPPORTUNITIES (FTA)
// fta_pct = chance the team goes 2 up AND fails to win (full event)
// ============================================================
function Metric({ label, value, tone }) {
  return (
    <div className="min-w-0">
      <p style={{ color: c.textMuted, letterSpacing: "0.08em" }} className="text-[10px] font-semibold uppercase mb-1">{label}</p>
      <p style={{ color: tone || c.text }} className="num text-sm font-semibold">{value}</p>
    </div>
  );
}

function kickoffParts(iso) {
  const d = new Date(iso);
  if (!iso || isNaN(d.getTime())) return { time: "TBC", day: "" };
  const full = formatKickoff(iso);
  return { time: d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }), day: full.split(" · ")[0] };
}

function FtaBox({ value, highlight }) {
  const tone = ftaTone(value);
  return (
    <div style={{ background: highlight ? "rgba(54,233,143,0.08)" : "rgba(255,255,255,0.02)", border: "1px solid " + (highlight ? "rgba(54,233,143,0.40)" : c.border) }} className="rounded-xl w-[112px] py-3 flex flex-col items-center justify-center flex-shrink-0">
      <BigNum value={value} tone={tone} size="text-[28px]" />
      <p style={{ color: c.textMuted, letterSpacing: "0.1em" }} className="text-[9px] font-bold uppercase leading-none mt-2">FTA chance</p>
    </div>
  );
}

function PriceLine({ o }) {
  if (o.not_at_my_books) return <p style={{ color: c.orange }} className="text-xs">Not priced at your bookmakers yet</p>;
  if (o.odds_estimated || !o.back_odds) return <p style={{ color: c.textMuted }} className="text-xs">Prices not in yet — tap to enter your own</p>;
  return (
    <div className="flex items-baseline gap-4 text-xs min-w-0">
      <span className="flex items-baseline gap-1.5 min-w-0">
        <span style={{ color: c.textMuted }}>Book</span>
        <span style={{ color: c.green }} className="num text-sm font-semibold">{Number(o.back_odds).toFixed(2)}</span>
        <span style={{ color: c.textSecondary }} className="truncate">{o.bookmaker}</span>
      </span>
      <span className="flex items-baseline gap-1.5 flex-shrink-0">
        <span style={{ color: c.textMuted }}>Lay{o.estimated_lay ? " est." : ""}</span>
        <span style={{ color: c.cyan }} className="num text-sm font-semibold">{Number(o.lay_odds).toFixed(2)}</span>
      </span>
    </div>
  );
}

function OpportunityCard({ o, onClick, highlight }) {
  const k = kickoffParts(o.kickoff);
  return (
    <button onClick={() => onClick(o)} style={{ ...(highlight ? accentCard : card), textAlign: "left" }} className="w-full rounded-xl p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-baseline gap-2">
          <span style={{ color: c.text }} className="num text-sm font-bold">{k.time}</span>
          <span style={{ color: c.textMuted }} className="text-xs">{k.day}</span>
        </span>
        <span style={{ color: c.textMuted, letterSpacing: "0.06em" }} className="text-[10px] font-semibold uppercase truncate">{o.league}</span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p style={{ color: c.text }} className="text-base font-semibold leading-snug truncate">{o.home_team}</p>
          <p style={{ color: c.textSecondary }} className="text-sm leading-snug truncate"><span style={{ color: c.textMuted }}>vs</span> {o.away_team}</p>
          <p style={{ color: c.textMuted }} className="text-xs mt-1.5 truncate">2-up team <span style={{ color: c.green }} className="font-medium">{o.team}</span></p>
        </div>
        <FtaBox value={o.fta_pct} highlight={highlight} />
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Metric label="Goes 2 up" value={pct(o.two_up_pct, 0)} />
        <Metric label="Then fails" value={pct(o.fail_given_2up_pct ?? o.turnaround_pct, 1)} />
        <Metric label="Usual 2-up" value={o.usual_2up_minute ? Math.round(o.usual_2up_minute) + "'" : "—"} />
      </div>
      <div style={{ borderTop: "1px solid " + c.border }} className="flex items-center justify-between gap-3 pt-3">
        <PriceLine o={o} />
        <DepthBars score={o.confidence} />
      </div>
    </button>
  );
}

// Desktop: dense sortable-looking table like a trading screen
function OpportunityTable({ list, onOpen }) {
  const th = { color: c.textMuted, letterSpacing: "0.1em" };
  return (
    <div style={card} className="rounded-xl overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr style={{ borderBottom: "1px solid " + c.border }}>
            {["Kick-off", "Match", "Goes 2 up", "Then fails", "FTA chance", "Book", "Lay est.", "Data"].map((h, i) => (
              <th key={h} style={th} className={"text-[10px] font-semibold uppercase py-3 px-4 " + (i < 2 ? "text-left" : i === 7 ? "text-left" : "text-right")}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {list.map((o, i) => {
            const k = kickoffParts(o.kickoff);
            const priced = !o.odds_estimated && o.back_odds;
            return (
              <tr key={oppKey(o)} onClick={() => onOpen(o)} style={{ borderBottom: "1px solid " + c.border, background: i === 0 ? "rgba(54,233,143,0.04)" : "transparent" }} className="cursor-pointer hover:bg-white/[0.02]">
                <td className="py-3 px-4 whitespace-nowrap">
                  <p style={{ color: c.text }} className="num font-semibold">{k.time}</p>
                  <p style={{ color: c.textMuted }} className="text-xs">{k.day}</p>
                </td>
                <td className="py-3 px-4">
                  <p style={{ color: c.text }} className="font-semibold">{o.home_team} <span style={{ color: c.textMuted }} className="font-normal">vs</span> {o.away_team}</p>
                  <p style={{ color: c.textMuted }} className="text-xs">{o.league} · 2-up team <span style={{ color: c.green }}>{o.team}</span></p>
                </td>
                <td style={{ color: c.text }} className="num py-3 px-4 text-right">{pct(o.two_up_pct, 0)}</td>
                <td style={{ color: c.text }} className="num py-3 px-4 text-right">{pct(o.fail_given_2up_pct ?? o.turnaround_pct, 1)}</td>
                <td className="py-3 px-4 text-right"><BigNum value={o.fta_pct} tone={ftaTone(o.fta_pct)} size="text-lg" /></td>
                <td className="py-3 px-4 text-right whitespace-nowrap">
                  {priced ? (<><p style={{ color: c.green }} className="num font-semibold">{Number(o.back_odds).toFixed(2)}</p><p style={{ color: c.textMuted }} className="text-xs">{o.bookmaker}</p></>) : <span style={{ color: c.textMuted }}>—</span>}
                </td>
                <td style={{ color: c.cyan }} className="num py-3 px-4 text-right font-semibold">{priced ? Number(o.lay_odds).toFixed(2) : "—"}</td>
                <td className="py-3 px-4"><DepthBars score={o.confidence} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// Bottom sheet on phones, centred dialog on desktop
function Sheet({ open, onClose, children }) {
  if (!open) return null;
  return (
    <div style={{ background: "rgba(2,5,12,0.72)", backdropFilter: "blur(6px)", WebkitBackdropFilter: "blur(6px)" }} className="fixed inset-0 z-50 flex items-end lg:items-center justify-center" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "linear-gradient(180deg, #0B1222 0%, " + c.bg + " 55%)", border: "1px solid " + c.border, boxShadow: "0 -24px 70px rgba(0,0,0,0.6)" }} className="w-full max-w-[440px] lg:max-w-[520px] max-h-[90vh] overflow-y-auto rounded-t-2xl lg:rounded-2xl p-5 pb-8">
        <div className="relative flex justify-center items-center mb-4 h-8">
          <div style={{ background: c.border }} className="w-10 h-1 rounded-full lg:hidden" />
          <button aria-label="Close" onClick={onClose} style={card} className="absolute right-0 w-8 h-8 rounded-full flex items-center justify-center">
            <X size={16} style={{ color: c.textSecondary }} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function NumField({ label, value, onChange, tone = c.text, prefix, step = "0.01", labelTone, highlight, sub }) {
  return (
    <label style={{ ...card, border: "1px solid " + (highlight || c.border) }} className="rounded-xl px-3 py-2.5 block min-w-0 cursor-text">
      <span style={{ color: labelTone || c.textMuted, letterSpacing: "0.08em" }} className="block text-[10px] font-semibold uppercase mb-1 truncate">{label}</span>
      <span className="flex items-baseline gap-1">
        {prefix && <span style={{ color: c.textSecondary }} className="text-lg font-semibold">{prefix}</span>}
        <input type="number" inputMode="decimal" step={step} value={value} onChange={(e) => onChange(e.target.value)} style={{ background: "transparent", color: tone, width: "100%" }} className="num text-xl font-bold" />
      </span>
      {sub && <span style={{ color: c.textMuted }} className="block text-[10px] mt-0.5 truncate">{sub}</span>}
    </label>
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
    setBackOdds(opportunity.back_odds != null ? Number(opportunity.back_odds).toFixed(2) : "");
    setLayOdds(opportunity.lay_odds != null ? Number(opportunity.lay_odds).toFixed(2) : "");
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
  const same = (a, b) => a != null && b !== "" && Math.abs(Number(a) - parseFloat(b)) < 1e-9;
  const pricesEdited = !same(o.back_odds, backOdds) || !same(o.lay_odds, layOdds);
  const estimated = o.odds_estimated && !pricesEdited;
  const layEstimated = o.estimated_lay && !o.odds_estimated && same(o.lay_odds, layOdds);
  const pickedBook = (o.back_prices || []).find((bp) => same(bp.back, backOdds))?.bookmaker
    || (!o.odds_estimated && same(o.back_odds, backOdds) ? o.bookmaker : null);

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

  const k = kickoffParts(o.kickoff);
  const liability = calcLiability(layNum, layStake);
  return (
    <Sheet open onClose={onClose}>
      <div className="flex items-center justify-between mb-3">
        <span className="flex items-baseline gap-2">
          <span style={{ color: c.text }} className="num text-sm font-bold">{k.time}</span>
          <span style={{ color: c.textMuted }} className="text-xs">{k.day}</span>
        </span>
        <span style={{ color: c.textMuted, letterSpacing: "0.06em" }} className="text-[10px] font-semibold uppercase">{o.league}</span>
      </div>
      <p style={{ color: c.text }} className="text-xl font-bold tracking-tight leading-tight">{o.home_team} <span style={{ color: c.textMuted }} className="font-medium">vs</span> {o.away_team}</p>
      <p style={{ color: c.textSecondary }} className="text-sm mt-1 mb-5">2-up team <span style={{ color: c.green }} className="font-medium">{o.team}</span></p>

      <SectionLabel>Model probabilities</SectionLabel>
      <div style={card} className="rounded-xl p-4 grid grid-cols-3 gap-3 mb-2">
        <div><BigNum value={o.two_up_pct} dp={1} tone={c.cyan} size="text-2xl" /><p style={{ color: c.textMuted }} className="text-[11px] mt-1.5">Goes 2 up</p></div>
        <div><BigNum value={o.fail_given_2up_pct ?? o.turnaround_pct} dp={1} tone={c.orange} size="text-2xl" /><p style={{ color: c.textMuted }} className="text-[11px] mt-1.5">Then fails to win</p></div>
        <div><BigNum value={o.fta_pct} tone={c.green} size="text-2xl" /><p style={{ color: c.textMuted }} className="text-[11px] mt-1.5">FTA (both)</p></div>
      </div>
      <div className="flex items-center justify-between mb-6">
        <DepthBars score={o.confidence} />
        <span style={{ color: c.textMuted }} className="text-[11px]">match history behind these numbers</span>
      </div>

      <SectionLabel>Market odds</SectionLabel>
      <div className="grid grid-cols-3 gap-2 mb-2">
        <NumField label="Back" sub={pickedBook || "Bookmaker"} value={backOdds} onChange={setBackOdds} tone={c.green} highlight={estimated ? "rgba(255,156,66,0.5)" : undefined} />
        <NumField label={layEstimated ? "Lay est." : "Lay"} sub="Exchange" labelTone={layEstimated ? c.orange : undefined} value={layOdds} onChange={setLayOdds} tone={c.cyan} highlight={estimated || layEstimated ? "rgba(255,156,66,0.35)" : undefined} />
        <NumField label="Comm. %" sub="Exchange fee" value={commission} onChange={setCommission} step="0.1" />
      </div>
      <p style={{ color: estimated ? c.orange : c.textMuted }} className="text-[11px] mb-3">
        {estimated ? "Placeholder prices — enter your bookmaker and exchange odds." : layEstimated ? "Lay is an estimate — check the live exchange price before you bet." : "Prices are editable."}
      </p>
      {(o.back_prices || []).length > 1 && (
        <div className="no-scrollbar flex gap-2 overflow-x-auto mb-6 -mx-1 px-1">
          {o.back_prices.map((bp) => (
            <button key={bp.bookmaker} onClick={() => setBackOdds(Number(bp.back).toFixed(2))} style={chip(same(bp.back, backOdds))} className="flex-shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold whitespace-nowrap">
              {bp.bookmaker} <span className="num">{Number(bp.back).toFixed(2)}</span>
            </button>
          ))}
        </div>
      )}

      <SectionLabel>Stake calculator</SectionLabel>
      <div style={card} className="rounded-xl p-4 mb-2">
        <div className="flex items-end justify-between gap-3">
          <label className="min-w-0 flex-1 cursor-text">
            <span style={{ color: c.textMuted, letterSpacing: "0.08em" }} className="block text-[10px] font-semibold uppercase mb-1">Back stake</span>
            <span className="flex items-baseline gap-1">
              <span style={{ color: c.textSecondary }} className="text-2xl font-semibold">£</span>
              <input type="number" inputMode="decimal" step="1" value={stake} onChange={(e) => setStake(e.target.value)} style={{ background: "transparent", color: c.text, width: "100%" }} className="num text-3xl font-bold" />
            </span>
          </label>
          <div className="grid grid-cols-2 gap-1.5 flex-shrink-0">
            {[10, 25, 50, 100].map((v) => (
              <button key={v} onClick={() => setStake(String(v))} style={chip(stakeNum === v)} className="rounded-md w-[52px] py-1 text-[11px] font-semibold num">£{v}</button>
            ))}
          </div>
        </div>
      </div>
      <div style={card} className="rounded-xl grid grid-cols-2 mb-6">
        <div className="py-3.5 flex flex-col items-center text-center">
          <p style={{ color: c.textMuted, letterSpacing: "0.1em" }} className="text-[10px] font-semibold uppercase leading-none">Lay stake</p>
          <p style={{ color: c.cyan }} className="num text-xl font-bold leading-none mt-2">£{layStake.toFixed(2)}</p>
        </div>
        <div style={{ borderLeft: "1px solid " + c.border }} className="py-3.5 flex flex-col items-center text-center">
          <p style={{ color: c.textMuted, letterSpacing: "0.1em" }} className="text-[10px] font-semibold uppercase leading-none">Liability</p>
          <p style={{ color: c.orange }} className="num text-xl font-bold leading-none mt-2">£{liability.toFixed(2)}</p>
        </div>
      </div>

      <SectionLabel>Outcomes</SectionLabel>
      <div style={card} className="rounded-xl mb-3">
        <div style={{ borderBottom: "1px solid " + c.border }} className="flex items-center justify-between px-4 py-3">
          <span style={{ color: c.textSecondary }} className="text-sm">Goes 2 up, then fails to win</span>
          <span style={{ color: c.green }} className="num text-sm font-bold">{money(ftaProfit)}</span>
        </div>
        <div className="flex items-center justify-between px-4 py-3">
          <span style={{ color: c.textSecondary }} className="text-sm">Any other result</span>
          <span style={{ color: ql >= 0 ? c.green : c.red }} className="num text-sm font-bold">{money(ql)}</span>
        </div>
      </div>
      <div style={expected >= 0 ? accentCard : card} className="rounded-xl px-4 py-4 flex items-end justify-between mb-4">
        <div>
          <p style={{ color: c.textMuted, letterSpacing: "0.12em" }} className="text-[10px] font-semibold uppercase mb-1">Expected (model)</p>
          <p style={{ color: expected >= 0 ? c.green : c.red }} className="num text-3xl font-bold tracking-tight">{money(expected)}</p>
        </div>
        <p style={{ color: c.textMuted }} className="text-xs text-right num">{ev.toFixed(0)}% of risk<br />per £{stakeNum || 0} staked</p>
      </div>
      {(() => {
        const be = breakEvenLay(backNum, stakeNum, commNum, o.fta_pct);
        return (
          <div style={card} className="rounded-xl px-4 py-3 flex items-center justify-between gap-3 mb-4">
            <span style={{ color: c.textSecondary }} className="text-xs">{be ? "Worth it if the live lay is" : "No break-even lay at this back price"}</span>
            {be && <span style={{ color: layNum && layNum <= be ? c.green : c.orange }} className="num text-base font-bold">≤ {be.toFixed(2)}</span>}
          </div>
        );
      })()}
      {layEstimated && (
        <p style={{ color: c.textMuted }} className="text-[11px] mb-4">
          Back price: best UK bookmaker price we found{o.odds_updated_at ? " (checked " + formatKickoff(o.odds_updated_at) + ")" : ""}. Lay is estimated from the market's fair price.
        </p>
      )}

      <button disabled={trackState === "saving" || trackState === "saved"} onClick={track} style={{ ...primaryBtn, opacity: trackState === "saved" ? 0.6 : 1 }} className="w-full rounded-xl py-3.5 flex items-center justify-center gap-2 text-sm font-semibold">
        <Bookmark size={16} /> {trackState === "saved" ? "Tracked in My Bets" : trackState === "saving" ? "Saving…" : "Track bet (paper)"}
      </button>
      {trackState && !["saving", "saved"].includes(trackState) && <p style={{ color: c.red }} className="text-xs text-center mt-2">{trackState}</p>}
      <Disclaimer />
    </Sheet>
  );
}

// ============================================================
// PAGES
// ============================================================
function StatTile({ label, children, sub }) {
  return (
    <div style={card} className="rounded-xl px-4 py-3.5 min-w-0">
      <p style={{ color: c.textMuted, letterSpacing: "0.12em" }} className="text-[10px] font-semibold uppercase mb-2 truncate">{label}</p>
      <div className="truncate">{children}</div>
      {sub && <p style={{ color: c.textMuted }} className="text-[11px] mt-1.5 truncate">{sub}</p>}
    </div>
  );
}

function BestOpportunity({ o, onOpen }) {
  const k = kickoffParts(o.kickoff);
  return (
    <div style={heroCard} className="rounded-2xl p-5 lg:p-6">
      <div className="flex items-center justify-between mb-4">
        <p style={{ color: c.green, letterSpacing: "0.16em" }} className="text-[11px] font-bold uppercase flex items-center gap-2">
          <span style={{ background: c.green, boxShadow: "0 0 10px " + c.green }} className="w-1.5 h-1.5 rounded-full" /> Best opportunity
        </p>
        <span style={{ color: c.textSecondary }} className="num text-xs">{k.day} · {k.time}</span>
      </div>
      <p style={{ color: c.text }} className="text-xl lg:text-2xl font-bold tracking-tight leading-tight">{o.home_team} <span style={{ color: c.textMuted }} className="font-medium">vs</span> {o.away_team}</p>
      <p style={{ color: c.textSecondary }} className="text-sm mt-1">{o.league} · 2-up team <span style={{ color: c.green }} className="font-medium">{o.team}</span></p>
      <div className="grid grid-cols-3 gap-3 my-5">
        <div>
          <BigNum value={o.fta_pct} tone={c.green} size="text-[28px] lg:text-4xl" />
          <p style={{ color: c.textSecondary }} className="text-[11px] mt-1.5 leading-tight">FTA chance<br /><span style={{ color: c.textMuted }}>2 up, then no win</span></p>
        </div>
        <div>
          <BigNum value={o.two_up_pct} dp={1} tone={c.cyan} size="text-[28px] lg:text-4xl" />
          <p style={{ color: c.textSecondary }} className="text-[11px] mt-1.5 leading-tight">Goes<br />2 goals up</p>
        </div>
        <div>
          <BigNum value={o.fail_given_2up_pct ?? o.turnaround_pct} dp={1} tone={c.orange} size="text-[28px] lg:text-4xl" />
          <p style={{ color: c.textSecondary }} className="text-[11px] mt-1.5 leading-tight">Lead then<br />fails to win</p>
        </div>
      </div>
      <div style={{ borderTop: "1px solid rgba(54,233,143,0.18)" }} className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-4">
        <PriceLine o={o} />
        <button onClick={() => onOpen(o)} style={{ color: c.green, border: "1px solid rgba(54,233,143,0.4)" }} className="flex-shrink-0 text-xs font-semibold px-3 py-2.5 rounded-lg flex items-center justify-center gap-1">
          Analysis <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}

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
  const profit = paper?.total_profit || 0;

  if (!entitled) {
    return (
      <PageShell activeTab="dashboard" onNavigate={nav} entitled={entitled}>
        <PageTitle title={<>The edge is in the <span style={{ color: c.green }}>comeback.</span></>} subtitle="TurnaroundIQ finds the fixtures where a team is likely to go two goals up and still fail to win — the moments 2-up offers pay out early." />
        <Paywall title="Unlock TurnaroundIQ Pro" onPurchased={onPurchased} />
        <Disclaimer />
      </PageShell>
    );
  }

  return (
    <PageShell activeTab="dashboard" onNavigate={nav} entitled={entitled}>
      <BetaBanner />
      <div className="hidden lg:block"><PageTitle title="Dashboard" subtitle="Early-payout (2-up) opportunities for games kicking off in the next 24 hours." /></div>
      <div style={card} className="rounded-xl grid grid-cols-4 mb-6 lg:mb-8">
        {[
          { label: "Top FTA", node: <BigNum value={top?.fta_pct} tone={c.green} size="text-lg lg:text-2xl" />, sub: top ? top.team : "—" },
          { label: "Avg FTA", node: <BigNum value={avgFta} tone={c.cyan} size="text-lg lg:text-2xl" />, sub: list.length + " picks" },
          { label: "Picks", node: <span style={{ color: c.text }} className="num text-lg lg:text-2xl font-bold">{list.length}</span>, sub: "Next 24h" },
          { label: "Paper P/L", node: <span style={{ color: profit >= 0 ? c.green : c.red }} className="num text-lg lg:text-2xl font-bold">{money(profit)}</span>, sub: (paper?.settled ?? 0) + " settled" },
        ].map((t, i) => (
          <div key={t.label} style={{ borderLeft: i ? "1px solid " + c.border : "none" }} className="px-1.5 lg:px-5 py-3.5 lg:py-4 min-w-0 flex flex-col items-center text-center">
            <p style={{ color: c.textMuted, letterSpacing: "0.1em" }} className="text-[9px] lg:text-[10px] font-semibold uppercase leading-none truncate max-w-full">{t.label}</p>
            <div className="h-7 lg:h-9 mt-2 flex items-center justify-center max-w-full overflow-hidden [&_*]:leading-none">{t.node}</div>
            <p style={{ color: c.textMuted }} className="text-[10px] lg:text-[11px] leading-none mt-1.5 truncate max-w-full">{t.sub}</p>
          </div>
        ))}
      </div>

      {opps.loading && <Loading />}
      {opps.error && <ErrorBox error={opps.error} onRetry={opps.reload} />}
      {!opps.loading && !opps.error && list.length === 0 && <Empty>{emptyPicksMessage(opps.data)}</Empty>}

      <div className="lg:grid lg:grid-cols-[1.35fr_1fr] lg:gap-6">
        <div>
          {top && <div className="mb-6"><BestOpportunity o={top} onOpen={onOpen} /></div>}
          {list.length > 1 && (
            <>
              <SectionLabel action="View all" onAction={() => nav("opportunities")}>Top opportunities</SectionLabel>
              <div className="flex flex-col gap-3 mb-6">
                {list.slice(1, 4).map((o) => <OpportunityCard key={oppKey(o)} o={o} onClick={onOpen} />)}
              </div>
            </>
          )}
        </div>
        <div>
          <SectionLabel>Paper performance</SectionLabel>
          <div style={card} className="rounded-2xl p-5 mb-6">
            <p style={{ color: c.textMuted, letterSpacing: "0.12em" }} className="text-[10px] font-semibold uppercase mb-2">Tracked paper bets</p>
            <p style={{ color: profit >= 0 ? c.text : c.red }} className="num text-4xl font-bold tracking-tight mb-5">{money(profit)}</p>
            <div className="grid grid-cols-3 gap-3">
              <Metric label="Open" value={String(paper?.open ?? 0)} />
              <Metric label="Settled" value={String(paper?.settled ?? 0)} />
              <Metric label="ROI" value={paper?.roi_pct == null ? "—" : pct(paper.roi_pct)} tone={(paper?.roi_pct || 0) >= 0 ? c.green : c.red} />
            </div>
            <button onClick={() => nav("bets")} style={{ color: c.green }} className="text-xs font-semibold mt-5 flex items-center gap-1">Open my bets <ChevronRight size={14} /></button>
          </div>
          <SectionLabel>Snapshot</SectionLabel>
          <div style={card} className="rounded-2xl p-5 mb-2 grid grid-cols-2 gap-5">
            <Metric label="Highest-rated league" value={topLeague ? topLeague[0] : "—"} />
            <Metric label="FTA hits (paper)" value={String(paper?.fta_hits ?? 0)} tone={c.green} />
            <Metric label="Paper staked" value={money(paper?.staked || 0)} />
            <Metric label="Picks above average" value={String(list.filter((o) => (o.fta_pct || 0) > 2).length)} />
          </div>
        </div>
      </div>
      <Disclaimer />
    </PageShell>
  );
}

function clockTime(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return isNaN(d.getTime()) ? null : d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

// Re-prices the next 24h of games. The server shares one refresh between all users
// (15-min cooldown), so a press during it just says when prices were last checked.
function RefreshOddsButton({ opps }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);
  const updated = clockTime(opps.data?.odds_updated_at);

  const run = async () => {
    setBusy(true);
    setNote(null);
    try {
      let st = await api.refreshOdds();
      if (!st.started && st.reason === "cooldown") {
        const mins = Math.max(1, Math.ceil((st.retry_after_s || 0) / 60));
        setNote(`Odds were just updated — next refresh available in ${mins} min.`);
        return;
      }
      if (!st.started && st.reason === "daily_limit") {
        setNote("Odds refresh limit reached for today — prices still update automatically.");
        return;
      }
      for (let i = 0; i < 60 && (st.started || st.running); i++) {
        await new Promise((r) => setTimeout(r, 3000));
        st = await api.oddsRefreshStatus();
        if (!st.running) break;
      }
      if (st.error) setNote(st.error);
      else if (st.last) setNote(`Updated prices for ${st.last.saved} game${st.last.saved === 1 ? "" : "s"}.`);
      opps.reload();
    } catch (e) {
      setNote(e.message || "Couldn't refresh odds");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mb-4">
      <div className="flex items-center justify-between gap-3">
        <span style={{ color: c.textSecondary }} className="text-xs">
          {updated ? `Odds checked ${updated}` : "Odds not checked yet"}
        </span>
        <button onClick={run} disabled={busy} style={{ background: c.card, border: "1px solid " + c.border, color: c.cyan, opacity: busy ? 0.6 : 1 }} className="flex items-center gap-1 text-xs font-medium px-3 py-2 rounded-full">
          <RefreshCw size={12} className={busy ? "animate-spin" : ""} /> {busy ? "Refreshing…" : "Refresh odds"}
        </button>
      </div>
      {note && <p style={{ color: c.textSecondary }} className="text-xs mt-2">{note}</p>}
    </div>
  );
}

// Pick the bookmakers you can bet with; every pick then shows the best back price
// among only those. Saved to the account (prefs.bookmakers), [] = any UK bookmaker.
function BookmakerFilter({ opps }) {
  const { reloadMe } = useContext(Account);
  const [open, setOpen] = useState(false);
  const [available, setAvailable] = useState(null);
  const [priced, setPriced] = useState([]);
  const [selected, setSelected] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const current = opps.data?.bookmakers || [];

  const toggleOpen = async () => {
    if (open) return setOpen(false);
    setOpen(true);
    setError(null);
    try {
      const r = await api.oddsBookmakers();
      setAvailable(r.available || []);
      setPriced(r.priced || r.available || []);
      setSelected(r.selected || []);
    } catch (e) {
      setError(e.message || "Couldn't load bookmakers");
    }
  };
  const flip = (name) =>
    setSelected((sel) => (sel.includes(name) ? sel.filter((b) => b !== name) : [...sel, name]));
  const save = async (list) => {
    setSaving(true);
    try {
      await api.patchPrefs({ bookmakers: list });
      setOpen(false);
      opps.reload();
      reloadMe && reloadMe();
    } catch (e) {
      setError(e.message || "Couldn't save");
    } finally {
      setSaving(false);
    }
  };
  const label = current.length === 0 ? "All bookmakers" : current.length === 1 ? current[0] : `${current.length} bookmakers`;

  return (
    <div className="mb-4">
      <button onClick={toggleOpen} style={{ background: c.card, border: "1px solid " + (open ? c.cyan : c.border) }} className="w-full flex items-center justify-between rounded-xl px-4 py-3">
        <span className="text-left">
          <span style={{ color: c.textSecondary }} className="block text-xs">Best price from</span>
          <span style={{ color: c.text }} className="text-sm font-medium">{label}</span>
        </span>
        <ChevronDown size={16} style={{ color: c.textSecondary, transform: open ? "rotate(180deg)" : "none" }} />
      </button>
      {open && (
        <div style={card} className="rounded-xl p-3 mt-2">
          <p style={{ color: c.textSecondary }} className="text-xs mb-3">Tick the bookmakers you have accounts with. Leave all unticked to use any UK bookmaker. "No prices yet" means our odds feed hasn't quoted them for upcoming games.</p>
          {available === null && !error && <p style={{ color: c.textSecondary }} className="text-xs py-2">Loading…</p>}
          <div className="grid grid-cols-2 gap-2">
            {(available || []).map((name) => {
              const on = selected.includes(name);
              const live = priced.includes(name);
              return (
                <button key={name} onClick={() => flip(name)} style={chip(on)} className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-left min-w-0">
                  <span style={{ border: "1px solid " + (on ? c.green : c.textMuted) }} className="w-4 h-4 rounded flex items-center justify-center flex-shrink-0">{on && <Check size={12} />}</span>
                  <span className="min-w-0">
                    <span style={{ color: on ? c.green : c.text }} className="block truncate font-medium">{name}</span>
                    <span style={{ color: live ? c.green : c.textMuted }} className="block text-[10px]">{live ? "● prices now" : "no prices yet"}</span>
                  </span>
                </button>
              );
            })}
          </div>
          {error && <p style={{ color: c.red }} className="text-xs mt-2">{error}</p>}
          <div className="flex gap-2 mt-3">
            <button onClick={() => save([])} disabled={saving} style={{ border: "1px solid " + c.border, color: c.textSecondary }} className="flex-1 rounded-lg py-2 text-xs font-medium">Any bookmaker</button>
            <button onClick={() => save(selected)} disabled={saving || available === null} style={primaryBtn} className="flex-1 rounded-lg py-2 text-xs font-semibold">{saving ? "Saving…" : "Save"}</button>
          </div>
        </div>
      )}
    </div>
  );
}

// Why the 24h list is empty: no games at all, or games that don't reach the floor.
function emptyPicksMessage(data) {
  const games = data?.games_in_window || 0;
  if (games > 0) {
    const best = data?.best_fta_in_window;
    return `${games} game${games === 1 ? "" : "s"} kick off in the next 24 hours, but none reach ${MIN_FTA}% FTA` +
      (best ? ` (best is ${Number(best).toFixed(2)}%).` : ".");
  }
  const next = data?.next_kickoff ? formatKickoff(data.next_kickoff) : null;
  return "No games in our leagues kick off in the next 24 hours." + (next ? ` Next kick-off: ${next}.` : "");
}

function OpportunitiesPage({ nav, entitled, opps, onOpen, onPurchased }) {
  const [league, setLeague] = useState("All leagues");
  const list = opps.data?.opportunities || [];
  const leagues = ["All leagues", ...Array.from(new Set(list.map((o) => o.league).filter(Boolean))).sort()];
  const filtered = list.filter((o) => league === "All leagues" || o.league === league);

  return (
    <PageShell activeTab="opportunities" onNavigate={nav} entitled={entitled}>
      <PageTitle
        title="Opportunities"
        subtitle={<>Games in the next 24 hours, ranked by FTA chance — the team goes 2 goals up <i>and</i> fails to win. The average is about 2%; we only show picks at {MIN_FTA}% or above.</>}
      />
      {entitled && !opps.needsPro && (
        <div className="lg:grid lg:grid-cols-2 lg:gap-4">
          <BookmakerFilter opps={opps} />
          <RefreshOddsButton opps={opps} />
        </div>
      )}
      {(opps.needsPro || !entitled) && <Paywall title="Opportunities is a Pro feature" onPurchased={onPurchased} />}
      {entitled && opps.loading && <Loading />}
      {entitled && opps.error && <ErrorBox error={opps.error} onRetry={opps.reload} />}
      {entitled && opps.data && (
        <>
          <div className="no-scrollbar flex gap-2 overflow-x-auto mb-5 -mx-1 px-1">
            {leagues.map((lg) => (
              <button key={lg} onClick={() => setLeague(lg)} style={chip(lg === league)} className="flex-shrink-0 text-xs font-semibold px-3.5 py-2 rounded-lg whitespace-nowrap">
                {lg}
              </button>
            ))}
          </div>
          {filtered.length > 0 && (
            <div className="hidden lg:block mb-2"><OpportunityTable list={filtered} onOpen={onOpen} /></div>
          )}
          <div className="flex flex-col gap-3 lg:hidden">
            {filtered.map((o, i) => <OpportunityCard key={oppKey(o)} o={o} onClick={onOpen} highlight={i === 0 && league === "All leagues"} />)}
          </div>
          {filtered.length === 0 && <Empty>{list.length === 0 ? emptyPicksMessage(opps.data) : "No opportunities match this filter right now."}</Empty>}
        </>
      )}
      <Disclaimer />
    </PageShell>
  );
}

function hunterTone(score) {
  if (score >= 70) return c.green;
  if (score >= 50) return c.cyan;
  return c.textSecondary;
}

function ScoreBox({ value, label, tone, highlight, tag }) {
  return (
    <div style={{ background: highlight ? "rgba(54,233,143,0.08)" : "rgba(255,255,255,0.02)", border: "1px solid " + (highlight ? "rgba(54,233,143,0.40)" : c.border) }} className="rounded-xl w-[112px] py-3 flex flex-col items-center justify-center flex-shrink-0">
      <span className="flex items-baseline leading-none">
        <span style={{ color: tone }} className="num text-[34px] font-bold leading-none">{value == null ? "—" : Number(value).toFixed(0)}</span>
        <span style={{ color: c.textMuted }} className="num text-xs font-semibold ml-0.5">/100</span>
      </span>
      <p style={{ color: tag ? tone : c.textMuted, letterSpacing: "0.1em" }} className="text-[9px] font-bold uppercase leading-none mt-2 text-center">{tag || label}</p>
    </div>
  );
}

function Bar({ label, value, tone, max = 100, right }) {
  const w = Math.max(2, Math.min(100, ((value || 0) / max) * 100));
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1.5">
        <span style={{ color: c.textMuted, letterSpacing: "0.08em" }} className="text-[10px] font-semibold uppercase">{label}</span>
        <span style={{ color: c.text }} className="num text-xs font-semibold">{right ?? Math.round(value || 0) + "%"}</span>
      </div>
      <div style={{ background: "rgba(255,255,255,0.05)" }} className="h-1.5 rounded-full overflow-hidden">
        <div style={{ width: w + "%", background: tone, boxShadow: "0 0 8px " + tone + "66" }} className="h-full rounded-full" />
      </div>
    </div>
  );
}

function FixtureHead({ f }) {
  const k = kickoffParts(f.kickoff);
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-baseline gap-2">
        <span style={{ color: c.text }} className="num text-sm font-bold">{k.time}</span>
        <span style={{ color: c.textMuted }} className="text-xs">{k.day}</span>
      </span>
      <span style={{ color: c.textMuted, letterSpacing: "0.06em" }} className="text-[10px] font-semibold uppercase truncate">{f.league}</span>
    </div>
  );
}

function FeatureList({ q, ranked, empty, render }) {
  return (
    <>
      {q.loading && <Loading />}
      {q.error && <ErrorBox error={q.error} onRetry={q.reload} />}
      {q.data && ranked.length === 0 && <Empty>{empty}</Empty>}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">{ranked.map(render)}</div>
    </>
  );
}

function EarlyGoalHunterPage({ nav, entitled, onPurchased }) {
  const q = useApi(() => api.earlyGoal(), [entitled]);
  const ranked = [...(q.data?.matches || [])].sort((a, b) => b.hunter_score - a.hunter_score);
  return (
    <PageShell activeTab="early-goal-hunter" onNavigate={nav} entitled={entitled}>
      <PageTitle title="Early Goal Hunter" subtitle={`Games in the next 24 hours most likely to see an early goal — and which side is likelier to strike first. Hunter score ${MIN_SCORE}/100 and above.`} />
      {q.needsPro && <Paywall onPurchased={onPurchased} />}
      <FeatureList q={q} ranked={ranked} empty={`Nothing scores ${MIN_SCORE}/100 or above in the next 24 hours.`} render={(f, i) => {
        const home = (f.p_home_scores_first || 0) * 100;
        const away = (f.p_away_scores_first || 0) * 100;
        const split = home + away > 0 ? (home / (home + away)) * 100 : 50;
        return (
          <div key={f.match_id || f.match} style={i === 0 ? accentCard : card} className="rounded-xl p-4 flex flex-col gap-4">
            <FixtureHead f={f} />
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p style={{ color: c.text }} className="text-base font-semibold truncate">{f.home_team}</p>
                <p style={{ color: c.textSecondary }} className="text-sm truncate"><span style={{ color: c.textMuted }}>vs</span> {f.away_team}</p>
              </div>
              <ScoreBox value={f.hunter_score} label="Hunter score" tone={hunterTone(f.hunter_score)} highlight={i === 0} />
            </div>
            <Bar label="Goal in first half" value={(f.p_first_half_goal || 0) * 100} tone={c.green} />
            <div>
              <div className="flex items-baseline justify-between mb-1.5">
                <span style={{ color: c.textMuted, letterSpacing: "0.08em" }} className="text-[10px] font-semibold uppercase">Scores first</span>
                {Math.round(100 - home - away) > 0 && <span style={{ color: c.textMuted }} className="num text-[10px]">{Math.round(100 - home - away)}% no goal</span>}
              </div>
              <div className="flex h-1.5 rounded-full overflow-hidden gap-[2px]">
                <div style={{ width: split + "%", background: c.cyan }} />
                <div style={{ width: 100 - split + "%", background: c.blue }} />
              </div>
              <div className="flex items-center justify-between mt-1.5 text-xs">
                <span className="truncate" style={{ color: c.textSecondary }}><span style={{ color: c.cyan }} className="num font-semibold">{Math.round(home)}%</span> {f.home_team}</span>
                <span className="truncate text-right" style={{ color: c.textSecondary }}>{f.away_team} <span style={{ color: c.blue }} className="num font-semibold">{Math.round(away)}%</span></span>
              </div>
            </div>
          </div>
        );
      }} />
      <Disclaimer />
    </PageShell>
  );
}

const CHAOS_COLORS = { o2_5: c.green, btts: c.cyan, early_goal: c.orange, instability: c.red };
const CHAOS_LABELS = { o2_5: "Over 2.5 goals", btts: "Both teams score", early_goal: "Early goal", instability: "Instability" };
function chaosLabelTone(label) {
  const l = String(label || "").toLowerCase();
  if (l.includes("high")) return c.red;
  if (l.includes("medium")) return c.orange;
  return c.cyan;
}

function ChaosFactorPage({ nav, entitled, onPurchased }) {
  const q = useApi(() => api.chaos(), [entitled]);
  const ranked = [...(q.data?.matches || [])].sort((a, b) => b.chaos_index - a.chaos_index);
  return (
    <PageShell activeTab="chaos-factor" onNavigate={nav} entitled={entitled}>
      <PageTitle title="Chaos Factor" subtitle={`How unpredictable the next 24 hours' games look: goals, both teams scoring, early goals and instability in one index. Chaos ${MIN_SCORE}/100 and above.`} />
      {q.needsPro && <Paywall onPurchased={onPurchased} />}
      <FeatureList q={q} ranked={ranked} empty={`Nothing scores ${MIN_SCORE}/100 or above in the next 24 hours.`} render={(f, i) => {
        const raw = f.pie || f.components || {};
        const parts = Array.isArray(raw)
          ? raw.map((e) => ({ key: e.key || e.name, value: Number(e.value) || 0 }))
          : Object.entries(raw).map(([key, value]) => ({ key, value: Number(value) || 0 }));
        const max = Math.max(...parts.map((p) => p.value), 1);
        const tone = chaosLabelTone(f.chaos_label);
        return (
          <div key={f.match_id || f.match} style={i === 0 ? accentCard : card} className="rounded-xl p-4 flex flex-col gap-4">
            <FixtureHead f={f} />
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p style={{ color: c.text }} className="text-base font-semibold truncate">{f.home_team}</p>
                <p style={{ color: c.textSecondary }} className="text-sm truncate"><span style={{ color: c.textMuted }}>vs</span> {f.away_team}</p>
              </div>
              <ScoreBox value={f.chaos_index} tone={tone} tag={(f.chaos_label || "") + " chaos"} highlight={i === 0} />
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-3">
              {parts.map((p) => (
                <Bar key={p.key} label={CHAOS_LABELS[p.key] || p.key} value={p.value} max={max} tone={CHAOS_COLORS[p.key] || c.textSecondary} right={p.value.toFixed(1) + "%"} />
              ))}
            </div>
          </div>
        );
      }} />
      <Disclaimer />
    </PageShell>
  );
}

function LiveMonitorPage({ nav, entitled }) {
  return (
    <PageShell activeTab="live" onNavigate={nav} entitled={entitled}>
      <PageTitle title="Live monitor" />
      <div style={card} className="rounded-2xl p-6 text-center">
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
  const [editing, setEditing] = useState(null);
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
        <h1 style={{ color: c.text }} className="text-[26px] lg:text-3xl font-bold tracking-tight">My bets <span style={{ color: c.textMuted }} className="text-base font-medium">paper</span></h1>
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
          <div style={(summary.total_profit || 0) >= 0 ? heroCard : card} className="rounded-2xl p-5 mb-3">
            <p style={{ color: c.textMuted, letterSpacing: "0.12em" }} className="text-[10px] font-semibold uppercase mb-2">Paper profit</p>
            <p style={{ color: (summary.total_profit || 0) >= 0 ? c.text : c.red }} className="num text-4xl font-bold tracking-tight mb-4">{money(summary.total_profit || 0)}</p>
            <div className="grid grid-cols-3 gap-3">
              <Metric label="ROI" value={summary.roi_pct == null ? "—" : pct(summary.roi_pct)} tone={(summary.roi_pct || 0) >= 0 ? c.green : c.red} />
              <Metric label="Bets" value={String(summary.total ?? bets.length)} />
              <Metric label="FTA hits" value={String(summary.fta_hits ?? 0)} tone={c.green} />
            </div>
          </div>
          <button onClick={() => setShowGraph(!showGraph)} style={card} className="w-full rounded-xl px-4 py-3 flex items-center justify-between mb-3">
            <span style={{ color: c.text }} className="text-sm font-medium">Profit graph</span>
            <ChevronRight size={18} style={{ color: c.textSecondary, transform: showGraph ? "rotate(90deg)" : "none" }} />
          </button>
          {showGraph && (
            <div style={card} className="rounded-xl p-3 mb-3">
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

          <div style={card} className="flex rounded-xl p-1 mb-5">
            <button onClick={() => setTab("open")} style={chip(tab === "open")} className="flex-1 text-sm font-semibold py-2 rounded-lg">Open ({open.length})</button>
            <button onClick={() => setTab("settled")} style={{ ...chip(tab === "settled"), marginLeft: 4 }} className="flex-1 text-sm font-semibold py-2 rounded-lg">Settled ({settled.length})</button>
          </div>
          <div className="flex flex-col gap-3">
            {(tab === "open" ? open : settled).map((b) => <BetRow key={b.id} b={b} onClick={() => setEditing(b)} />)}
            {(tab === "open" ? open : settled).length === 0 && (
              <Empty>{tab === "open" ? "No open bets. Track one from an opportunity." : "Nothing settled yet."}</Empty>
            )}
          </div>
          <p style={{ color: c.textMuted }} className="text-[11px] text-center mt-3">Tap a bet to edit, settle or delete it.</p>
        </>
      )}
      <BetEditSheet bet={editing} onClose={() => setEditing(null)} onChanged={() => { setEditing(null); q.reload(); reloadMe(); }} />
      <Disclaimer />
    </PageShell>
  );
}

function BetRow({ b, onClick }) {
  const isOpen = b.status === "open";
  const tone = isOpen ? c.cyan : resultTone(b.result);
  const dateStr = (iso) => (iso ? new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");
  const value = isOpen ? b.expected_profit : Number(b.actual_profit || 0);
  return (
    <button onClick={onClick} style={{ ...card, textAlign: "left" }} className="w-full rounded-xl p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <span style={{ color: c.textMuted, letterSpacing: "0.06em" }} className="text-[10px] font-semibold uppercase truncate">{b.league || "—"} · {b.product === "fta" ? "FTA" : b.product}</span>
        <span style={{ color: tone, border: "1px solid " + tone + "66", background: tone + "14", letterSpacing: "0.08em" }} className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-md flex-shrink-0">{isOpen ? "Open" : resultLabel(b.result)}</span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p style={{ color: c.text }} className="text-base font-semibold truncate">{b.home_team} <span style={{ color: c.textMuted }} className="font-normal">vs</span> {b.away_team}</p>
          <p style={{ color: c.textMuted }} className="text-xs mt-0.5 truncate">2-up team <span style={{ color: c.green }}>{b.team}</span></p>
        </div>
        <div className="text-right flex-shrink-0">
          <p style={{ color: isOpen ? c.textSecondary : value >= 0 ? c.green : c.red }} className="num text-lg font-bold">{value == null ? "—" : money(value)}</p>
          <p style={{ color: c.textMuted }} className="text-[10px] uppercase tracking-wider">{isOpen ? "Expected" : "Profit"}</p>
        </div>
      </div>
      <div style={{ borderTop: "1px solid " + c.border }} className="flex items-center justify-between pt-3 text-xs">
        <span style={{ color: c.textSecondary }} className="num">£{Number(b.stake || 0).toFixed(2)} @ <span style={{ color: c.green }} className="font-semibold">{b.back_odds ? Number(b.back_odds).toFixed(2) : "—"}</span>{b.lay_odds ? <> · lay <span style={{ color: c.cyan }} className="font-semibold">{Number(b.lay_odds).toFixed(2)}</span></> : null}</span>
        <span style={{ color: c.textMuted }}>{isOpen ? "Opened " + dateStr(b.created_at) : "Settled " + dateStr(b.settled_at)}</span>
      </div>
    </button>
  );
}

function BetEditSheet({ bet, onClose, onChanged }) {
  const [form, setForm] = useState(null);
  const [lastId, setLastId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState(null);
  if (bet && bet.id !== lastId) {
    setLastId(bet.id);
    setForm({
      stake: String(bet.stake ?? ""), back_odds: bet.back_odds ? Number(bet.back_odds).toFixed(2) : "",
      lay_odds: bet.lay_odds ? Number(bet.lay_odds).toFixed(2) : "", commission: String(bet.commission ?? 2),
      bookmaker: bet.bookmaker || "",
    });
    setConfirmDelete(false);
    setError(null);
  }
  if (!bet || !form) return null;
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));
  const run = async (fn) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onChanged();
    } catch (e) {
      setError(e.message || "Something went wrong");
    } finally {
      setBusy(false);
    }
  };
  const save = () => run(() => api.editTracked(bet.id, {
    stake: parseFloat(form.stake) || undefined, back_odds: parseFloat(form.back_odds) || undefined,
    lay_odds: parseFloat(form.lay_odds) || undefined, commission: form.commission === "" ? undefined : parseFloat(form.commission),
    bookmaker: form.bookmaker || undefined,
  }));
  const isOpen = bet.status === "open";
  return (
    <Sheet open onClose={onClose}>
      <p style={{ color: c.textMuted, letterSpacing: "0.12em" }} className="text-[10px] font-semibold uppercase mb-2">Edit tracked bet</p>
      <p style={{ color: c.text }} className="text-xl font-bold tracking-tight leading-tight">{bet.home_team} <span style={{ color: c.textMuted }} className="font-medium">vs</span> {bet.away_team}</p>
      <p style={{ color: c.textSecondary }} className="text-sm mt-1 mb-5">2-up team <span style={{ color: c.green }}>{bet.team}</span> · {isOpen ? "open" : resultLabel(bet.result)}</p>

      <SectionLabel>Your bet</SectionLabel>
      <div className="grid grid-cols-2 gap-2 mb-2">
        <NumField label="Stake" prefix="£" value={form.stake} onChange={set("stake")} step="1" />
        <NumField label="Commission %" value={form.commission} onChange={set("commission")} step="0.1" />
        <NumField label="Back odds" value={form.back_odds} onChange={set("back_odds")} tone={c.green} />
        <NumField label="Lay odds" value={form.lay_odds} onChange={set("lay_odds")} tone={c.cyan} />
      </div>
      <label style={card} className="rounded-xl px-3 py-2.5 block mb-2">
        <span style={{ color: c.textMuted, letterSpacing: "0.08em" }} className="block text-[10px] font-semibold uppercase mb-1">Bookmaker</span>
        <input value={form.bookmaker} onChange={(e) => set("bookmaker")(e.target.value)} maxLength={40} style={{ background: "transparent", color: c.text, width: "100%" }} className="text-base font-semibold" />
      </label>
      {!isOpen && <p style={{ color: c.textMuted }} className="text-[11px] mb-2">The result stays the same; profit is recalculated with the corrected prices.</p>}
      <button disabled={busy} onClick={save} style={{ ...primaryBtn, opacity: busy ? 0.6 : 1 }} className="w-full rounded-xl py-3 text-sm font-semibold mt-2 mb-6">
        {busy ? "Saving…" : "Save changes"}
      </button>

      {isOpen && (
        <>
          <SectionLabel>Settle manually</SectionLabel>
          <div className="grid grid-cols-2 gap-2 mb-6">
            <button disabled={busy} onClick={() => run(() => api.settleTracked(bet.id, "fta"))} style={chip(false)} className="rounded-xl py-3 text-xs font-semibold">
              <span style={{ color: c.green }}>Went 2 up, no win</span>
            </button>
            <button disabled={busy} onClick={() => run(() => api.settleTracked(bet.id, "no_fta"))} style={chip(false)} className="rounded-xl py-3 text-xs font-semibold">
              Any other result
            </button>
          </div>
        </>
      )}

      <button disabled={busy} onClick={() => (confirmDelete ? run(() => api.deleteTracked(bet.id)) : setConfirmDelete(true))} style={{ color: c.red, border: "1px solid " + (confirmDelete ? c.red : "rgba(255,82,82,0.35)"), background: confirmDelete ? "rgba(255,82,82,0.10)" : "transparent" }} className="w-full rounded-xl py-3 text-sm font-semibold">
        {confirmDelete ? "Tap again to delete for good" : "Delete bet"}
      </button>
      {error && <p style={{ color: c.red }} className="text-xs text-center mt-3">{error}</p>}
    </Sheet>
  );
}

const CALC_MODES = [
  { key: "qualifying", label: "2UP bet" },
  { key: "snr", label: "Free bet (SNR)" },
  { key: "sr", label: "Free bet (SR)" },
];

function CalcField({ label, value, onChange, tone, prefix }) {
  return (
    <div style={card} className="rounded-xl p-3">
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
        <div style={card} className="rounded-xl p-4 mb-4">
          <OutputRow label="Lay stake" value={"£" + ls.toFixed(2)} tone={c.cyan} />
          <OutputRow label="Liability" value={"£" + calcLiability(l, ls).toFixed(2)} tone={c.orange} />
          <OutputRow label="Qualifying loss" value={money(ql)} tone={ql >= 0 ? c.green : c.red} />
        </div>
        <div style={card} className="rounded-xl p-4">
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
      <div style={card} className="rounded-xl p-4">
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
        <h1 style={{ color: c.text }} className="text-[26px] lg:text-3xl font-bold tracking-tight">Calculator</h1>
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
    case "beta": return { text: "Free beta until " + betaDate(me), tone: c.green };
    case "cancelled": return { text: "Cancelled — access until " + dateStr, tone: c.orange };
    case "billing_issue": return { text: "Payment problem — update it in your store account", tone: c.red };
    case "expired": return { text: "Expired", tone: c.red };
    case "refund":
    case "revoke": return { text: "Subscription revoked", tone: c.red };
    default: return { text: "Status unknown — contact support", tone: c.textSecondary };
  }
}

function SettingsPage({ nav, entitled, me, userId, onPurchased, reloadMe, onSignedOut }) {
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
  const deleteAccount = async () => {
    const warn = me?.paid
      ? "Cancel your subscription first (Manage subscription) — deleting your account does not stop payments.\n\n"
      : "";
    if (!window.confirm(warn + "Delete your account and all its data? This can't be undone.")) return;
    try {
      await api.deleteMe();
      await signOut();
      onSignedOut();
    } catch (e) {
      window.alert(e.message || "Couldn't delete the account");
    }
  };

  return (
    <PageShell activeTab="menu" onNavigate={nav} entitled={entitled}>
      <PageTitle title="Settings" />

      <div style={card} className="rounded-2xl p-4 mb-5 flex items-center gap-3">
        <div style={{ background: c.cardAlt, border: "1px solid " + c.border }} className="w-11 h-11 rounded-full flex items-center justify-center flex-shrink-0">
          <User size={18} style={{ color: c.textSecondary }} />
        </div>
        <div className="flex-1 min-w-0">
          <p style={{ color: c.text }} className="text-sm font-medium truncate">{me?.email || (entitled ? "TurnaroundIQ Pro" : "Free account")}</p>
          <p style={{ color: status.tone }} className="text-xs truncate">{status.text}</p>
        </div>
      </div>

      <p style={{ color: c.textSecondary }} className="text-[11px] font-semibold uppercase tracking-wider mb-2">Subscription</p>
      <div style={card} className="rounded-xl px-4 mb-5">
        {isBeta(me) && me?.purchase_url ? (
          <button onClick={() => openWebCheckout(me.purchase_url)} style={{ borderBottom: "1px solid " + c.border }} className="w-full flex items-center gap-3 py-3 text-left">
            <CreditCard size={18} style={{ color: c.green }} />
            <span style={{ color: c.text }} className="text-sm flex-1">
              Subscribe{me.beta.founder_price ? " — " + me.beta.founder_price + "/month founding price" : ""}
            </span>
            <ChevronRight size={16} style={{ color: c.textSecondary }} />
          </button>
        ) : entitled && (isNative || me?.management_url) ? (
          <button onClick={() => manageSubscription(me?.management_url)} style={{ borderBottom: "1px solid " + c.border }} className="w-full flex items-center gap-3 py-3 text-left">
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
        {isNative ? (
          <button disabled={busy} onClick={doRestore} className="w-full flex items-center gap-3 py-3 text-left">
            <RotateCcw size={18} style={{ color: c.textSecondary }} />
            <span style={{ color: c.text }} className="text-sm flex-1">{busy ? "Restoring…" : "Restore purchases"}</span>
          </button>
        ) : (
          <button onClick={async () => { await signOut(); onSignedOut(); }} className="w-full flex items-center gap-3 py-3 text-left">
            <LogOut size={18} style={{ color: c.red }} />
            <span style={{ color: c.text }} className="text-sm flex-1">Sign out</span>
          </button>
        )}
        {!isNative && (
          <button onClick={deleteAccount} className="w-full flex items-center gap-3 py-3 text-left" style={{ borderTop: "1px solid " + c.border }}>
            <X size={18} style={{ color: c.red }} />
            <span style={{ color: c.red }} className="text-sm flex-1">Delete account</span>
          </button>
        )}
      </div>

      <p style={{ color: c.textSecondary }} className="text-[11px] font-semibold uppercase tracking-wider mb-2">Trading preferences</p>
      <div style={card} className="rounded-xl p-4 mb-5 flex flex-col gap-4">
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
        <button onClick={save} style={primaryBtn} className="rounded-xl py-2.5 text-sm font-semibold">Save preferences</button>
        {saved && <p style={{ color: saved === "Saved" ? c.green : c.red }} className="text-xs text-center">{saved}</p>}
      </div>

      <p style={{ color: c.textSecondary }} className="text-[11px] font-semibold uppercase tracking-wider mb-2">About</p>
      <div style={card} className="rounded-xl p-4 mb-5 flex flex-col gap-2">
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
        <p style={{ color: c.textSecondary }} className="text-[11px] break-all">Support ID: {me?.app_user_id || (isNative ? userId : "—")}</p>
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
      <p style={{ color: c.text }} className="text-2xl font-semibold tracking-tight mb-1">Model testing (dev)</p>
      <p style={{ color: c.textSecondary }} className="text-sm mb-4">Training runs from {API_BASE}. Only ADMIN_USER_IDS can see this.</p>
      {q.loading && <Loading />}
      {(q.error || q.needsPro) && <ErrorBox error={q.error || "Not authorised — add your Support ID to ADMIN_USER_IDS on the server."} onRetry={q.reload} />}
      {q.data && runs.length === 0 && <Empty>No training runs logged yet.</Empty>}
      {runs.length > 0 && (
        <>
          <div style={card} className="rounded-xl p-3 mb-4">
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
              <div key={r.id} style={card} className="rounded-xl p-4">
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
    } catch (e) {
      setMe(null);
      if (!isNative && e instanceof ApiError && e.status === 401) {
        clearSession(); // session expired -> back to sign in
        setUserIdState(null);
      }
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

  const afterSignIn = async () => {
    setUserIdState(await initPurchasesToken());
    await loadMe();
    setPage("dashboard");
  };

  if (booted && !isNative && !userId) {
    return <SignInPage onSignedIn={afterSignIn} />;
  }

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
    stables: <StablesPage {...common} ui={STABLES_UI} />,
    live: <LiveMonitorPage {...common} />,
    bets: <MyBetsPage {...common} reloadMe={loadMe} />,
    calculator: <CalculatorPage {...common} prefs={me?.prefs} />,
    settings: <SettingsPage {...common} me={me} userId={userId} reloadMe={loadMe} onSignedOut={() => { setMe(null); setUserIdState(null); }} />,
    ...(SHOW_DEV_TOOLS ? { "model-testing": <ModelTestingPage {...common} /> } : {}),
  };

  return (
    <Account.Provider value={{ me, reloadMe: loadMe }}>
      {pages[page] || pages.dashboard}
      <OpportunityDetailModal opportunity={selected} onClose={() => setSelected(null)} prefs={me?.prefs} />
    </Account.Provider>
  );
}

// Design system handed to pages that live in their own files (The Stables).
const STABLES_UI = {
  c, card, accentCard, primaryBtn, chip, useApi,
  PageShell, PageTitle, SectionLabel, Paywall, Loading, ErrorBox, Empty, Bar,
};

// After web sign-in the session token is already set on the API client.
async function initPurchasesToken() {
  return getSession();
}
