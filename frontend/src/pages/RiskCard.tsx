import { useEffect, useState } from "react";
import { api, RiskSummary } from "../api";
import CategoryBars from "../CategoryBars";
import { fmtTime } from "../format";


export default function RiskCard() {
  const [horizon, setHorizon] = useState(0);
  const [data, setData] = useState<RiskSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    setLoading(true);
    api.risk(horizon).then((d) => {
      const ok = d && typeof d === "object" && d.category_counts && typeof d.category_counts.low === "number" && Array.isArray(d.warnings);
      if (!ok) throw new Error("Unexpected response from the risk API (version mismatch?).");
      setData(d); setError(null);
    })
      .catch((e: Error) => { setData(null); setError(e.message); })
      .finally(() => setLoading(false));
  }, [horizon, nonce]);

  return (
    <div className="card" aria-label="Flood risk">
      <h3>Flood risk index <span className="tag not_verified">uncalibrated</span></h3>
      <label>Time{" "}
        <select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} aria-label="Risk horizon">
          <option value={0}>Latest hour (estimate)</option>
          {[1, 2, 3].map((h) => <option key={h} value={h}>+{h} h (experimental forecast)</option>)}
        </select>
      </label>
      {loading && <div className="skeleton" role="status" aria-label="Loading risk" />}
      {error && !loading && (
        <div role="alert"><p className="bad">{error}</p><button onClick={() => setNonce((n) => n + 1)}>Retry</button></div>
      )}
      {data && !loading && (
        <>
          {data.status === "unavailable" ? (
            <p className="muted"><span className="tag unavailable">unavailable</span> No risk index: rainfall data is missing, so nothing is shown rather than guessed.</p>
          ) : (
            <CategoryBars counts={data.category_counts} total={data.cells_scored} />
          )}
          {data.horizon_status === "experimental_forecast" && <p className="bad">EXPERIMENTAL: based on the provider's hourly forecast; not validated.</p>}
          {!data.reliable && data.status === "ok" && <p className="bad" role="alert">Inputs are stale or incomplete — do not rely on this.</p>}
          {data.warnings.map((w) => <p key={w} className="muted small">⚠ {w}</p>)}
          <p className="muted small">Rainfall hour ending {fmtTime(data.observation_time)} · {data.cells_scored}/{data.cells_total} cells scored · model {data.model_version}</p>
          <p className="muted small">{data.score_semantics} Categories are relative within Hyderabad. Advisory only — follow official instructions.</p>
        </>
      )}
    </div>
  );
}
