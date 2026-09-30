# Wire the app to live FastAPI data

Files in `frontend/lib/`:

| File | Role |
|------|------|
| `apiClient.js` | `API_BASE`, Bearer token, `api.me/opportunities/earlyGoal/chaos` |
| `mappers.js` | FastAPI JSON → existing card props |
| `useLiveData.js` | `useMe`, `useOpportunities`, `useEarlyGoal`, `useChaos` |

## 1. Env

```bash
NEXT_PUBLIC_API_BASE=https://api.turnaroundiq.co.uk
# Local development only — never set in a store build:
# NEXT_PUBLIC_DEV_USER_ID=<your RevenueCat sandbox appUserID>
```

The app must call `setAppUserId(Purchases.appUserID)` after
`Purchases.configure()`. With no id the API returns 401 and the UI shows the
paywall. To test Pro, make a **sandbox purchase** (TestFlight / Play internal
testing) — do **not** insert entitled rows into the production `subscribers`
table: the API trusts the bearer id, so a guessable id marked Pro is free Pro
for anyone.

## 2. Import in `app.jsx` (or move lib next to the app)

```js
import { useMe, useOpportunities, useEarlyGoal, useChaos } from "./lib/useLiveData";
// or copy the three lib files into your Next project
```

Also need `useEffect` / `useCallback` if not already imported from React.

## 3. Replace `App` bootstrap

Remove simulated `subscription` state. Use:

```js
export default function App() {
  const [page, setPage] = useState("dashboard");
  const [selectedOpportunity, setSelectedOpportunity] = useState(null);
  const [alerts, setAlerts] = useState(INITIAL_ALERTS);
  const { subscription, reload: reloadMe } = useMe();
  const entitled = subscription.entitled;

  const unreadCount = alerts.filter((a) => a.unread).length;
  const markAllRead = () => setAlerts(alerts.map((a) => ({ ...a, unread: false })));

  const pages = {
    dashboard: (
      <DashboardPage
        onNavigate={setPage}
        onOpenOpportunity={setSelectedOpportunity}
        unreadCount={unreadCount}
        entitled={entitled}
      />
    ),
    opportunities: (
      <OpportunitiesPage
        onNavigate={setPage}
        onOpenOpportunity={setSelectedOpportunity}
        unreadCount={unreadCount}
        entitled={entitled}
      />
    ),
    "early-goal-hunter": (
      <EarlyGoalHunterPage onNavigate={setPage} unreadCount={unreadCount} entitled={entitled} />
    ),
    "chaos-factor": (
      <ChaosFactorPage onNavigate={setPage} unreadCount={unreadCount} entitled={entitled} />
    ),
    // ... rest unchanged
    settings: (
      <SettingsPage
        onNavigate={setPage}
        unreadCount={unreadCount}
        entitled={entitled}
        subscription={subscription}
        onRefreshMe={reloadMe}
      />
    ),
  };
  // ...
}
```

## 4. `OpportunitiesPage` — live list

```js
function OpportunitiesPage({ onNavigate, onOpenOpportunity, unreadCount, entitled }) {
  const { items, loading, error, needsPro, reload } = useOpportunities(20);

  if (!entitled || needsPro) {
    return (
      <PageShell activeTab="opportunities" onNavigate={onNavigate} unreadCount={unreadCount}>
        <PageHeader onNavigate={onNavigate} unreadCount={unreadCount} />
        <Paywall />
      </PageShell>
    );
  }

  return (
    <PageShell activeTab="opportunities" onNavigate={onNavigate} unreadCount={unreadCount}>
      <PageHeader onNavigate={onNavigate} unreadCount={unreadCount} />
      <div className="flex items-center justify-between mb-4">
        <p style={{ color: c.text }} className="text-xl font-medium">Opportunities</p>
        <button onClick={reload} style={{ color: c.cyan }} className="text-xs">Refresh</button>
      </div>
      {loading && <p style={{ color: c.textSecondary }}>Loading…</p>}
      {error && <p style={{ color: c.red }} className="text-sm">{error}</p>}
      {!loading && items.length === 0 && (
        <p style={{ color: c.textSecondary }} className="text-sm py-10 text-center">
          No opportunities right now (odds feed may be empty).
        </p>
      )}
      <div className="flex flex-col gap-3">
        {items.map((o) => (
          <OpportunityRow key={o.fixture_id} o={o} onClick={onOpenOpportunity} />
        ))}
      </div>
    </PageShell>
  );
}
```

## 5. `EarlyGoalHunterPage`

```js
function EarlyGoalHunterPage({ onNavigate, unreadCount, entitled }) {
  const { items, loading, error, needsPro, reload } = useEarlyGoal(20);

  if (!entitled || needsPro) {
    return (
      <PageShell activeTab="early-goal-hunter" onNavigate={onNavigate} unreadCount={unreadCount}>
        <PageHeader onNavigate={onNavigate} unreadCount={unreadCount} />
        <Paywall />
      </PageShell>
    );
  }

  return (
    <PageShell activeTab="early-goal-hunter" onNavigate={onNavigate} unreadCount={unreadCount}>
      <PageHeader onNavigate={onNavigate} unreadCount={unreadCount} />
      <div className="flex items-center justify-between mb-2">
        <p style={{ color: c.text }} className="text-xl font-medium">Early Goal Hunter</p>
        <button onClick={reload} style={{ color: c.cyan }} className="text-xs">Refresh</button>
      </div>
      <p style={{ color: c.textSecondary }} className="text-xs mb-4">
        Ranked by early-goal / first-scorer signal — separate from FTA opportunities.
      </p>
      {loading && <p style={{ color: c.textSecondary }}>Loading…</p>}
      {error && <p style={{ color: c.red }} className="text-sm">{error}</p>}
      {!loading && items.length === 0 && (
        <p style={{ color: c.textSecondary }} className="text-sm py-10 text-center">No fixtures scored yet.</p>
      )}
      <div className="flex flex-col gap-3">
        {items.map((f) => (
          <EarlyGoalHunterRow key={f.fixture_id} f={f} />
        ))}
      </div>
    </PageShell>
  );
}
```

## 6. `ChaosFactorPage` — use `pie` for Recharts

In `ChaosFixtureCard`, build pie from `f.pie` (not only components):

```js
const pieSource = f.pie || f.chaos_components;
const pieData = Object.entries(pieSource).map(([key, value]) => ({
  key,
  name: key,
  value,
}));
```

Page body:

```js
function ChaosFactorPage({ onNavigate, unreadCount, entitled }) {
  const { items, loading, error, needsPro, reload } = useChaos(20);
  // same loading / paywall / map pattern as Early Goal
  // items.map(f => <ChaosFixtureCard key={f.fixture_id} f={f} />)
}
```

## 7. Dashboard (optional)

Pass `useOpportunities` into dashboard or lift state; until then dashboard can keep mocks or accept `items` as props from a parent that already fetched.

## 8. Stop using mock arrays for these three

You can leave `export const opportunities` / `otherFixtures` for Storybook, but pages above should **not** import them.

## 9. CORS

API allows `CORS_ORIGINS=*` (native apps don't need CORS). Base URL: `https://api.turnaroundiq.co.uk` (Caddy → 127.0.0.1:8080).

## Field mapping (quick)

| UI prop | API |
|---------|-----|
| `book_odds` | `back_odds` |
| `ev` | `ev_percent` |
| `confidence_score` | `confidence` (0–1 → ×100) |
| `fta` style | `fta_pct` |
| `hunter_score` | same |
| `chaos_components` | `components` |
| pie slices | `pie` |
