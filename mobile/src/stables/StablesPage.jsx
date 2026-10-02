/**
 * The Stables: horse racing extra-place value.
 *
 * Kept out of App.jsx so racing work doesn't collide with football edits.
 * App.jsx passes its design system in as `ui` (colours, card styles,
 * PageShell, Paywall, ...), so this page looks like every other page.
 */
import React, { useMemo, useState } from "react";
import { ChevronDown, Info } from "lucide-react";
import { api } from "../lib/api";

const pct = (v, dp = 1) => (v == null || isNaN(v) ? "—" : (100 * Number(v)).toFixed(dp) + "%");
const signedPct = (v, dp = 1) => (v == null || isNaN(v) ? "—" : (v >= 0 ? "+" : "") + (100 * Number(v)).toFixed(dp) + "%");
const pts = (v) => (v == null || isNaN(v) ? "—" : (v >= 0 ? "+" : "") + (100 * Number(v)).toFixed(1) + " pts");
const fractionLabel = (f) => (f ? "1/" + Math.round(1 / f) : "—");
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
        <Metric ui={ui} label={`Top ${o.places_paid}`} value={pct(o.model_probability)} tone={c.green} sub="model" />
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

function RunnerTable({ ui, race }) {
  const { c } = ui;
  const th = { color: c.textMuted, letterSpacing: "0.1em" };
  const cols = ["Win", "Top 3", "Top 4", "Top 5", "4th", "5th"];
  return (
    <div className="overflow-x-auto -mx-1">
      <table className="w-full text-xs lg:text-sm">
        <thead>
          <tr style={{ borderBottom: "1px solid " + c.border }}>
            <th style={th} className="text-[10px] font-semibold uppercase py-2 px-1 text-left">Runner</th>
            <th style={th} className="text-[10px] font-semibold uppercase py-2 px-1 text-right">Odds</th>
            {cols.map((h) => <th key={h} style={th} className={"text-[10px] font-semibold uppercase py-2 px-1 text-right" + (h === "Top 3" || h === "Top 4" ? " hidden lg:table-cell" : "")}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {race.runners.map((r) => {
            const value = race.opportunities.some((o) => o.horse === r.name && (o.grade === "A" || o.grade === "B"));
            return (
              <tr key={r.name} style={{ borderBottom: "1px solid " + c.border }}>
                <td className="py-2 px-1 max-w-[104px] lg:max-w-[220px] truncate" style={{ color: value ? c.green : c.text }}>{r.number ? <span style={{ color: c.textMuted }} className="num mr-1">{r.number}</span> : null}{r.name}</td>
                <td style={{ color: c.textSecondary }} className="num py-2 px-1 text-right">{r.best_win_odds ? Number(r.best_win_odds).toFixed(2) : "—"}</td>
                <td style={{ color: c.text }} className="num py-2 px-1 text-right">{pct(r.win_probability)}</td>
                <td style={{ color: c.text }} className="num py-2 px-1 text-right hidden lg:table-cell">{pct(r.top3_probability)}</td>
                <td style={{ color: c.text }} className="num py-2 px-1 text-right hidden lg:table-cell">{pct(r.top4_probability)}</td>
                <td style={{ color: c.text }} className="num py-2 px-1 text-right">{pct(r.top5_probability)}</td>
                <td style={{ color: c.orange }} className="num py-2 px-1 text-right">{pct(r.positions[3])}</td>
                <td style={{ color: c.orange }} className="num py-2 px-1 text-right">{pct(r.positions[4])}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RaceCard({ ui, race }) {
  const { c, card } = ui;
  const [open, setOpen] = useState(false);
  const strong = race.opportunities.filter((o) => o.grade === "A" || o.grade === "B").length;
  const offers = (race.offers || []).map((t) => `${t.bookmaker} ${t.places} pl ${fractionLabel(t.fraction)}`).join(" · ");
  return (
    <div style={card} className="rounded-xl p-4">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between gap-3 text-left">
        <div className="min-w-0">
          <p style={{ color: c.text }} className="text-sm font-semibold truncate">
            {race.time && <span className="num mr-2">{race.time}</span>}{race.course || race.name || "Race"}
          </p>
          <p style={{ color: c.textMuted }} className="text-xs truncate">
            {race.field_size} runners{race.handicap ? " · handicap" : ""}{race.going ? " · " + race.going : ""} · {offers}
          </p>
        </div>
        <span className="flex items-center gap-2 flex-shrink-0">
          {strong > 0 && <span style={{ color: c.green }} className="text-xs font-semibold">{strong} value</span>}
          <ChevronDown size={16} style={{ color: c.textMuted, transform: open ? "rotate(180deg)" : "none" }} />
        </span>
      </button>
      {open && <div className="mt-3"><RunnerTable ui={ui} race={race} /></div>}
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

function CardsTab({ ui, entitled }) {
  const { c, chip, useApi, Loading, ErrorBox, Empty, SectionLabel } = ui;
  const [date, setDate] = useState(null);
  const q = useApi(() => api.stablesRaces(date), [entitled, date]);
  const data = q.data;
  const dates = useMemo(() => {
    const ds = new Set(data?.dates || []);
    if (data?.date) ds.add(data.date);
    return [...ds].sort().reverse().slice(0, 10);
  }, [data]);
  return (
    <>
      {dates.length > 1 && (
        <div className="no-scrollbar flex gap-2 overflow-x-auto mb-4 -mx-1 px-1">
          {dates.map((d) => (
            <button key={d} onClick={() => setDate(d)} style={chip(d === data?.date)} className="flex-shrink-0 text-xs font-semibold px-3.5 py-2 rounded-lg whitespace-nowrap num">{d}</button>
          ))}
        </div>
      )}
      {q.loading && <Loading />}
      {q.error && <ErrorBox error={q.error} onRetry={q.reload} />}
      {data && data.races.length === 0 && (
        <Empty>No race cards loaded for {data.date} yet. Use “Price a race” to enter one by hand.</Empty>
      )}
      {data && data.races.length > 0 && (
        <>
          <ModelNote ui={ui} cal={data.calibration} source={data.races[0]?.probability_source} />
          <OpportunityList ui={ui} list={data.opportunities} />
          <SectionLabel>Races · {data.races.length}</SectionLabel>
          <div className="flex flex-col gap-3">{data.races.map((r) => <RaceCard key={r.race_id} ui={ui} race={r} />)}</div>
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
            {label("Race type")}
            <div className="flex gap-2">
              <button onClick={() => setHandicap(true)} style={chip(handicap)} className="text-xs font-semibold px-3 py-2 rounded-lg">Handicap</button>
              <button onClick={() => setHandicap(false)} style={chip(!handicap)} className="text-xs font-semibold px-3 py-2 rounded-lg">Other</button>
            </div>
          </div>
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
