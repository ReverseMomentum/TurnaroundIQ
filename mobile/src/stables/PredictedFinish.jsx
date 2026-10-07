/**
 * Predicted finish: each runner on its own lane, placed by where the model
 * expects it to finish (expected position from the simulated races), the
 * leader nearest the finish line. Lanes inside the paid places are green.
 */
import React, { useState } from "react";

const ordinal = (n) => {
  const s = n % 100 >= 11 && n % 100 <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th";
  return n + s;
};

// Expected finishing position from P(1st)..P(9th); the rest of the field shares what is left.
function expectedPosition(r, n) {
  const pos = r.positions || [];
  let e = 0;
  let mass = 0;
  pos.forEach((p, i) => { e += (i + 1) * p; mass += p; });
  const tail = n > pos.length ? (pos.length + 1 + n) / 2 : n;
  return e + Math.max(0, 1 - mass) * tail;
}

function placeChance(r, k) {
  const top = r[`top${k}_probability`];
  if (top != null) return top;
  return (r.positions || []).slice(0, k).reduce((a, b) => a + b, 0);
}

export default function PredictedFinish({ ui, race, places, onOpen }) {
  const { c } = ui;
  const [show, setShow] = useState("place");    // which chance the labels show: "win" or "place"
  const runners = (race.runners || []).filter((r) => !r.non_runner);
  const n = runners.length;
  if (n < 2) return null;
  const rows = runners.map((r) => ({ r, e: expectedPosition(r, n), p: show === "win" ? r.win_probability || 0 : placeChance(r, places) }))
    .sort((a, b) => a.e - b.e);
  const eMin = rows[0].e;
  const eMax = rows[rows.length - 1].e;
  const span = Math.max(0.5, eMax - eMin);
  const LEFT = 14;           // % of lane width for the slowest runner
  const RIGHT = 90;          // % for the expected winner
  const at = (e) => RIGHT - ((e - eMin) / span) * (RIGHT - LEFT);
  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-2">
        <p style={{ color: c.text }} className="text-sm font-semibold">Predicted finish</p>
        <div style={{ background: c.cardAlt, border: "1px solid " + c.border }} className="flex rounded-full p-0.5">
          {[["win", "Win %"], ["place", `Top ${places} %`]].map(([k, label]) => (
            <button key={k} onClick={() => setShow(k)} className="text-[11px] font-semibold px-3 py-1 rounded-full"
              style={show === k
                ? { background: "linear-gradient(180deg, #43F09A 0%, #2BD47F 100%)", color: "#03140B" }
                : { color: c.textSecondary }}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <div style={{ border: "1px solid " + c.border, background: "#070C16" }} className="relative rounded-xl overflow-hidden">
        {/* finish line */}
        <div aria-hidden className="absolute top-0 bottom-0" style={{
          right: "6%", width: 6,
          backgroundImage: "repeating-linear-gradient(0deg, rgba(245,247,250,0.85) 0 6px, rgba(5,8,15,0.9) 6px 12px)",
          opacity: 0.55,
        }} />
        {rows.map(({ r, e, p }, i) => {
          const paid = i < places;
          const x = at(e);
          const tone = paid ? c.green : c.cyan;
          // label behind the runner if it fits there, else in front of it (lane ~340px on a phone)
          const W = 340;
          const need = (r.name.length + 5) * 7.6;
          const roomLeft = ((x - 12) / 100) * W - 18;
          const roomRight = ((91 - x) / 100) * W - 18;
          const labelLeft = roomLeft >= need || roomLeft >= roomRight;
          const nameMax = Math.max(48, (labelLeft ? roomLeft : roomRight) - 34);
          return (
            <button key={r.name} onClick={onOpen ? () => onOpen(race, r) : undefined} className="relative w-full block text-left"
              style={{
                height: 40,
                background: i % 2 ? "rgba(54,233,143,0.025)" : "rgba(54,233,143,0.055)",
                borderTop: i === places ? "1px dashed rgba(54,233,143,0.45)" : "none",
              }}>
              <span className="absolute left-2 top-1/2 -translate-y-1/2 num text-[11px] font-bold w-6 h-6 rounded-md flex items-center justify-center"
                style={{ background: paid ? "rgba(54,233,143,0.14)" : c.cardAlt, color: paid ? c.green : c.textMuted, border: "1px solid " + (paid ? "rgba(54,233,143,0.35)" : c.border) }}>
                {i + 1}
              </span>
              {/* trail */}
              <span aria-hidden className="absolute top-1/2 -translate-y-1/2 rounded-full" style={{
                left: "11%", width: `calc(${x - 11}% - 10px)`, height: 3,
                background: `linear-gradient(90deg, rgba(0,0,0,0) 0%, ${paid ? "rgba(54,233,143,0.55)" : "rgba(75,199,255,0.35)"} 100%)`,
              }} />
              {/* runner: saddle cloth */}
              <span className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 num text-[11px] font-bold rounded-md flex items-center justify-center"
                style={{ left: `${x}%`, width: 26, height: 22, background: tone, color: "#03140B",
                  boxShadow: paid ? "0 0 14px rgba(54,233,143,0.45)" : "0 0 10px rgba(75,199,255,0.25)" }}>
                {r.number ?? "•"}
              </span>
              {/* name + chance */}
              <span className="absolute top-1/2 -translate-y-1/2 text-[11px] font-semibold whitespace-nowrap"
                style={labelLeft
                  ? { right: `calc(${100 - x}% + 18px)`, color: c.text, textAlign: "right" }
                  : { left: `calc(${x}% + 18px)`, color: c.text }}>
                <span className="inline-block truncate align-bottom" style={{ maxWidth: nameMax }}>{r.name}</span>
                <span className="num ml-1" style={{ color: paid ? c.green : c.textSecondary }}>{p < 0.005 ? "<1" : Math.round(100 * p)}%</span>
              </span>
            </button>
          );
        })}
      </div>
      <p style={{ color: c.textMuted }} className="text-[10px] mt-1.5 leading-snug">
        Order by expected finishing position across 10,000 simulated races; the further right, the better it is expected
        to run. Green lanes are the {places} paid places ({ordinal(places)} and above). % shows each runner's chance
        {show === "win" ? " of winning" : ` of finishing in the top ${places}`}. A guide, not a forecast: favourites get beaten often.
      </p>
    </div>
  );
}
