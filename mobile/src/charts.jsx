// Charts live in their own file so the charts library (the biggest part of the
// bundle) only downloads when a page actually draws a chart.
import React from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

// lines: [{ key, name?, color }]; colors: the app's `c` palette
export default function SimpleLineChart({ data, lines, colors: c, legend = false, formatter }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 5, right: 8, left: -20, bottom: 0 }}>
        <CartesianGrid stroke={c.border} strokeDasharray="3 3" />
        <XAxis dataKey="index" stroke={c.textSecondary} tick={{ fontSize: 11 }} />
        <YAxis stroke={c.textSecondary} tick={{ fontSize: 11 }} />
        <Tooltip contentStyle={{ background: c.cardAlt, border: "1px solid " + c.border, borderRadius: 8 }}
          labelStyle={{ color: c.text }} formatter={formatter} />
        {legend && <Legend wrapperStyle={{ fontSize: 12, color: c.textSecondary }} />}
        {lines.map((l) => (
          <Line key={l.key} type="monotone" dataKey={l.key} name={l.name || l.key} stroke={l.color} strokeWidth={2} dot={{ r: 3 }} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
