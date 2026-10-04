/**
 * The Stables: horse racing extra-place value.
 *
 * Kept out of App.jsx so racing work doesn't collide with football edits.
 * App.jsx passes its design system in as `ui` (colours, card styles,
 * PageShell, Paywall, ...), so this page looks like every other page.
 */
import React, { useMemo, useState } from "react";
import { Check, ChevronDown, Info, Plus, RefreshCw, X } from "lucide-react";
import { api } from "../lib/api";

const pct = (v, dp = 1) => (v == null || isNaN(v) ? "—" : (100 * Number(v)).toFixed(dp) + "%");
const signedPct = (v, dp = 1) => (v == null || isNaN(v) ? "—" : (v >= 0 ? "+" : "") + (100 * Number(v)).toFixed(dp) + "%");
const pts = (v) => (v == null || isNaN(v) ? "—" : (v >= 0 ? "+" : "") + (100 * Number(v)).toFixed(1) + " pts");
const fractionLabel = (f) => (f ? "1/" + Math.round(1 / f) : "—");
const UK_FRACTIONS = [[1,5],[2,9],[1,4],[2,7],[3,10],[1,3],[4,11],[2,5],[4,9],[1,2],[8,15],[4,7],[8,13],[4,6],[8,11],[4,5],[5,6],[10,11],[1,1],[11,10],[6,5],[5,4],[11,8],[6,4],[13,8],[7,4],[15,8],[2,1],[9,4],[5,2],[11,4],[3,1],[10,3],[7,2],[4,1],[9,2],[5,1],[11,2],[6,1],[13,2],[7,1],[15,2],[8,1],[17,2],[9,1],[10,1],[11,1],[12,1],[14,1],[16,1],[18,1],[20,1],[22,1],[25,1],[28,1],[33,1],[40,1],[50,1],[66,1],[80,1],[100,1],[125,1],[150,1],[200,1],[250,1],[500,1]];
/** Smallest standard UK price at or above decimal odds d, e.g. 12.57 -> "12/1". */
export function ukPriceAtLeast(d) {
  if (d == null || !isFinite(d)) return null;
  const f = UK_FRACTIONS.find(([a, b]) => 1 + a / b >= d - 1e-9);
  if (!f) return null;
  return f[0] === f[1] ? "evs" : `${f[0]}/${f[1]}`;
}
/** Bookmaker extra-place offers on a race (the engine adds a generic "Best price" one when there are none). */
const realOffers = (race) => (race.offers || []).filter((t) => t.bookmaker !== "Best price");
const shortBook = (b) => (b.length > 9 ? b.slice(0, 8) + "…" : b);
const offerKey = (o) => `${o.race_id || ""}|${o.horse}|${o.bookmaker}`;

/** "9/2", "4.5", "evs", "5-2" -> decimal odds (null if unreadable). */
export function parseOdds(s) {
  const t = String(s || "").trim().toLowerCase();
  if (!t) return null;
  if (t === "evs" || t === "evens") return 2;
  const m = t.match(/^(\d+(?:\.\d+)?)\s*[/-]\s*(\d+(?:\.\d+)?)$/);
  if (m) return Number(m[2]) > 0 ? 1 + Number(m[1]) / Number(m[2]) : null;
  const d = Number(t);
  return isFinite(d) && d > 1 ? d : null;
}

/** One runner per line: "Name  9/2" or "Name, 5.5" -> [{name, odds}] plus unreadable lines. */
export function parseRunners(text) {
  const runners = [];
  const bad = [];
  for (const raw of String(text || "").split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const m = line.match(/^(.*?)[\s,;:]+(evs|evens|\d+(?:\.\d+)?(?:\s*[/-]\s*\d+(?:\.\d+)?)?)$/i);
    const odds = m ? parseOdds(m[2]) : null;
    if (m && m[1].trim() && odds) runners.push({ name: m[1].trim().slice(0, 60), odds: Number(odds.toFixed(3)) });
    else bad.push(line);
  }
  return { runners, bad };
}

function gradeTone(ui, g) {
  const { c } = ui;
  return { A: c.green, B: c.cyan, C: c.orange }[g] || c.textMuted;
}

function GradeBox({ ui, grade, conf, highlight }) {
  const { c } = ui;
  const tone = gradeTone(ui, grade);
  return (
    <div style={{ background: highlight ? "rgba(54,233,143,0.08)" : "rgba(255,255,255,0.02)", border: "1px solid " + (highlight ? "rgba(54,233,143,0.40)" : c.border) }} className="rounded-xl w-[96px] py-3 flex flex-col items-center justify-center flex-shrink-0">
      <span style={{ color: tone }} className="num text-[32px] font-bold leading-none">{grade}</span>
      <p style={{ color: c.textMuted, letterSpacing: "0.1em" }} className="text-[9px] font-bold uppercase leading-none mt-2">Grade · {conf}</p>
    </div>
  );
}

