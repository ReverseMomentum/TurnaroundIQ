/**
 * The Stables: horse racing extra-place value.
 *
 * Kept out of App.jsx so racing work doesn't collide with football edits.
 * App.jsx passes its design system in as `ui` (colours, card styles,
 * PageShell, Paywall, ...), so this page looks like every other page.
 */
import React, { useMemo, useState } from "react";
import { Check, ChevronDown, Filter, Info, Plus, RefreshCw, X } from "lucide-react";
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
/** Offers grouped by terms: [{ key, places, fraction, books: [names] }], most places first. */
const groupOffers = (offers) => {
  const m = new Map();
  for (const t of offers) {
    const key = `${t.places}|${fractionLabel(t.fraction)}`;
    if (!m.has(key)) m.set(key, { key, places: t.places, fraction: t.fraction, books: [] });
    m.get(key).books.push(t.bookmaker);
  }
  return [...m.values()].sort((a, b) => b.places - a.places || b.fraction - a.fraction);
};
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

function RunnerTable({ ui, race, extra, onOpen }) {
  const { c } = ui;
  const th = { color: c.textMuted, letterSpacing: "0.1em" };
  // one column per set of terms (bookmakers with the same terms share a value line)
  const groups = groupOffers(realOffers(race)).slice(0, 3);
  const valueCols = groups.length
    ? groups.map((g) => ({ key: g.key, label: g.books.length === 1 ? `${shortBook(g.books[0])} ${g.places}pl` : `${g.places}pl ${fractionLabel(g.fraction)}`,
        get: (r) => r.offer_value_from?.[g.books[0]] }))
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
              <tr key={r.name} onClick={onOpen ? () => onOpen(race, r) : undefined} style={{ borderBottom: "1px solid " + c.border, cursor: onOpen ? "pointer" : "default" }}>
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

function RaceCard({ ui, race, extra, canEdit, onChanged, onOpen }) {
  const { c, card } = ui;
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [showBooks, setShowBooks] = useState(false);
  const strong = race.opportunities.filter((o) => o.grade === "A" || o.grade === "B").length;
  const offers = realOffers(race);
  const groups = groupOffers(offers);
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
      {(groups.length > 0 || race.inactive_offers?.length > 0) && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {groups.map((g) => (
            <button key={g.key} onClick={() => setShowBooks(!showBooks)} style={{ color: c.green, border: "1px solid rgba(54,233,143,0.35)", background: "rgba(54,233,143,0.06)" }}
              className="text-[11px] font-semibold px-2 py-1 rounded-md">
              {g.places} places {fractionLabel(g.fraction)} · {g.books.length === 1 ? g.books[0] : `${g.books.length} bookmakers`}
            </button>
          ))}
          {race.inactive_offers?.length > 0 && (
            <button onClick={() => setShowBooks(!showBooks)} style={{ color: c.textMuted, border: "1px solid " + c.border }}
              className="text-[11px] font-medium px-2 py-1 rounded-md">
              +{race.inactive_offers.length} need more runners
            </button>
          )}
        </div>
      )}
      {showBooks && (
        <div style={{ borderTop: "1px solid " + c.border }} className="mt-2 pt-2 flex flex-col gap-1.5">
          {groups.map((g) => (
            <div key={g.key} className="text-[11px] leading-relaxed">
              <span style={{ color: c.green }} className="font-semibold">{g.places} places {fractionLabel(g.fraction)}: </span>
              {g.books.map((b, i) => (
                <span key={b} style={{ color: c.textSecondary }} className="inline-flex items-center gap-0.5">
                  {b}
                  {canEdit && (
                    <button disabled={busy} onClick={() => remove(b)} aria-label={`Remove ${b} offer`} style={{ color: c.textMuted }} className="px-0.5">
                      <X size={11} />
                    </button>
                  )}
                  {i < g.books.length - 1 ? "," : ""}&nbsp;
                </span>
              ))}
            </div>
          ))}
          {race.inactive_offers?.length > 0 && (
            <p style={{ color: c.textMuted }} className="text-[11px]">
              Not standing with {race.field_size} runners: {race.inactive_offers.map((t) => `${t.bookmaker} (${t.min_runners}+)`).join(", ")}
            </p>
          )}
        </div>
      )}
      {open && (
        <div className="mt-3">
          <RunnerTable ui={ui} race={race} extra={extra} onOpen={onOpen} />
          {race.standard_terms?.fraction > 0 && (
            <p style={{ color: c.textMuted }} className="text-[11px] mt-2">
              {offers.length
                ? "Value from: the smallest price worth taking each-way with each bookmaker's offer above."
                : `Value from: the smallest bookmaker price worth taking each-way at ${race.standard_terms.places + extra} places, ${fractionLabel(race.standard_terms.fraction)} odds.`}{" "}
              Green where the exchange price is already that big. No value calls on runners at 33/1 or bigger: in past races the model overrated them.
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
        {cal?.learned?.length ? ` A learned model adjusts each runner using ${cal.learned.length} form, connections and rating inputs.` : ""}
        {cal?.segments?.length ? ` Position chances use separate curves for ${cal.segments.length} race-type and field-size groups.` : ""}
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
// Odds filter for the shortlist and value list (decimal prices, lower bound inclusive).
const ODDS_FILTERS = [
  { key: "all", label: "All", lo: 0, hi: Infinity },
  { key: "short", label: "Up to 4/1", lo: 0, hi: 5.0 },
  { key: "mid", label: "4/1–8/1", lo: 5.0, hi: 9.0 },
  { key: "long", label: "8/1–16/1", lo: 9.0, hi: 17.0 },
  { key: "big", label: "16/1–33/1", lo: 17.0, hi: 34.0 },
];
const inOdds = (filter, price) => !filter || filter.key === "all" || (price >= filter.lo && price < filter.hi);

// What it takes to make "Worth checking" (the rest sit behind "show all"):
const SHORTLIST_MARGIN = 0.05;    // exchange price at least 5% over the value line (about the model's own error)
const SHORTLIST_SPREAD = 0.15;    // back/lay gap no wider than 15%: wider means a thin market and a shaky price
const SHORTLIST_VOLUME = 250;     // £ matched on the horse, when Betfair reports it

function shortlistCheck(r, price, vf) {
  const ex = r.exchange || {};
  if (price < vf * (1 + SHORTLIST_MARGIN)) return "thin margin";
  if (ex.back && ex.lay && ex.lay / ex.back - 1 > SHORTLIST_SPREAD) return "wide spread";
  if (ex.volume > 0 && ex.volume < SHORTLIST_VOLUME) return "little traded";   // 0 / missing = not reported
  return null;
}

function Shortlist({ ui, races, extra, onOpen, oddsFilter }) {
  const { c, card, SectionLabel, Empty } = ui;
  const [showAll, setShowAll] = useState(false);
  const rows = [];
  for (const race of races) {
    if (!(race.standard_terms?.fraction > 0)) continue;
    const offers = realOffers(race);
    const terms = offers.length
      ? groupOffers(offers).map((g) => ({ book: g.books[0],
          label: `${g.places} places ${fractionLabel(g.fraction)} · ${g.books.length === 1 ? g.books[0] : g.books.length + " bookmakers"}`,
          get: (r) => r.offer_value_from?.[g.books[0]] }))
      : [{ book: null, label: `${race.standard_terms.places + extra} places ${fractionLabel(race.standard_terms.fraction)}`, get: (r) => r.value_from?.[String(extra)] }];
    for (const r of race.runners) {
      const price = r.best_win_odds || r.exchange_back;
      // One row per horse: the offer with the lowest value line (the best terms).
      const ok = terms.map((t) => ({ t, vf: t.get(r) })).filter(({ vf }) => vf && price && price >= vf)
        .sort((a, b) => a.vf - b.vf);
      if (ok.length && inOdds(oddsFilter, price)) {
        rows.push({ race, r, vf: ok[0].vf, price, t: ok[0].t, more: ok.length - 1, ratio: price / ok[0].vf,
          why: shortlistCheck(r, price, ok[0].vf) });
      }
    }
  }
  rows.sort((a, b) => (b.t.book ? 1 : 0) - (a.t.book ? 1 : 0) || b.ratio - a.ratio);
  const strong = rows.filter((x) => !x.why);
  const top = (showAll ? rows : strong).slice(0, showAll ? 40 : 15);
  return (
    <>
      <SectionLabel>Worth checking · {strong.length}</SectionLabel>
      <p style={{ color: c.textMuted }} className="text-[11px] -mt-2 mb-3 leading-snug">
        The exchange price is at least {Math.round(SHORTLIST_MARGIN * 100)}% over the value line, in a market that is
        trading properly (back/lay gap under {Math.round(SHORTLIST_SPREAD * 100)}%, £{SHORTLIST_VOLUME}+ matched). If the
        bookmaker's price is at or above "value from" on those terms, the model rates it value. Races with entered
        offers come first, on each bookmaker's terms; the rest use {extra ? `${extra} extra place${extra > 1 ? "s" : ""}` : "standard terms"}.
      </p>
      {top.length === 0 && <Empty>No runner clears the value line with room to spare{oddsFilter && oddsFilter.key !== "all" ? ` in the ${oddsFilter.label} range` : ""}.</Empty>}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2 mb-6">
        {top.map(({ race, r, vf, price, t, more, ratio, why }) => (
          <button key={race.race_id + r.name + (t.book || "")} onClick={() => onOpen?.(race, r)} style={{ ...card, textAlign: "left" }} className="rounded-xl px-4 py-3 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p style={{ color: c.text }} className="text-sm font-semibold truncate">{r.name}</p>
              <p style={{ color: c.textMuted }} className="text-xs truncate">
                <span className="num">{race.time}</span> {race.course} · <span style={{ color: t.book ? c.green : c.textMuted }}>{t.label}</span>{more > 0 ? ` +${more} more` : ""}
              </p>
            </div>
            <div className="text-right flex-shrink-0">
              <p style={{ color: c.green }} className="num text-sm font-bold">{ukPriceAtLeast(vf)}+</p>
              <p style={{ color: c.textMuted }} className="text-[10px]">exchange <span className="num">{Number(price).toFixed(2)}</span>
                {" · "}<span style={{ color: why ? c.orange : c.green }} className="num">+{Math.round((ratio - 1) * 100)}%</span></p>
              {why && <p style={{ color: c.orange }} className="text-[10px]">{why}</p>}
            </div>
          </button>
        ))}
      </div>
      {rows.length > strong.length && (
        <button onClick={() => setShowAll(!showAll)} style={{ color: c.textSecondary, border: "1px solid " + c.border }}
          className="w-full rounded-xl py-2.5 text-xs font-medium -mt-4 mb-6">
          {showAll ? "Show only the strongest" : `Show ${rows.length - strong.length} more that only just clear the line`}
        </button>
      )}
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
  const [mode, setMode] = useState("pick");
  const [pasted, setPasted] = useState("");
  const upcoming = races.filter((r) => !r.started && r.race_id);
  const day = races.find((r) => r.date)?.date;
  const savePasted = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const out = await api.stablesPasteOffers(day, pasted);
      const parts = [`Saved ${out.offers} offer${out.offers === 1 ? "" : "s"} on ${out.races} race${out.races === 1 ? "" : "s"}.`];
      if (out.not_found?.length) parts.push(`Not on the cards yet: ${out.not_found.join(", ")}.`);
      if (out.not_understood?.length) parts.push(`Lines not understood: ${out.not_understood.slice(0, 5).join(" · ")}`);
      setMsg(parts.join(" "));
      if (out.offers) setPasted("");
      onSaved?.();
    } catch (e) {
      setMsg(e.message);
    }
    setBusy(false);
  };
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
  const books = [...new Map(book.split(",").map((b) => b.trim()).filter(Boolean).map((b) => [b.toLowerCase(), b])).values()];
  const toggleBook = (b) => {
    const has = books.some((x) => x.toLowerCase() === b.toLowerCase());
    setBook((has ? books.filter((x) => x.toLowerCase() !== b.toLowerCase()) : [...books, b]).join(", "));
  };
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
      setMsg(`Added ${out.bookmakers.join(", ")} · ${places} places ${fraction} to ${out.races} race${out.races === 1 ? "" : "s"}.`);
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
  const ready = books.length > 0 && sel.size > 0;
  return (
    <div style={card} className="rounded-xl p-4 flex flex-col gap-4 mb-5">
      <div className="flex items-center justify-between">
        <p style={{ color: c.text }} className="text-sm font-semibold">Add extra-place offer</p>
        <button onClick={() => setOpen(false)} aria-label="Close" style={{ color: c.textMuted }}><X size={18} /></button>
      </div>
      <div className="flex gap-2">
        {[["pick", "Pick races"], ["paste", "Paste a list"]].map(([k, t]) => (
          <button key={k} onClick={() => { setMode(k); setMsg(null); }} style={chip(mode === k)} className="text-xs font-semibold px-3 py-1.5 rounded-lg">{t}</button>
        ))}
      </div>
      {mode === "paste" ? (
        <>
          <div>
            {label(`Offers for ${day || "today"}`)}
            <textarea value={pasted} onChange={(e) => setPasted(e.target.value)} rows={10} maxLength={20000}
              placeholder={"14:10 Killarney\n(4 places, 1/5 odds)\nbet365\nBetway (12+)\n(5 places, 1/5 odds)\nSky Bet (12+)"}
              style={{ background: c.cardAlt, border: "1px solid " + c.border, color: c.text }} className="w-full rounded-lg px-3 py-2 text-sm outline-none num" />
          </div>
          {msg && <p style={{ color: c.textSecondary }} className="text-xs">{msg}</p>}
          <button disabled={!pasted.trim() || !day || busy} onClick={savePasted} style={{ ...primaryBtn, opacity: !pasted.trim() || !day || busy ? 0.5 : 1 }} className="rounded-xl py-3 text-sm font-bold">
            {busy ? "Saving…" : "Save offers"}
          </button>
          <p style={{ color: c.textMuted }} className="text-[11px] -mt-2">One race per line ("14:10 Killarney"), then the terms ("(4 places, 1/5 odds)"), then one bookmaker per line. "(12+)" means the offer only stands with 12 or more runners. Saving again replaces a bookmaker's terms on that race.</p>
        </>
      ) : (<>
      <div>
        {label("Bookmakers · separate with commas")}
        <input value={book} onChange={(e) => setBook(e.target.value)} maxLength={400} placeholder="e.g. Bet365, Paddy Power"
          style={{ background: c.cardAlt, border: "1px solid " + c.border, color: c.text }} className="w-full rounded-lg px-3 py-2 text-sm outline-none" />
        {knownBooks.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {knownBooks.map((b) => <button key={b} onClick={() => toggleBook(b)} style={chip(books.some((x) => x.toLowerCase() === b.toLowerCase()))} className="text-xs font-semibold px-3 py-1.5 rounded-lg">{b}</button>)}
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
                    const has = books.length > 0 && books.every((b) => realOffers(r).some((t) => t.bookmaker.toLowerCase() === b.toLowerCase()));
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
        {busy ? "Saving…" : `Add${books.length > 1 ? ` ${books.length} bookmakers` : ""} to ${sel.size} race${sel.size === 1 ? "" : "s"}`}
      </button>
      <p style={{ color: c.textMuted }} className="text-[11px] -mt-2">Offers are shared with everyone using The Stables. Several bookmakers with the same terms: separate them with commas. A tick shows races that already have these offers; saving again replaces them.</p>
      </>)}
    </div>
  );
}

const BET_PLACES = [2, 3, 4, 5, 6, 7, 8];

// The model's chance of finishing in the first k (recalibrated top 3-6, else summed positions).
function placeChance(runner, k) {
  const top = runner[`top${k}_probability`];
  if (top != null) return top;
  return (runner.positions || []).slice(0, k).reduce((a, b) => a + b, 0);
}

/**
 * Each-way bet (stake = total, half win / half place) with an optional exchange lay.
 *   none: no lay
 *   part: lay the win only (covers the win half; mainly the place half rides)
 *   full: lay the win and the place, the place on Betfair's place market at the
 *         standard places: roughly level if it wins or places inside the
 *         standard places, and both place bets pay if it lands an extra place.
 * pWin / pStd / pPlace: model chances of winning, the standard places, the paid places.
 */
export function ewLayOutcomes({ stake, odds, fraction, layOdds, placeLayOdds, mode, commission, pWin, pStd, pPlace, winPct = 100 }) {
  const half = stake / 2;
  const placeOdds = 1 + (odds - 1) * fraction;
  const cm = (commission || 0) / 100;
  // 100% = the win half covered; part lay can go lower, or higher ("min loss", below)
  const pctUsed = mode === "part" ? Math.min(Math.max(winPct, 0), 200) : 100;
  // Stakes rounded to the penny first, as Betfair takes them; liability and outcomes follow from those.
  const pence = (v) => Math.round(v * 100) / 100;
  const winLay = mode !== "none" && layOdds > 1 && layOdds - cm > 0 ? pence((pctUsed / 100) * (half * odds) / (layOdds - cm)) : 0;
  if (mode === "full" && !(placeLayOdds > 1)) return null;       // needs the place lay price
  const placeLay = mode === "full" && placeLayOdds - cm > 0 ? pence((half * placeOdds) / (placeLayOdds - cm)) : 0;
  const winLiab = winLay * ((layOdds || 1) - 1);
  const placeLiab = placeLay * ((placeLayOdds || 1) - 1);
  const win = half * (odds - 1) + half * (placeOdds - 1) - winLiab - placeLiab;
  const placed = -half + half * (placeOdds - 1) + winLay * (1 - cm) - placeLiab;
  const extra = -half + half * (placeOdds - 1) + winLay * (1 - cm) + placeLay * (1 - cm);
  const lost = -stake + winLay * (1 - cm) + placeLay * (1 - cm);
  const pS = Math.max(pStd ?? pPlace, pWin), pP = Math.max(pPlace, pS);
  const ev = pWin * win + (pS - pWin) * placed + (pP - pS) * extra + (1 - pP) * lost;
  return { winLay, placeLay, liability: winLiab + placeLiab, win, placed, extra, lost, ev,
    worst: Math.min(win, placed, extra, lost) };
}

// Betfair place markets for one runner: prices, the chance they imply, and the model's chance.
function PlaceMarkets({ ui, runner, stdPlaces }) {
  const { c, SectionLabel } = ui;
  const pm = runner.place_exchange || {};
  const ks = Object.keys(pm).map(Number).filter((k) => pm[k] && (pm[k].back || pm[k].lay)).sort((a, b) => a - b);
  if (!ks.length) return null;
  return (
    <>
      <SectionLabel>Betfair place markets</SectionLabel>
      <div style={{ border: "1px solid " + c.border }} className="rounded-xl overflow-hidden mb-4">
        <table className="w-full text-xs">
          <thead>
            <tr style={{ color: c.textMuted }}>
              {["Places", "Back", "Lay", "Market", "Model"].map((h, i) => <th key={h} className={"py-1.5 px-2 font-semibold " + (i ? "text-right" : "text-left")}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {ks.map((k) => {
              const { back, lay } = pm[k];
              const mid = back && lay ? (back + lay) / 2 : back || lay;
              const implied = mid > 1 ? 1 / mid : null;
              const model = placeChance(runner, k);
              return (
                <tr key={k} style={{ borderTop: "1px solid " + c.border }}>
                  <td style={{ color: c.text }} className="py-1.5 px-2">{k}{k === stdPlaces ? " (standard)" : ""}</td>
                  <td style={{ color: c.green }} className="num py-1.5 px-2 text-right">{back ? Number(back).toFixed(2) : "—"}</td>
                  <td style={{ color: c.cyan }} className="num py-1.5 px-2 text-right">{lay ? Number(lay).toFixed(2) : "—"}</td>
                  <td style={{ color: c.textSecondary }} className="num py-1.5 px-2 text-right">{implied ? pct(implied) : "—"}</td>
                  <td style={{ color: implied && model > implied ? c.green : c.text }} className="num py-1.5 px-2 text-right">{pct(model)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

/**
 * Win lay % (of the 100% lay) that loses least in the worst case when only the win
 * is laid: it makes "wins" and "unplaced" cost the same, and a placed horse then
 * collects the win lay and the place part. = (win odds + place odds) / win odds.
 * With a full lay (win + place) the standard 100% / 100% stakes already do this.
 */
export function minLossWinPct(odds, fraction) {
  if (!(odds > 1)) return 100;
  const placeOdds = 1 + (odds - 1) * fraction;
  return (100 * (odds + placeOdds)) / odds;
}

// The learned model's inputs for one runner (place rates are shrunk towards ~30%).
function RunnerFacts({ ui, runner }) {
  const { c, SectionLabel } = ui;
  const f = runner.features || {};
  if (!Object.keys(f).length) return null;
  const num = (v, dp = 1) => (v == null ? "—" : Number(v).toFixed(dp));
  // average points a run above (+) or below (-) what its starting prices implied, shrunk towards 0
  const pts = (v) => (v == null ? "—" : `${v >= 0 ? "+" : "−"}${Math.abs(100 * v).toFixed(0)} pts`);
  const days = runner.days_since_run ?? (f.log_days != null && f.log_days > 0 ? Math.round(Math.exp(f.log_days) - 1) : null);
  // [label, value, runs it is based on]: no runs on file -> "—" rather than the 30% starting point
  const rate = (v, runs) => (runs === 0 ? "—" : pct(v, 0));
  const runsSub = (runs) => (runs == null ? null : runs === 0 ? "no runs on file" : `${runs} run${runs === 1 ? "" : "s"}`);
  const items = [
    ["Last run", f.last_pos == null ? "—" : f.last_pos >= 12 ? "DNF" : ordinal(f.last_pos)],
    ["Avg of last 3", num(f.avg3_pos)],
    ["Avg of last 5", num(f.avg5_pos)],
    ["Days since run", days == null ? "—" : String(days)],
    ["Course place", rate(f.course_rate, f.course_runs), f.course_runs],
    ["Distance place", rate(f.distance_rate, f.distance_runs), f.distance_runs],
    ["Jockey place", rate(f.jockey_rate, f.jockey_runs), f.jockey_runs],
    ["Jockey 30 days", rate(f.jockey_30d, f.jockey_30d_runs), f.jockey_30d_runs],
    ["Trainer place", rate(f.trainer_rate, f.trainer_runs), f.trainer_runs],
    ["Trainer 30 days", rate(f.trainer_30d, f.trainer_30d_runs), f.trainer_30d_runs],
    ["Horse + jockey", rate(f.horse_jockey_rate, f.horse_jockey_runs), f.horse_jockey_runs],
    ["OR vs field", f.or_missing === 1 || f.or_rel == null ? "—" : (f.or_rel >= 0 ? "+" : "") + num(f.or_rel, 0),
      null, f.or_missing === 1 ? "no rating" : null],
    ["Placed vs prices", f.priced_runs === 0 ? "—" : pts(f.place_excess), f.priced_runs],
    ["Won vs prices", f.priced_runs === 0 ? "—" : pts(f.win_excess), f.priced_runs],
  ];
  return (
    <>
      <SectionLabel>Form & connections</SectionLabel>
      <div className="grid grid-cols-3 gap-x-3 gap-y-2 mb-1">
        {items.map(([k, v, runs, note]) => <Metric key={k} ui={ui} label={k} value={v} sub={note || runsSub(runs)} />)}
      </div>
      <p style={{ color: c.textMuted }} className="text-[11px] mb-4">
        Place = finished in the first three. Rates lean towards the 30% average until there are enough runs
        {f.history_runs != null ? ` (${f.history_runs} past runs on file for this horse)` : ""}. "vs prices" compares its
        record with the chances its prices gave it; a horse that places more often than it wins can be under-rated
        by place terms based on its win price.
      </p>
    </>
  );
}

// Betfair gives weight in lbs ("148.0") -> "10-8"; anything else is shown as given.
const stoneLbs = (w) => {
  const n = Number(w);
  return Number.isFinite(n) && n > 60 ? `${Math.floor(n / 14)}-${Math.round(n % 14)}` : String(w);
};

const ordinal = (n) => {
  const v = Math.round(n);
  const s = v % 100 >= 11 && v % 100 <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[v % 10] || "th";
  return v + s;
};

// Tap a runner: what the model sees, and a form to track the bet in My bets.
function RunnerSheet({ ui, race, runner, extra, onClose }) {
  const { c, card, chip, primaryBtn, Sheet, Bar, SectionLabel } = ui;
  const offers = realOffers(race);
  const std = race.standard_terms || {};
  const first = offers[0];
  const [book, setBook] = useState(first?.bookmaker || "");
  const [places, setPlaces] = useState(first?.places || (std.places || 3) + (extra || 0));
  const [fraction, setFraction] = useState(first ? fractionLabel(first.fraction) : fractionLabel(std.fraction || 0.2));
  const [oddsText, setOddsText] = useState("");
  // Stake each way, as bookmakers quote it: "£5 each-way" = £5 win + £5 place = £10 in total.
  const [stakeEach, setStakeEach] = useState("5");
  const stake = String(2 * (parseFloat(stakeEach) || 0));
  const [paper, setPaper] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [layMode, setLayMode] = useState("none");
  // Betfair's place market at the standard places (the one a full lay uses), filled in when collected
  const stdLay = runner.place_exchange?.[String(std.fraction > 0 ? std.places : 0)]?.lay;
  const [placeLayText, setPlaceLayText] = useState(stdLay ? String(stdLay) : "");
  const [layText, setLayText] = useState(runner.exchange?.lay ? String(runner.exchange.lay) : "");
  const [commission, setCommission] = useState(String(ui.defaultCommission ?? 2));
  const odds = parseOdds(oddsText);
  const layOdds = parseFloat(layText) || null;
  const placeLayOdds = parseFloat(placeLayText) || null;
  const stdPlaces = std.fraction > 0 ? std.places : 0;
  const frac = 1 / (Number(String(fraction).split("/")[1]) || 5);
  // Part lay is sized for the smallest possible loss (see minLossWinPct), not picked by hand.
  const minLossPct = minLossWinPct(odds || 0, frac);
  const winPct = minLossPct;
  const outcomes = (m) => ewLayOutcomes({ stake: Number(stake) || 0, odds: odds || 0, fraction: frac, layOdds, winPct,
    placeLayOdds, mode: m, commission: parseFloat(commission) || 0, pWin: runner.win_probability || 0,
    pStd: stdPlaces ? placeChance(runner, stdPlaces) : null, pPlace: placeChance(runner, places) });
  const offer = offers.find((t) => t.bookmaker === book.trim() && t.places === places && fractionLabel(t.fraction) === fraction);
  const generic = fraction === fractionLabel(std.fraction) ? runner.value_from?.[String(places - (std.places || 0))] : null;
  const valueLine = offer ? runner.offer_value_from?.[offer.bookmaker] : generic;
  const pickOffer = (t) => { setBook(t.bookmaker); setPlaces(t.places); setFraction(fractionLabel(t.fraction)); };
  const submit = async () => {
    setBusy(true);
    setMsg(null);
    try {
      await api.stablesTrack({ race_id: race.race_id, horse: runner.name, bookmaker: book.trim(), odds,
        stake: Number(stake), places, fraction, paper,
        lay_mode: { none: "none", part: "win", full: "full" }[layMode],
        lay_pct: layMode === "part" ? winPct : layMode === "full" ? 100 : 0,
        lay_odds: layMode !== "none" ? layOdds : null, place_lay_odds: layMode === "full" ? placeLayOdds : null,
        commission: parseFloat(commission) || 0 });
      setMsg({ ok: true, text: `Added to My bets (${paper ? "paper" : "real"}). It settles itself from Betfair results where it can.` });
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    }
    setBusy(false);
  };
  const label = (t) => <p style={{ color: c.textMuted, letterSpacing: "0.08em" }} className="text-[10px] font-semibold uppercase mb-1.5">{t}</p>;
  const facts = [
    runner.jockey && `J: ${runner.jockey}`, runner.trainer && `T: ${runner.trainer}`,
    runner.age && `${runner.age}yo`, runner.weight && stoneLbs(runner.weight),
    runner.official_rating && `OR ${runner.official_rating}`, runner.draw && `draw ${runner.draw}`,
    runner.form && `form ${runner.form}`,
  ].filter(Boolean);
  const ex = runner.exchange || {};
  const layOk = layMode === "none" || (layOdds > 1 && (layMode === "part" ? winPct > 0 : placeLayOdds > 1 && stdPlaces > 0));
  const ready = book.trim() && odds && Number(stake) > 0 && !race.started && layOk;
  return (
    <Sheet open onClose={onClose}>
      <p style={{ color: c.textMuted, letterSpacing: "0.12em" }} className="text-[10px] font-semibold uppercase mb-1">{race.time} {race.course}</p>
      <p style={{ color: c.text }} className="text-xl font-bold tracking-tight">{runner.number ? <span style={{ color: c.textMuted }} className="num mr-2">{runner.number}</span> : null}{runner.name}</p>
      {facts.length > 0 && <p style={{ color: c.textSecondary }} className="text-xs mt-1">{facts.join(" · ")}</p>}
      <div className="grid grid-cols-3 gap-3 my-4">
        <Metric ui={ui} label="Exchange" value={ex.back ? Number(ex.back).toFixed(2) : "—"} sub={ex.lay ? `lay ${Number(ex.lay).toFixed(2)}` : "back"} />
        <Metric ui={ui} label="Win" value={pct(runner.win_probability)} tone={c.green} sub="model" />
        <Metric ui={ui} label={`Top ${std.places || 3}`} value={pct(runner[`top${std.places || 3}_probability`])} sub="standard places" />
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 mb-4">
        <Bar label="Top 4" value={100 * (runner.top4_probability || 0)} tone={c.cyan} right={pct(runner.top4_probability)} />
        <Bar label="Top 5" value={100 * (runner.top5_probability || 0)} tone={c.cyan} right={pct(runner.top5_probability)} />
        <Bar label="Exactly 4th" value={100 * (runner.positions?.[3] || 0)} max={30} tone={c.orange} right={pct(runner.positions?.[3])} />
        <Bar label="Exactly 5th" value={100 * (runner.positions?.[4] || 0)} max={30} tone={c.orange} right={pct(runner.positions?.[4])} />
      </div>
      <PlaceMarkets ui={ui} runner={runner} stdPlaces={std.fraction > 0 ? std.places : 0} />
      <RunnerFacts ui={ui} runner={runner} />
      <SectionLabel>Value from</SectionLabel>
      <div className="flex flex-wrap gap-2 mb-4">
        {groupOffers(offers).map((g) => {
          const vf = runner.offer_value_from?.[g.books[0]];
          const on = g.books.includes(book.trim()) && places === g.places && fraction === fractionLabel(g.fraction);
          // same terms = same value line; picking keeps your bookmaker if it is one of them
          const pick = () => pickOffer({ bookmaker: g.books.includes(book.trim()) ? book.trim() : g.books[0], places: g.places, fraction: g.fraction });
          return (
            <button key={g.key} onClick={pick} style={chip(on)} className="text-xs font-semibold px-3 py-1.5 rounded-lg">
              {g.books.length === 1 ? g.books[0] : `${g.books.length} bookmakers`} {g.places}pl {fractionLabel(g.fraction)}: <span className="num">{vf ? ukPriceAtLeast(vf) + "+" : "—"}</span>
            </button>
          );
        })}
        {[0, 1, 2, 3].filter((x) => runner.value_from?.[String(x)] !== undefined).map((x) => (
          <span key={x} style={{ border: "1px solid " + c.border, color: c.textSecondary }} className="text-xs px-3 py-1.5 rounded-lg">
            {(std.places || 0) + x}pl {fractionLabel(std.fraction)}: <span className="num">{runner.value_from[String(x)] ? ukPriceAtLeast(runner.value_from[String(x)]) + "+" : "—"}</span>
          </span>
        ))}
        {runner.beyond_value_range && <span style={{ color: c.textMuted }} className="text-xs">No value call at 33/1 or bigger.</span>}
      </div>

      <SectionLabel>Track this bet</SectionLabel>
      <div style={card} className="rounded-xl p-3 flex flex-col gap-3 mb-3">
        <div className="-mb-4">
          <ui.SlideSwitch options={LAY_MODES} value={layMode} onChange={setLayMode} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            {label("Bookmaker")}
            <input value={book} onChange={(e) => setBook(e.target.value)} maxLength={40} placeholder="e.g. Bet365"
              style={{ background: c.cardAlt, border: "1px solid " + c.border, color: c.text }} className="w-full rounded-lg px-3 py-2 text-sm outline-none" />
          </div>
          <div>
            {label("Your odds")}
            <input value={oddsText} onChange={(e) => setOddsText(e.target.value)} inputMode="decimal" placeholder="9/1 or 10.0"
              style={{ background: c.cardAlt, border: "1px solid " + (oddsText && !odds ? c.red : c.border), color: c.text }} className="w-full rounded-lg px-3 py-2 text-sm num outline-none" />
          </div>
        </div>
        <div>
          {label("Places paid")}
          <div className="flex flex-wrap gap-2">{BET_PLACES.map((p) => <button key={p} onClick={() => setPlaces(p)} style={chip(p === places)} className="num text-xs font-semibold px-3 py-1.5 rounded-lg">{p}</button>)}</div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            {label("Fraction")}
            <div className="flex gap-2">{["1/4", "1/5", "1/6"].map((f) => <button key={f} onClick={() => setFraction(f)} style={chip(f === fraction)} className="num text-xs font-semibold px-2.5 py-1.5 rounded-lg">{f}</button>)}</div>
          </div>
          <div>
            {label("Stake each way")}
            <input value={stakeEach} onChange={(e) => setStakeEach(e.target.value)} inputMode="decimal"
              style={{ background: c.cardAlt, border: "1px solid " + c.border, color: c.text }} className="w-full rounded-lg px-3 py-2 text-sm num outline-none" />
            <p style={{ color: c.textMuted }} className="text-[10px] mt-1 num">£{(parseFloat(stakeEach) || 0).toFixed(2)} win + £{(parseFloat(stakeEach) || 0).toFixed(2)} place = £{(2 * (parseFloat(stakeEach) || 0)).toFixed(2)} total</p>
          </div>
        </div>
        <LayChooser ui={ui} mode={layMode} setMode={setLayMode} placeLayText={placeLayText} setPlaceLayText={setPlaceLayText}
          stdPlaces={stdPlaces} places={places}
          layText={layText} setLayText={setLayText} commission={commission} setCommission={setCommission}
          outcomes={odds && Number(stake) > 0 ? outcomes : null} label={label} />
        <div className="flex gap-2">
          <button onClick={() => setPaper(true)} style={chip(paper)} className="text-xs font-semibold px-3 py-1.5 rounded-lg">Paper</button>
          <button onClick={() => setPaper(false)} style={chip(!paper)} className="text-xs font-semibold px-3 py-1.5 rounded-lg">Real bet</button>
        </div>
        {valueLine && odds && (
          <p style={{ color: odds >= valueLine ? c.green : c.orange }} className="text-xs font-semibold">
            {odds >= valueLine ? "At or above" : "Below"} the value line ({ukPriceAtLeast(valueLine)}) for these terms.
          </p>
        )}
        <button disabled={!ready || busy} onClick={submit} style={{ ...primaryBtn, opacity: !ready || busy ? 0.5 : 1 }} className="rounded-xl py-3 text-sm font-bold">
          {race.started ? "Race has started" : busy ? "Adding…" : "Add to My bets"}
        </button>
        {msg && <p style={{ color: msg.ok ? c.green : c.red }} className="text-xs">{msg.text}</p>}
      </div>
      <p style={{ color: c.textMuted }} className="text-[11px] leading-snug">
        Each tracked bet keeps a snapshot of the model at this moment, so results can show where it is right and wrong.
        Estimates only, not tips. 18+ · BeGambleAware.org
      </p>
    </Sheet>
  );
}

const LAY_MODES = [
  { key: "none", label: "No lay" },
  { key: "part", label: "Part lay" },
  { key: "full", label: "Full lay" },
];

// Lay on the exchange (picked with the switch at the top of the bet form): what each option returns.
function LayChooser({ ui, mode, setMode, placeLayText, setPlaceLayText, stdPlaces, places, layText, setLayText,
  commission, setCommission, outcomes, label }) {
  const { c } = ui;
  const modes = [["none", "No lay"], ["part", "Part lay"], ["full", "Full lay"]];
  const gbp = (v) => (v < 0 ? "−£" : "£") + Math.abs(v).toFixed(2);
  const tone = (v) => (v > 0.005 ? c.green : v < -0.005 ? c.red : c.textSecondary);
  const rows = outcomes ? modes.map(([k]) => [k, outcomes(k)]) : [];
  const hasExtra = stdPlaces > 0 && places > stdPlaces;
  const input = (lbl, value, set, placeholder) => (
    <div>
      <p style={{ color: c.textMuted }} className="text-[10px] mb-1">{lbl}</p>
      <input value={value} onChange={(e) => set(e.target.value)} inputMode="decimal" placeholder={placeholder}
        style={{ background: c.cardAlt, border: "1px solid " + (value && !(parseFloat(value) > 1) && placeholder ? c.red : c.border), color: c.text }}
        className="w-full rounded-lg px-2 py-1.5 text-sm num outline-none" />
    </div>
  );
  const line = (title, key, money = true) => (
    <tr>
      <td style={{ color: c.textMuted }} className="py-1 pr-1">{title}</td>
      {rows.map(([k, o]) => (
        <td key={k} style={{ color: !o ? c.textMuted : money ? tone(o[key]) : c.textSecondary, fontWeight: k === mode ? 700 : 500 }} className="num py-1 px-1 text-right">
          {!o || (!money && !o[key]) ? "—" : gbp(o[key])}
        </td>
      ))}
    </tr>
  );
  const title = {
    none: "No lay: a straight each-way bet",
    part: "Part lay: lay the win on Betfair, sized for the smallest possible loss",
    full: `Full lay: lay the win and the place (${stdPlaces || "standard"} places) on Betfair`,
  }[mode];
  return (
    <div>
      {label(title)}
      {mode !== "none" && (
        <div className={`grid ${mode === "full" ? "grid-cols-3" : "grid-cols-2"} gap-3 mb-2`}>
          {input("Win lay odds", layText, setLayText, "e.g. 11.5")}
          {mode === "full" && input(`Place lay odds (${stdPlaces} pl)`, placeLayText, setPlaceLayText, "e.g. 3.2")}
          {input("Commission %", commission, setCommission)}
        </div>
      )}
      {rows.some(([k, o]) => k === "full" && !o) && stdPlaces > 0 && (
        <p style={{ color: c.textMuted }} className="text-[11px] mb-2">Full lay figures need the place lay price ({stdPlaces} places on Betfair).</p>
      )}
      {mode === "full" && !stdPlaces && (
        <p style={{ color: c.orange }} className="text-[11px] mb-2">This race has no standard place market (win only), so a full lay isn't possible.</p>
      )}
      {rows.length > 0 && (
        <table className="w-full text-xs">
          <thead>
            <tr style={{ color: c.textMuted }}>
              <th className="py-1 text-left font-semibold"></th>
              {modes.map(([k, t]) => (
                <th key={k} className="py-1 px-1 text-right font-semibold">
                  <button onClick={() => setMode(k)} style={{ color: k === mode ? c.green : c.textMuted }}>{t}</button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {line("Win lay stake", "winLay", false)}
            {line("Place lay stake", "placeLay", false)}
            {line("Liability", "liability", false)}
            {line("If it wins", "win")}
            {line(stdPlaces >= 2 ? `If ${stdPlaces === 2 ? "2nd" : "2nd–" + ordinal(stdPlaces)}` : "If it places", "placed")}
            {hasExtra && line(`If ${ordinal(stdPlaces + 1)}${places > stdPlaces + 1 ? "–" + ordinal(places) : ""} (extra)`, "extra")}
            {line("If unplaced", "lost")}
            {line("Model estimate", "ev")}
          </tbody>
        </table>
      )}
      <p style={{ color: c.textMuted }} className="text-[11px] mt-1.5 leading-snug">
        Both lays are sized for the smallest possible loss. Part lay lays the win only, so a winner and an
        unplaced horse cost the same small amount, and a placed horse collects the win lay and the place part.
        Full lay also lays the place half at the standard places: winning, placing normally and finishing
        unplaced come out about level, and an extra place pays both place bets. Neither removes the risk, and
        exchange prices move: enter the lay prices you can actually get.
      </p>
    </div>
  );
}

const pctOrDash = (v) => (v == null ? "—" : signedPct(v));

function TrackerTab({ ui, entitled }) {
  const { c, card, chip, useApi, Loading, ErrorBox, Empty, SectionLabel, money } = ui;
  const [paper, setPaper] = useState(null);
  const q = useApi(() => api.stablesTracker(paper), [entitled, paper]);
  const d = q.data;
  const table = (title, rows) => {
    const entries = Object.entries(rows || {}).filter(([, r]) => r.bets);
    if (!entries.length) return null;
    return (
      <div className="mb-5">
        <SectionLabel>{title}</SectionLabel>
        <div style={card} className="rounded-xl p-3 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr style={{ color: c.textMuted }}>
                {["", "bets", "return", "model", "CLV", "placed", "model"].map((h, i) => <th key={i} className={"py-1 px-1 font-semibold " + (i ? "text-right" : "text-left")}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {entries.map(([k, r]) => (
                <tr key={k} style={{ borderTop: "1px solid " + c.border }}>
                  <td style={{ color: c.text }} className="py-1.5 px-1">{k}</td>
                  <td style={{ color: c.textSecondary }} className="num py-1.5 px-1 text-right">{r.settled}/{r.bets}</td>
                  <td style={{ color: (r.roi || 0) >= 0 ? c.green : c.red }} className="num py-1.5 px-1 text-right">{pctOrDash(r.roi)}</td>
                  <td style={{ color: c.textSecondary }} className="num py-1.5 px-1 text-right">{pctOrDash(r.expected_roi)}</td>
                  <td style={{ color: (r.avg_clv || 0) >= 0 ? c.green : c.orange }} className="num py-1.5 px-1 text-right">{pctOrDash(r.avg_clv)}</td>
                  <td style={{ color: c.text }} className="num py-1.5 px-1 text-right">{r.placed_rate == null ? "—" : pct(r.placed_rate, 0)}</td>
                  <td style={{ color: c.textSecondary }} className="num py-1.5 px-1 text-right">{r.model_place == null ? "—" : pct(r.model_place, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };
  const a = d?.all;
  return (
    <>
      <div className="flex gap-2 mb-4">
        {[[null, "All"], [true, "Paper"], [false, "Real"]].map(([v, l]) => (
          <button key={l} onClick={() => setPaper(v)} style={chip(paper === v)} className="text-xs font-semibold px-3.5 py-2 rounded-lg">{l}</button>
        ))}
      </div>
      {q.loading && !d && <Loading />}
      {q.error && <ErrorBox error={q.error} onRetry={q.reload} />}
      {a && a.bets === 0 && <Empty>No tracked racing bets yet. Tap a runner in Race cards and use "Add to My bets".</Empty>}
      {a && a.bets > 0 && (
        <>
          <div className="grid grid-cols-3 gap-3 mb-5">
            <div style={card} className="rounded-xl p-3"><Metric ui={ui} label="Profit" value={money(a.profit)} tone={a.profit >= 0 ? c.green : c.red} sub={`${a.settled} settled / ${a.bets}`} /></div>
            <div style={card} className="rounded-xl p-3"><Metric ui={ui} label="Return" value={pctOrDash(a.roi)} tone={(a.roi || 0) >= 0 ? c.green : c.red} sub={`model said ${pctOrDash(a.expected_roi)}`} /></div>
            <div style={card} className="rounded-xl p-3"><Metric ui={ui} label="CLV" value={pctOrDash(a.avg_clv)} tone={(a.avg_clv || 0) >= 0 ? c.green : c.orange} sub={a.beat_sp == null ? "vs Betfair SP" : `beat SP ${pct(a.beat_sp, 0)}`} /></div>
          </div>
          <p style={{ color: c.textMuted }} className="text-[11px] -mt-2 mb-5 leading-snug">
            Return vs model: did the edge the model showed turn up? CLV: your odds against Betfair SP. Steadily positive CLV is the
            earliest sign of a real edge; returns take hundreds of bets to settle down. Placed vs model checks the place chances.
          </p>
          {table("By grade", d.by_grade)}
          {table("By win odds", d.by_odds)}
          {table("By race type", d.by_race_type)}
          {table("By places paid", d.by_places)}
          {table("By bookmaker", d.by_bookmaker)}
        </>
      )}
    </>
  );
}

function CardsTab({ ui, entitled }) {
  const { c, chip, useApi, Loading, ErrorBox, Empty, SectionLabel } = ui;
  const date = null;   // always today's cards
  const [refreshes, setRefreshes] = useState(0);
  const [extra, setExtra] = useState(1);
  const [showStarted, setShowStarted] = useState(false);
  const [picked, setPicked] = useState(null);
  const open = (race, runner) => setPicked({ race, runner });
  const q = useApi(() => api.stablesRaces(date, refreshes > 0), [entitled, date, refreshes]);
  const data = q.data;
  const refreshing = q.loading && Boolean(data);
  const clock = (iso) => new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  const fed = data?.feed?.last_fetch ? clock(data.feed.last_fetch) : null;
  const updated = data?.priced_at
    ? new Date(data.priced_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
    : null;
  const [oddsKey, setOddsKeyState] = useState(() => {
    try { return localStorage.getItem("tiq_stables_odds") || "all"; } catch { return "all"; }
  });
  const setOddsKey = (k) => {
    setOddsKeyState(k);
    try { localStorage.setItem("tiq_stables_odds", k); } catch { /* private mode */ }
  };
  const [oddsOpen, setOddsOpen] = useState(false);
  const oddsFilter = ODDS_FILTERS.find((f) => f.key === oddsKey) || ODDS_FILTERS[0];
  const refreshBtn = (
    <button onClick={() => setRefreshes((n) => n + 1)} disabled={q.loading} aria-label="Refresh races"
      style={{ color: c.green, border: "1px solid rgba(54,233,143,0.35)", opacity: q.loading ? 0.6 : 1 }}
      className="ml-auto flex-shrink-0 flex items-center gap-1.5 text-xs font-semibold px-2.5 py-2 rounded-lg">
      <RefreshCw size={15} className={q.loading ? "animate-spin" : ""} />
      <span className="hidden sm:inline">{refreshing ? "Refreshing…" : "Refresh"}</span>
    </button>
  );
  return (
    <>
      {data?.feed?.error && <p style={{ color: c.orange }} className="text-[11px] mb-3">Betfair: {data.feed.error}</p>}
      {q.loading && !data && <Loading />}
      {q.error && <ErrorBox error={q.error} onRetry={q.reload} />}
      {data && data.races.length === 0 && (
        <>
          <div className="flex mb-3">{refreshBtn}</div>
          <Empty>No race cards loaded for {data.date} yet. Use “Price a race” to enter one by hand.</Empty>
        </>
      )}
      {data && data.races.length > 0 && (
        <>
          <ModelNote ui={ui} cal={data.calibration} source={data.races[0]?.probability_source} />
          <div className="flex items-center gap-2 mb-1.5">
            <span style={{ color: c.textMuted, letterSpacing: "0.08em" }} className="text-[10px] font-semibold uppercase mr-0.5">Extra places</span>
            {[0, 1, 2, 3].map((x) => (
              <button key={x} onClick={() => setExtra(x)} style={chip(x === extra)} className="text-xs font-semibold px-2.5 py-1.5 rounded-lg num">{x === 0 ? "None" : "+" + x}</button>
            ))}
            {refreshBtn}
          </div>
          {updated && <p style={{ color: c.textMuted }} className="text-[11px] text-right mb-3">Priced at {updated}{fed ? ` · Betfair ${fed}` : ""}</p>}
          <div className="mb-4">
            <button onClick={() => setOddsOpen(!oddsOpen)} style={chip(oddsFilter.key !== "all")}
              className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg">
              <Filter size={13} /> Odds: {oddsFilter.label}
              <ChevronDown size={13} style={{ transform: oddsOpen ? "rotate(180deg)" : "none" }} />
            </button>
            {oddsOpen && (
              <div className="flex flex-wrap gap-2 mt-2">
                {ODDS_FILTERS.map((f) => (
                  <button key={f.key} onClick={() => { setOddsKey(f.key); setOddsOpen(false); }} style={chip(f.key === oddsFilter.key)}
                    className="num text-xs font-semibold px-3 py-1.5 rounded-lg">{f.label}</button>
                ))}
              </div>
            )}
          </div>
          {data.can_edit_offers && <OffersPanel ui={ui} races={data.races} onSaved={q.reload} />}
          <Shortlist ui={ui} races={data.races.filter((r) => !r.started)} extra={extra} onOpen={open} oddsFilter={oddsFilter} />
          {data.opportunities.length > 0 && <OpportunityList ui={ui} list={data.opportunities.filter((o) => inOdds(oddsFilter, o.win_odds))} />}
          <SectionLabel>Races · {data.races.filter((r) => !r.started).length} to come</SectionLabel>
          {data.races.every((r) => r.started) && <Empty>All of this day's races have started.</Empty>}
          <div className="flex flex-col gap-3">
            {data.races.filter((r) => showStarted || !r.started).map((r) => (
              <div key={r.race_id} style={{ opacity: r.started ? 0.5 : 1 }}>
                <RaceCard ui={ui} race={r} extra={extra} canEdit={data.can_edit_offers} onChanged={q.reload} onOpen={open} />
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
      {data && <p style={{ color: c.textMuted }} className="text-[11px] mt-3">Prices are as loaded; check the live price and terms with the bookmaker. Tap a runner for details and to track a bet.</p>}
      {picked && <RunnerSheet ui={ui} race={picked.race} runner={picked.runner} extra={extra} onClose={() => setPicked(null)} />}
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
            <button onClick={() => setTab("tracker")} style={chip(tab === "tracker")} className="text-xs font-semibold px-3.5 py-2 rounded-lg">Tracker</button>
          </div>
          {tab === "cards" ? <CardsTab ui={ui} entitled={entitled} /> : tab === "manual" ? <ManualTab ui={ui} /> : <TrackerTab ui={ui} entitled={entitled} />}
        </>
      )}
      <StablesDisclaimer ui={ui} />
    </PageShell>
  );
}
