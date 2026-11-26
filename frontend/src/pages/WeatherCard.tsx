import { useCallback, useEffect, useState } from "react";
import { api, ApiError, WeatherSnapshot } from "../api";

import { fmtTime as fmt } from "../format";
function age(s: number | null) {
  if (s === null) return "";
  if (s < 90) return `${s}s ago`;
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  return `${(s / 3600).toFixed(1)} h ago`;
}

export default function WeatherCard() {
  const [snap, setSnap] = useState<WeatherSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMsg, setRefreshMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(async () => {
    try { setSnap(await api.weather()); setLoadError(null); }
    catch (e) { setLoadError((e as Error).message); }   // keep any snapshot we already have
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function refresh() {
    setRefreshing(true); setRefreshMsg(null);
    try { const r = await api.refreshWeather(); setRefreshMsg({ ok: true, text: r.message }); }
    catch (e) { setRefreshMsg({ ok: false, text: e instanceof ApiError ? e.message : "Refresh failed." }); }
    finally { setRefreshing(false); await load(); }
  }

  if (loading) return <div className="skeleton" role="status" aria-label="Loading weather" />;
  if (!snap) return (
    <div className="card error" role="alert"><strong>Could not load weather status.</strong> {loadError}
      <div><button onClick={() => { setLoading(true); void load(); }}>Retry</button></div></div>
  );

  const none = snap.freshness === "unavailable";
  return (
    <div className="card" aria-label="Live rainfall">
      <h3>Rainfall — live, <em>modelled</em> <span className={`tag fresh-${snap.freshness}`}>{snap.freshness}</span></h3>
      {none ? (
        <p className="muted">No weather data has been fetched yet. Nothing is shown rather than guessed.</p>
      ) : (
        <>
          <p className="big">{snap.summary.max_mm_per_hour ?? "—"} <small>mm/h max</small> · {snap.summary.mean_mm_per_hour ?? "—"} <small>mm/h mean</small></p>
          <p className="muted">Hour ending {fmt(snap.latest_valid_time)} · fetched {fmt(snap.fetched_at)} ({age(snap.age_seconds)}) · {snap.summary.points_with_value}/{snap.summary.points} points</p>
        </>
      )}
      {snap.note && <p className="bad" role="note">{snap.note}</p>}
      {snap.freshness === "stale" && <p className="bad">Data is stale. Do not rely on it.</p>}
      {snap.last_run_status === "failed" && <p className="bad" role="alert">Last refresh failed: {snap.last_error}{!none && " Showing the previous data."}</p>}
      {loadError && <p className="bad">Status could not be re-checked: {loadError}</p>}
      <p className="muted small">{snap.label_explanation} {snap.attribution}.</p>
      <button onClick={refresh} disabled={refreshing}>{refreshing ? "Refreshing…" : "Refresh now"}</button>
      {refreshMsg && <p className={refreshMsg.ok ? "ok" : "bad"} role="status">{refreshMsg.text}</p>}
    </div>
  );
}