function Metric({ ui, label, value, tone, sub }) {
  const { c } = ui;
  return (
    <div className="min-w-0">
      <p style={{ color: c.textMuted, letterSpacing: "0.08em" }} className="text-[10px] font-semibold uppercase">{label}</p>
      <p style={{ color: tone || c.text }} className="num text-[15px] font-semibold">{value}</p>
      {sub && <p style={{ color: c.textMuted }} className="text-[10px]">{sub}</p>}
    </div>
  );
}

function OpportunityCard({ ui, o, highlight }) {
  const { c, card, accentCard, Bar } = ui;
  const [open, setOpen] = useState(false);
  const stake = o.recommended_stake_pct;
  return (
    <div style={highlight ? accentCard : card} className="rounded-xl p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-baseline gap-2 min-w-0">
          {o.time && <span style={{ color: c.text }} className="num text-sm font-bold">{o.time}</span>}
          {o.course && <span style={{ color: c.textMuted }} className="text-xs truncate">{o.course}</span>}
        </span>
        <span style={{ color: c.textMuted, letterSpacing: "0.06em" }} className="text-[10px] font-semibold uppercase whitespace-nowrap">
          {o.bookmaker} · {o.places_paid} places · {fractionLabel(o.fraction)}
        </span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p style={{ color: c.text }} className="text-base font-semibold truncate">{o.horse}</p>
          <p style={{ color: c.textSecondary }} className="text-sm">
            <span className="num">{Number(o.win_odds).toFixed(2)}</span> win · place pays <span className="num">{Number(o.place_odds).toFixed(2)}</span>
          </p>
          <p style={{ color: c.textMuted }} className="text-xs mt-0.5">
            {o.standard_places} places as standard, {o.places_paid - o.standard_places} extra
          </p>
        </div>
        <GradeBox ui={ui} grade={o.grade} conf={o.confidence} highlight={highlight} />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Metric ui={ui} label={`Top ${o.places_paid}`} value={pct(o.model_probability)} tone={c.green} sub={o.raw_model_probability != null ? `model ${pct(o.raw_model_probability)}, adjusted` : "model"} />
        <Metric ui={ui} label="Book implies" value={pct(o.market_probability)} sub="from place odds" />
        <Metric ui={ui} label="Edge" value={pts(o.edge)} tone={o.robust_edge > 0 ? c.green : c.orange} sub={o.robust_edge > 0 ? "clears the band" : "inside the band"} />
        <Metric ui={ui} label="Each-way EV" value={signedPct(o.each_way_ev)} tone={o.each_way_ev > 0 ? c.green : c.red} sub="per £1 staked" />
        <Metric ui={ui} label="Place EV" value={signedPct(o.place_ev)} sub="place half" />
        <Metric ui={ui} label="¼ Kelly" value={stake > 0 ? stake.toFixed(2) + "%" : "No stake"} tone={stake > 0 ? c.cyan : c.textMuted} sub="of bankroll, EW" />
      </div>
      <button onClick={() => setOpen(!open)} style={{ color: c.textSecondary }} className="flex items-center gap-1 text-xs font-medium self-start">
        <ChevronDown size={14} style={{ transform: open ? "rotate(180deg)" : "none" }} /> {open ? "Hide" : "Positions and confidence"}
      </button>
      {open && (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-x-4 gap-y-3">
            <Bar label="Win" value={100 * o.win_probability} tone={c.green} right={pct(o.win_probability)} />
            <Bar label="Top 3" value={100 * o.top3_probability} tone={c.cyan} right={pct(o.top3_probability)} />
            <Bar label="Top 4" value={100 * o.top4_probability} tone={c.cyan} right={pct(o.top4_probability)} />
            <Bar label="Top 5" value={100 * o.top5_probability} tone={c.cyan} right={pct(o.top5_probability)} />
            <Bar label="Exactly 4th" value={100 * o.p4} max={30} tone={c.orange} right={pct(o.p4)} />
            <Bar label="Exactly 5th" value={100 * o.p5} max={30} tone={c.orange} right={pct(o.p5)} />
            <Bar label="Exactly 6th" value={100 * o.p6} max={30} tone={c.orange} right={pct(o.p6)} />
            <Bar label="Extra places" value={100 * o.extra_place_probability} max={50} tone={c.green} right={pct(o.extra_place_probability)} />
          </div>
          <div className="grid grid-cols-4 gap-2">
            {Object.entries(o.confidence_parts || {}).map(([k, v]) => (
              <Metric key={k} ui={ui} label={k} value={Math.round(v * 100)} sub="/100" />
            ))}
          </div>
          <p style={{ color: c.textMuted }} className="text-[11px] leading-snug">
            Kelly stakes use the low end of the uncertainty band (±{pct(o.uncertainty)}) and are capped at 5% of bankroll.
            ½ Kelly: {o.stakes?.half?.each_way_pct?.toFixed(2)}% · full: {o.stakes?.full?.each_way_pct?.toFixed(2)}% · place-only ¼ Kelly: {o.stakes?.quarter?.place_only_pct?.toFixed(2)}%.
          </p>
        </div>
      )}
    </div>
  );
}

