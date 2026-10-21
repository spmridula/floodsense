import { api } from "../api";
import { useAsync } from "../useAsync";

export default function Overview() {
  const health = useAsync(api.health);
  const ready = useAsync(api.ready);
  const loading = health.loading || ready.loading;
  const error = health.error ?? ready.error;

  return (
    <section>
      <h1>Overview</h1>
      <p className="muted">Phase 1 foundation: backend connectivity and system status. No rainfall or risk data is shown yet — none has been ingested.</p>
      {loading && <div className="skeleton" role="status" aria-label="Loading status" />}
      {error && !loading && (
        <div className="card error" role="alert">
          <strong>Backend unavailable.</strong> {error}
          <div><button onClick={() => { health.retry(); ready.retry(); }}>Retry</button></div>
        </div>
      )}
      {!loading && !error && health.data && ready.data && (
        <div className="grid">
          <div className="card"><h3>API</h3><p className="ok">● {health.data.status}</p><p className="muted">v{health.data.version}</p></div>
          <div className="card">
            <h3>Readiness</h3>
            <p className={ready.data.status === "ready" ? "ok" : "bad"}>● {ready.data.status}</p>
            {ready.data.checks.map((c) => <p key={c.name} className="muted">{c.name}: {c.ok ? "ok" : "failing"} — {c.detail}</p>)}
          </div>
          <div className="card"><h3>Rainfall &amp; risk</h3><p className="muted"><span className="tag unavailable">unavailable</span> Weather ingestion arrives in Phase 2.</p></div>
        </div>
      )}
    </section>
  );
}
