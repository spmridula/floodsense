import { useState } from "react";
import { api } from "../api";
import { useAsync } from "../useAsync";
import DemoPanel from "./DemoPanel";
import ErrorBoundary from "../ErrorBoundary";
import RiskCard from "./RiskCard";
import WeatherCard from "./WeatherCard";

export default function Overview() {
  const health = useAsync(api.health);
  const ready = useAsync(api.ready);
  const [mode, setMode] = useState<"live" | "demo">("live");
  const loading = health.loading || ready.loading;
  const error = health.error ?? ready.error;

  return (
    <section>
      <h1>Overview</h1>
      <p className="muted">Phase 3: live modelled rainfall, a baseline flood-risk index (uncalibrated, relative), and a separate synthetic demo mode.</p>
      <div role="tablist" className="modes">
        <button role="tab" aria-selected={mode === "live"} className={mode === "live" ? "on" : ""} onClick={() => setMode("live")}>Live data</button>
        <button role="tab" aria-selected={mode === "demo"} className={mode === "demo" ? "on" : ""} onClick={() => setMode("demo")}>Demo (synthetic)</button>
      </div>
      {loading && <div className="skeleton" role="status" aria-label="Loading status" />}
      {error && !loading && (
        <div className="card error" role="alert">
          <strong>Backend unavailable.</strong> {error}
          <div><button onClick={() => { health.retry(); ready.retry(); }}>Retry</button></div>
        </div>
      )}
      {!loading && !error && health.data && ready.data && (
        <>
          <div className="card status" aria-label="System status">
            <span className="ok">● {health.data.status}</span> <span className="muted">API v{health.data.version}</span>
            <span className={ready.data.status === "ready" ? "ok" : "bad"}>● {ready.data.status}</span>
            {ready.data.checks.map((c) => <span key={c.name} className="muted">{c.name}: {c.ok ? "ok" : "failing"} — {c.detail}</span>)}
          </div>
          <div className="grid2">
            {mode === "live" ? (
              <>
                <ErrorBoundary label="Rainfall panel"><WeatherCard /></ErrorBoundary>
                <ErrorBoundary label="Risk panel"><RiskCard /></ErrorBoundary>
              </>
            ) : (
              <ErrorBoundary label="Demo panel"><DemoPanel /></ErrorBoundary>
            )}
          </div>
        </>
      )}
    </section>
  );
}