function RunnerTable({ ui, race, extra }) {
  const { c } = ui;
  const th = { color: c.textMuted, letterSpacing: "0.1em" };
  const offers = realOffers(race).slice(0, 3);
  const valueCols = offers.length
    ? offers.map((t) => ({ key: t.bookmaker, label: `${shortBook(t.bookmaker)} ${t.places}pl`, get: (r) => r.offer_value_from?.[t.bookmaker] }))
    : extra != null && race.standard_terms?.fraction > 0
      ? [{ key: "generic", label: "Value from", get: (r) => r.value_from?.[String(extra)] }]
      : [];
  const withValue = valueCols.length > 0;
  const cols = ["Win", "Top 3", "Top 4", "Top 5", "4th", "5th"];
  const hideMobile = (h) => h === "Top 3" || h === "Top 4" || (withValue && (h === "4th" || h === "5th")) || (valueCols.length > 1 && h === "Top 5");
  return (
    <div className="overflow-x-auto -mx-1">
      <table className="w-full text-xs lg:text-sm">
        <thead>
          <tr style={{ borderBottom: "1px solid " + c.border }}>
            <th style={th} className="text-[10px] font-semibold uppercase py-2 px-1 text-left">Runner</th>
            <th style={th} className="text-[10px] font-semibold uppercase py-2 px-1 text-right">Odds</th>
            {cols.map((h) => <th key={h} style={th} className={"text-[10px] font-semibold uppercase py-2 px-1 text-right" + (hideMobile(h) ? " hidden lg:table-cell" : "")}>{h}</th>)}
            {valueCols.map((v) => <th key={v.key} style={{ ...th, color: c.green }} className="text-[10px] font-semibold uppercase py-2 px-1 text-right whitespace-nowrap">{v.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {race.runners.map((r) => {
            const value = race.opportunities.some((o) => o.horse === r.name && (o.grade === "A" || o.grade === "B"));
            const price = r.best_win_odds || r.exchange_back;
            return (
              <tr key={r.name} style={{ borderBottom: "1px solid " + c.border }}>
                <td className="py-2 px-1 max-w-[104px] lg:max-w-[220px] truncate" style={{ color: value ? c.green : c.text }}>{r.number ? <span style={{ color: c.textMuted }} className="num mr-1">{r.number}</span> : null}{r.name}</td>
                <td style={{ color: c.textSecondary }} className="num py-2 px-1 text-right">{price ? Number(price).toFixed(2) : "—"}</td>
                <td style={{ color: c.text }} className="num py-2 px-1 text-right">{pct(r.win_probability)}</td>
                <td style={{ color: c.text }} className="num py-2 px-1 text-right hidden lg:table-cell">{pct(r.top3_probability)}</td>
                <td style={{ color: c.text }} className="num py-2 px-1 text-right hidden lg:table-cell">{pct(r.top4_probability)}</td>
                <td style={{ color: c.text }} className={"num py-2 px-1 text-right" + (hideMobile("Top 5") ? " hidden lg:table-cell" : "")}>{pct(r.top5_probability)}</td>
                <td style={{ color: c.orange }} className={"num py-2 px-1 text-right" + (withValue ? " hidden lg:table-cell" : "")}>{pct(r.positions[3])}</td>
                <td style={{ color: c.orange }} className={"num py-2 px-1 text-right" + (withValue ? " hidden lg:table-cell" : "")}>{pct(r.positions[4])}</td>
                {valueCols.map((v) => {
                  const vf = v.get(r);
                  return (
                    <td key={v.key} style={{ color: vf && price && price >= vf ? c.green : c.textSecondary }} className="num py-2 px-1 text-right whitespace-nowrap font-semibold">
                      {vf ? ukPriceAtLeast(vf) : "—"}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RaceCard({ ui, race, extra, canEdit, onChanged }) {
  const { c, card } = ui;
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const strong = race.opportunities.filter((o) => o.grade === "A" || o.grade === "B").length;
  const offers = realOffers(race);
  const remove = async (bookmaker) => {
    setBusy(true);
    try {
      await api.stablesDeleteOffer(race.race_id, bookmaker);
      onChanged?.();
    } finally {
      setBusy(false);
    }
  };
  return (
    <div style={card} className="rounded-xl p-4">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between gap-3 text-left">
        <div className="min-w-0">
          <p style={{ color: c.text }} className="text-sm font-semibold truncate">
            {race.time && <span className="num mr-2">{race.time}</span>}{race.course || race.name || "Race"}
          </p>
          <p style={{ color: c.textMuted }} className="text-xs truncate">
            {race.field_size} runners{race.handicap ? " · handicap" : ""}{race.going ? " · " + race.going : ""}
            {race.standard_terms?.fraction > 0 ? ` · standard ${race.standard_terms.places} pl ${fractionLabel(race.standard_terms.fraction)}` : " · win only"}
          </p>
        </div>
        <span className="flex items-center gap-2 flex-shrink-0">
          {strong > 0 && <span style={{ color: c.green }} className="text-xs font-semibold">{strong} value</span>}
          <ChevronDown size={16} style={{ color: c.textMuted, transform: open ? "rotate(180deg)" : "none" }} />
        </span>
      </button>
      {offers.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {offers.map((t) => (
            <span key={t.bookmaker} style={{ color: c.green, border: "1px solid rgba(54,233,143,0.35)", background: "rgba(54,233,143,0.06)" }}
              className="text-[11px] font-semibold px-2 py-1 rounded-md flex items-center gap-1.5">
              {t.bookmaker} · {t.places} places {fractionLabel(t.fraction)}
              {canEdit && (
                <button disabled={busy} onClick={() => remove(t.bookmaker)} aria-label={`Remove ${t.bookmaker} offer`} style={{ color: c.textMuted }}>
                  <X size={12} />
                </button>
              )}
            </span>
          ))}
        </div>
      )}
      {open && (
        <div className="mt-3">
          <RunnerTable ui={ui} race={race} extra={extra} />
          {race.standard_terms?.fraction > 0 && (
            <p style={{ color: c.textMuted }} className="text-[11px] mt-2">
              {offers.length
                ? "Value from: the smallest price worth taking each-way with each bookmaker's offer above."
                : `Value from: the smallest bookmaker price worth taking each-way at ${race.standard_terms.places + extra} places, ${fractionLabel(race.standard_terms.fraction)} odds.`}{" "}
              Green where the exchange price is already that big. No value calls on runners over 50/1: in past races the model overrated them.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function ModelNote({ ui, cal, source }) {
  const { c } = ui;
  const fitted = cal?.fitted;
  return (
    <div style={{ border: "1px solid " + c.border }} className="rounded-xl p-3 mb-4 flex gap-2">
      <Info size={14} style={{ color: c.textMuted, flexShrink: 0, marginTop: 2 }} />
      <p style={{ color: c.textSecondary }} className="text-xs leading-snug">
        Win chances come from {source === "exchange" ? "exchange prices" : "bookmaker prices with the margin taken out"}; 10,000 simulated races turn them into a chance for every finishing position.{" "}
        {fitted
          ? `Position model fitted on ${cal.n_races.toLocaleString()} past races.`
          : "Position model is running on published research values and has not been fitted on results yet, so grade A is held back."}
      </p>
    </div>
  );
}

// A/B up front; grade C (positive EV but inside the uncertainty band) behind a toggle.
function OpportunityList({ ui, list }) {
  const { c, SectionLabel, Empty } = ui;
  const [showC, setShowC] = useState(false);
  const strong = list.filter((o) => o.grade === "A" || o.grade === "B");
  const marginal = list.filter((o) => o.grade === "C");
  const shown = showC ? [...strong, ...marginal] : strong;
  return (
    <>
      <SectionLabel>Extra-place value · {strong.length}</SectionLabel>
      {list.length === 0 && <Empty>No runner shows positive each-way value under these terms.</Empty>}
      {list.length > 0 && strong.length === 0 && !showC && (
        <Empty>Nothing clears the uncertainty band. {marginal.length} runner{marginal.length === 1 ? "" : "s"} show a thin positive EV.</Empty>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-3">
        {shown.map((o, i) => <OpportunityCard key={offerKey(o)} ui={ui} o={o} highlight={i === 0 && o.grade !== "C"} />)}
      </div>
      {marginal.length > 0 && (
        <button onClick={() => setShowC(!showC)} style={{ color: c.textSecondary, border: "1px solid " + c.border }} className="w-full rounded-xl py-2.5 text-xs font-medium mb-6">
          {showC ? "Hide grade C" : `Show ${marginal.length} grade C (thin or uncertain edge)`}
        </button>
      )}
      {marginal.length === 0 && <div className="mb-3" />}
    </>
  );
}

// Runners whose exchange price already beats the "value from" line: the ones worth
// checking against bookmakers' extra-place offers.
// Runners whose exchange price already beats the "value from" line: the ones worth
// checking with the bookmaker. Races with entered offers use each bookmaker's real
// terms; other races use the generic "extra places" setting.
function Shortlist({ ui, races, extra }) {
  const { c, card, SectionLabel, Empty } = ui;
  const rows = [];
  for (const race of races) {
    if (!(race.standard_terms?.fraction > 0)) continue;
    const offers = realOffers(race);
    const terms = offers.length
      ? offers.map((t) => ({ book: t.bookmaker, label: `${t.bookmaker} · ${t.places} places ${fractionLabel(t.fraction)}`, get: (r) => r.offer_value_from?.[t.bookmaker] }))
      : [{ book: null, label: `${race.standard_terms.places + extra} places ${fractionLabel(race.standard_terms.fraction)}`, get: (r) => r.value_from?.[String(extra)] }];
    for (const r of race.runners) {
      const price = r.best_win_odds || r.exchange_back;
      // One row per horse: the offer with the lowest value line (the best terms).
      const ok = terms.map((t) => ({ t, vf: t.get(r) })).filter(({ vf }) => vf && price && price >= vf)
        .sort((a, b) => a.vf - b.vf);
      if (ok.length) rows.push({ race, r, vf: ok[0].vf, price, t: ok[0].t, more: ok.length - 1, ratio: price / ok[0].vf });
    }
  }
  rows.sort((a, b) => (b.t.book ? 1 : 0) - (a.t.book ? 1 : 0) || b.ratio - a.ratio);
  const top = rows.slice(0, 15);
  return (
    <>
      <SectionLabel>Worth checking · {rows.length}</SectionLabel>
      <p style={{ color: c.textMuted }} className="text-[11px] -mt-2 mb-3 leading-snug">
        The exchange price already beats the value line. If the bookmaker's price is at or above "value from" on
        those terms, the model rates it value. Races with entered offers come first, on each bookmaker's terms;
        the rest use {extra ? `${extra} extra place${extra > 1 ? "s" : ""}` : "standard terms"}.
      </p>
      {top.length === 0 && <Empty>No runner clears the value line at exchange prices.</Empty>}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2 mb-6">
        {top.map(({ race, r, vf, price, t, more }) => (
          <div key={race.race_id + r.name + (t.book || "")} style={card} className="rounded-xl px-4 py-3 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p style={{ color: c.text }} className="text-sm font-semibold truncate">{r.name}</p>
              <p style={{ color: c.textMuted }} className="text-xs truncate">
                <span className="num">{race.time}</span> {race.course} · <span style={{ color: t.book ? c.green : c.textMuted }}>{t.label}</span>{more > 0 ? ` +${more} more` : ""}
              </p>
            </div>
            <div className="text-right flex-shrink-0">
              <p style={{ color: c.green }} className="num text-sm font-bold">{ukPriceAtLeast(vf)}+</p>
              <p style={{ color: c.textMuted }} className="text-[10px]">exchange <span className="num">{Number(price).toFixed(2)}</span></p>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

const OFFER_PLACES = [2, 3, 4, 5, 6, 7, 8];
const OFFER_FRACTIONS = ["1/4", "1/5", "1/6"];

// Admin form: pick a bookmaker, tick race times by track, set places + fraction.
function OffersPanel({ ui, races, onSaved }) {
  const { c, card, chip, primaryBtn } = ui;
  const [open, setOpen] = useState(false);
  const [book, setBook] = useState("");
  const [places, setPlaces] = useState(4);
  const [fraction, setFraction] = useState("1/5");
  const [sel, setSel] = useState(() => new Set());
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const upcoming = races.filter((r) => !r.started && r.race_id);
  const byCourse = useMemo(() => {
    const m = new Map();
    for (const r of upcoming) {
      const k = r.course || "Other";
      if (!m.has(k)) m.set(k, []);
      m.get(k).push(r);
    }
    for (const list of m.values()) list.sort((a, b) => (a.time || "").localeCompare(b.time || ""));
    return [...m.entries()].sort((a, b) => (a[1][0].time || "").localeCompare(b[1][0].time || ""));
  }, [upcoming]);
  const knownBooks = [...new Set(races.flatMap((r) => realOffers(r).map((t) => t.bookmaker)))];
  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleCourse = (list) => setSel((s) => {
    const n = new Set(s);
    const all = list.every((r) => n.has(r.race_id));
    list.forEach((r) => (all ? n.delete(r.race_id) : n.add(r.race_id)));
    return n;
  });
  const save = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const out = await api.stablesAddOffers({ bookmaker: book.trim(), places, fraction, race_ids: [...sel] });
      setMsg(`Added ${book.trim()} ${places} places ${fraction} to ${out.updated} race${out.updated === 1 ? "" : "s"}.`);
      setSel(new Set());
      onSaved?.();
    } catch (e) {
      setMsg(e.message);
    }
    setBusy(false);
  };
  const label = (t) => <p style={{ color: c.textMuted, letterSpacing: "0.08em" }} className="text-[10px] font-semibold uppercase mb-1.5">{t}</p>;
  if (!open) {
    return (
      <button onClick={() => setOpen(true)} style={{ color: c.green, border: "1px dashed rgba(54,233,143,0.45)" }}
        className="w-full rounded-xl py-3 text-sm font-semibold flex items-center justify-center gap-2 mb-5">
        <Plus size={16} /> Add extra-place offer
      </button>
    );
  }
  const ready = book.trim() && sel.size > 0;
  return (
    <div style={card} className="rounded-xl p-4 flex flex-col gap-4 mb-5">
      <div className="flex items-center justify-between">
        <p style={{ color: c.text }} className="text-sm font-semibold">Add extra-place offer</p>
        <button onClick={() => setOpen(false)} aria-label="Close" style={{ color: c.textMuted }}><X size={18} /></button>
      </div>
      <div>
        {label("Bookmaker")}
        <input value={book} onChange={(e) => setBook(e.target.value)} maxLength={40} placeholder="e.g. Bet365"
          style={{ background: c.cardAlt, border: "1px solid " + c.border, color: c.text }} className="w-full rounded-lg px-3 py-2 text-sm outline-none" />
        {knownBooks.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {knownBooks.map((b) => <button key={b} onClick={() => setBook(b)} style={chip(b === book)} className="text-xs font-semibold px-3 py-1.5 rounded-lg">{b}</button>)}
          </div>
        )}
      </div>
      <div>
        {label(`Races · ${sel.size} selected`)}
        {byCourse.length === 0 && <p style={{ color: c.textMuted }} className="text-xs">No races still to run.</p>}
        <div className="flex flex-col gap-3">
          {byCourse.map(([course, list]) => {
            const all = list.every((r) => sel.has(r.race_id));
            return (
              <div key={course}>
                <div className="flex items-center justify-between mb-1.5">
                  <span style={{ color: c.text }} className="text-sm font-semibold">{course}</span>
                  <button onClick={() => toggleCourse(list)} style={{ color: c.green }} className="text-xs font-semibold">{all ? "None" : "All"}</button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {list.map((r) => {
                    const on = sel.has(r.race_id);
                    const has = book.trim() && realOffers(r).some((t) => t.bookmaker === book.trim());
                    return (
                      <button key={r.race_id} onClick={() => toggle(r.race_id)} style={chip(on)} className="num text-xs font-semibold px-3 py-1.5 rounded-lg flex items-center gap-1">
                        {has && <Check size={12} />}{r.time}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <div>
        {label("Places paid")}
        <div className="flex flex-wrap gap-2">{OFFER_PLACES.map((p) => <button key={p} onClick={() => setPlaces(p)} style={chip(p === places)} className="num text-xs font-semibold px-3.5 py-2 rounded-lg">{p}</button>)}</div>
      </div>
      <div>
        {label("Each-way fraction")}
        <div className="flex gap-2">{OFFER_FRACTIONS.map((f) => <button key={f} onClick={() => setFraction(f)} style={chip(f === fraction)} className="num text-xs font-semibold px-3.5 py-2 rounded-lg">{f}</button>)}</div>
      </div>
      {msg && <p style={{ color: c.textSecondary }} className="text-xs">{msg}</p>}
      <button disabled={!ready || busy} onClick={save} style={{ ...primaryBtn, opacity: !ready || busy ? 0.5 : 1 }} className="rounded-xl py-3 text-sm font-bold">
        {busy ? "Saving…" : `Add to ${sel.size} race${sel.size === 1 ? "" : "s"}`}
      </button>
      <p style={{ color: c.textMuted }} className="text-[11px] -mt-2">Offers are shared with everyone using The Stables. A tick shows races that already have this bookmaker's offer; saving again replaces it.</p>
    </div>
  );
}

function CardsTab({ ui, entitled }) {
  const { c, chip, useApi, Loading, ErrorBox, Empty, SectionLabel } = ui;
  const [date, setDate] = useState(null);
  const [refreshes, setRefreshes] = useState(0);
  const [extra, setExtra] = useState(1);
  const [showStarted, setShowStarted] = useState(false);
  const q = useApi(() => api.stablesRaces(date, refreshes > 0), [entitled, date, refreshes]);
  const data = q.data;
  const refreshing = q.loading && Boolean(data);
  const clock = (iso) => new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  const fed = data?.feed?.last_fetch ? clock(data.feed.last_fetch) : null;
  const updated = data?.priced_at
    ? new Date(data.priced_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
    : null;
  const dates = useMemo(() => {
    const ds = new Set(data?.dates || []);
    if (data?.date) ds.add(data.date);
    return [...ds].sort().reverse().slice(0, 10);
  }, [data]);
  return (
    <>
      <div className="flex items-center justify-between gap-3 mb-4">
        <button onClick={() => setRefreshes((n) => n + 1)} disabled={q.loading}
          style={{ color: c.green, border: "1px solid rgba(54,233,143,0.35)", opacity: q.loading ? 0.6 : 1 }}
          className="flex items-center gap-2 text-xs font-semibold px-3.5 py-2 rounded-lg">
          <RefreshCw size={14} className={q.loading ? "animate-spin" : ""} /> {refreshing ? "Refreshing…" : "Refresh races"}
        </button>
        {updated && <span style={{ color: c.textMuted }} className="text-[11px] text-right">Priced at {updated}{fed ? ` · Betfair ${fed}` : ""}</span>}
      </div>
      {data?.feed?.error && <p style={{ color: c.orange }} className="text-[11px] mb-3">Betfair: {data.feed.error}</p>}
      {dates.length > 1 && (
        <div className="no-scrollbar flex gap-2 overflow-x-auto mb-4 -mx-1 px-1">
          {dates.map((d) => (
            <button key={d} onClick={() => setDate(d)} style={chip(d === data?.date)} className="flex-shrink-0 text-xs font-semibold px-3.5 py-2 rounded-lg whitespace-nowrap num">{d}</button>
          ))}
        </div>
      )}
      {q.loading && !data && <Loading />}
      {q.error && <ErrorBox error={q.error} onRetry={q.reload} />}
      {data && data.races.length === 0 && (
        <Empty>No race cards loaded for {data.date} yet. Use “Price a race” to enter one by hand.</Empty>
      )}
      {data && data.races.length > 0 && (
        <>
          <ModelNote ui={ui} cal={data.calibration} source={data.races[0]?.probability_source} />
          <div className="flex items-center gap-2 mb-4">
            <span style={{ color: c.textMuted, letterSpacing: "0.08em" }} className="text-[10px] font-semibold uppercase mr-1">Extra places</span>
            {[0, 1, 2, 3].map((x) => (
              <button key={x} onClick={() => setExtra(x)} style={chip(x === extra)} className="text-xs font-semibold px-3 py-1.5 rounded-lg num">{x === 0 ? "None" : "+" + x}</button>
            ))}
          </div>
          {data.can_edit_offers && <OffersPanel ui={ui} races={data.races} onSaved={q.reload} />}
          <Shortlist ui={ui} races={data.races.filter((r) => !r.started)} extra={extra} />
          {data.opportunities.length > 0 && <OpportunityList ui={ui} list={data.opportunities} />}
          <SectionLabel>Races · {data.races.filter((r) => !r.started).length} to come</SectionLabel>
          {data.races.every((r) => r.started) && <Empty>All of this day's races have started.</Empty>}
          <div className="flex flex-col gap-3">
            {data.races.filter((r) => showStarted || !r.started).map((r) => (
              <div key={r.race_id} style={{ opacity: r.started ? 0.5 : 1 }}>
                <RaceCard ui={ui} race={r} extra={extra} canEdit={data.can_edit_offers} onChanged={q.reload} />
              </div>
            ))}
          </div>
          {data.started_count > 0 && (
            <button onClick={() => setShowStarted(!showStarted)} style={{ color: c.textSecondary, border: "1px solid " + c.border }} className="w-full rounded-xl py-2.5 text-xs font-medium mt-3">
              {showStarted ? "Hide started races" : `Show ${data.started_count} started race${data.started_count === 1 ? "" : "s"}`}
            </button>
          )}
        </>
      )}
      {data && <p style={{ color: c.textMuted }} className="text-[11px] mt-3">Prices are as loaded; check the live price and terms with the bookmaker.</p>}
    </>
  );
}

const PLACES = [3, 4, 5, 6, 7, 8];
const FRACTIONS = ["1/4", "1/5", "1/6"];

function ManualTab({ ui }) {
  const { c, card, chip, primaryBtn, ErrorBox, SectionLabel } = ui;
  const [text, setText] = useState("");
  const [bookmaker, setBookmaker] = useState("");
  const [places, setPlaces] = useState(5);
  const [fraction, setFraction] = useState("1/5");
  const [handicap, setHandicap] = useState(true);
  const [raceType, setRaceType] = useState("flat");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const parsed = parseRunners(text);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.stablesPrice({
        handicap,
        race_type: raceType,
        runners: parsed.runners,
        terms: [{ bookmaker: bookmaker.trim() || "Bookmaker", places, fraction }],
      }));
    } catch (e) {
      setError(e.message);
      setResult(null);
    }
    setBusy(false);
  };

  const label = (t) => <p style={{ color: c.textMuted, letterSpacing: "0.08em" }} className="text-[10px] font-semibold uppercase mb-1.5">{t}</p>;
  return (
    <>
      <div style={card} className="rounded-xl p-4 flex flex-col gap-4 mb-5">
        <div>
          {label("Runners — one per line, name then odds")}
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={8} placeholder={"Horse One 9/2\nHorse Two 6.0\nHorse Three 12/1"}
            style={{ background: c.cardAlt, border: "1px solid " + c.border, color: c.text }} className="w-full rounded-lg p-3 text-sm num outline-none" />
          <p style={{ color: parsed.bad.length ? c.orange : c.textMuted }} className="text-[11px] mt-1">
            {parsed.runners.length} runners read{parsed.bad.length ? ` · can't read: ${parsed.bad.slice(0, 2).join(", ")}` : ""}. Include every runner so the margin can be taken out.
          </p>
        </div>
        <div>
          {label("Places paid (with extra places)")}
          <div className="flex gap-2 flex-wrap">{PLACES.map((p) => <button key={p} onClick={() => setPlaces(p)} style={chip(p === places)} className="text-xs font-semibold px-3.5 py-2 rounded-lg num">{p}</button>)}</div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            {label("Each-way fraction")}
            <div className="flex gap-2">{FRACTIONS.map((f) => <button key={f} onClick={() => setFraction(f)} style={chip(f === fraction)} className="text-xs font-semibold px-3 py-2 rounded-lg num">{f}</button>)}</div>
          </div>
          <div>
            {label("Handicap?")}
            <div className="flex gap-2">
              <button onClick={() => setHandicap(true)} style={chip(handicap)} className="text-xs font-semibold px-3 py-2 rounded-lg">Yes</button>
              <button onClick={() => setHandicap(false)} style={chip(!handicap)} className="text-xs font-semibold px-3 py-2 rounded-lg">No</button>
            </div>
          </div>
        </div>
        <div>
          {label("Race")}
          <div className="flex gap-2">
            {[["flat", "Flat"], ["hurdle", "Hurdle"], ["chase", "Chase"]].map(([k, l]) => (
              <button key={k} onClick={() => setRaceType(k)} style={chip(raceType === k)} className="text-xs font-semibold px-3 py-2 rounded-lg">{l}</button>
            ))}
          </div>
          <p style={{ color: c.textMuted }} className="text-[11px] mt-1">Jumps races allow for fallers and pulled-up runners, who can't place.</p>
        </div>
        <div>
          {label("Bookmaker (optional)")}
          <input value={bookmaker} onChange={(e) => setBookmaker(e.target.value)} maxLength={40}
            style={{ background: c.cardAlt, border: "1px solid " + c.border, color: c.text }} className="w-full rounded-lg px-3 py-2 text-sm outline-none" />
        </div>
        <button disabled={busy || parsed.runners.length < 2} onClick={run} style={{ ...primaryBtn, opacity: busy || parsed.runners.length < 2 ? 0.5 : 1 }} className="rounded-xl py-3 text-sm font-bold">
          {busy ? "Pricing…" : "Price this race"}
        </button>
      </div>
      {error && <ErrorBox error={error} />}
      {result && (
        <>
          <ModelNote ui={ui} cal={result.calibration} source={result.probability_source} />
          <OpportunityList ui={ui} list={result.opportunities} />
          <SectionLabel>All runners · book margin {result.book_overround ? ((result.book_overround - 1) * 100).toFixed(1) + "%" : "—"}</SectionLabel>
          <div style={card} className="rounded-xl p-4"><RunnerTable ui={ui} race={result} /></div>
        </>
      )}
    </>
  );
}

function StablesDisclaimer({ ui }) {
  return (
    <p style={{ color: ui.c.textSecondary }} className="text-[11px] leading-snug text-center mt-6">
      The Stables is a racing analysis tool. Percentages are model estimates from market prices — not
      predictions, tips or guaranteed profit. Extra-place terms and prices change and bookmakers may limit
      stakes; check them before betting. Betting involves risk; only stake what you can afford to lose.
      18+ · BeGambleAware.org
    </p>
  );
}

export default function StablesPage({ nav, entitled, onPurchased, ui }) {
  const { PageShell, PageTitle, Paywall, chip } = ui;
  const [tab, setTab] = useState("cards");
  return (
    <PageShell activeTab="stables" onNavigate={nav} entitled={entitled}>
      <PageTitle
        title="The Stables"
        subtitle="Extra-place each-way offers, priced runner by runner. We estimate each horse's chance of finishing in every position, then compare its chance of landing in the paid places with what the bookmaker's each-way terms imply."
      />
      {!entitled && <Paywall title="The Stables is a Pro feature" onPurchased={onPurchased} />}
      {entitled && (
        <>
          <div className="flex gap-2 mb-5">
            <button onClick={() => setTab("cards")} style={chip(tab === "cards")} className="text-xs font-semibold px-3.5 py-2 rounded-lg">Race cards</button>
            <button onClick={() => setTab("manual")} style={chip(tab === "manual")} className="text-xs font-semibold px-3.5 py-2 rounded-lg">Price a race</button>
          </div>
          {tab === "cards" ? <CardsTab ui={ui} entitled={entitled} /> : <ManualTab ui={ui} />}
        </>
      )}
      <StablesDisclaimer ui={ui} />
    </PageShell>
  );
}
