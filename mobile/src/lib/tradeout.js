// Trade-out (cash-out) maths for an open 2UP bet: back at the bookie, lay on the exchange.
//
// Outcomes are about the 2-up team: "win" = they win the match, "noWin" = draw or loss.
// Once the bookie has paid out early (2UP triggered) the back bet is a fixed profit.
// Trading out = one more exchange bet on the 2-up team at the current price that
// leaves the same total whatever happens. Exchange commission is charged on the
// exchange's net winnings in each outcome, as exchanges do per market.

export function layStakeFor(stake, back, lay, commissionPct) {
  const d = lay - commissionPct / 100;
  return d > 0 ? (back * stake) / d : 0;
}

// Totals (bookie + exchange) per outcome, after an extra exchange bet of x at price p
// (x > 0 = back the 2-up team, x < 0 = lay it).
export function outcomes({ stake, back, layStake, lay, commissionPct, paidOut }, x = 0, p = 2) {
  const c = commissionPct / 100;
  const bookWin = stake * (back - 1);
  const bookNoWin = paidOut ? stake * (back - 1) : -stake;
  const exWin = -layStake * (lay - 1) + x * (p - 1);
  const exNoWin = layStake - x;
  const net = (v) => (v > 0 ? v * (1 - c) : v);
  return { win: bookWin + net(exWin), noWin: bookNoWin + net(exNoWin) };
}

// The exchange bet that equalises both outcomes at price p.
export function tradeOut(bet, p) {
  if (!(p > 1) || !(bet.stake > 0) || !(bet.layStake > 0)) return null;
  let lo = -20 * (bet.stake + bet.layStake) * Math.max(bet.lay, 2);
  let hi = -lo;
  for (let i = 0; i < 200; i++) {
    const mid = (lo + hi) / 2;
    const o = outcomes(bet, mid, p);
    if (o.win < o.noWin) lo = mid; else hi = mid;
  }
  const x = (lo + hi) / 2;
  const o = outcomes(bet, x, p);
  return {
    action: x >= 0 ? "back" : "lay",
    stake: Math.abs(x),
    liability: x >= 0 ? Math.abs(x) : Math.abs(x) * (p - 1),
    result: (o.win + o.noWin) / 2,
  };
}
