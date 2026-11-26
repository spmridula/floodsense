import { CellDetail } from "../api";
import { fmtTime } from "../format";
import { CATEGORY_COLORS, Feature } from "./mapLogic";

type Props = {
  id: string | null; props: Feature["properties"] | null; detail: CellDetail | null; loading: boolean; error: string | null;
  demo: boolean; demoCategory: string | null; onRetry: () => void;
};

export default function CellPanel({ id, props, detail, loading, error, demo, demoCategory, onRetry }: Props) {
  if (!id || !props) return <div className="card" aria-label="Cell details"><h3>Cell details</h3><p className="muted">Click a hexagon on the map to see why it has its colour.</p></div>;
  const cat = demo ? demoCategory : detail?.category ?? null;
  return (
    <div className="card" aria-label="Cell details">
      <h3>Cell details <span className="muted small">{id}</span></h3>
      {props.is_water ? (
        <p>Water body ({Math.round(Number(props.water_fraction ?? 1) * 100)}% water). Not scored; risk for people near its edge is not represented.</p>
      ) : (
        <>
          {cat && <p><span className="catdot" style={{ background: CATEGORY_COLORS[cat] }} aria-hidden /> <strong>{cat}</strong>
            {demo && <span className="tag synthetic_demo"> synthetic rain</span>}</p>}
          {loading && !demo && <div className="skeleton" role="status" aria-label="Loading cell details" />}
          {error && !demo && <div role="alert"><p className="bad">{error}</p><button onClick={onRetry}>Retry</button></div>}
          {detail && !demo && (
            <>
              <p>{detail.explanation.summary}</p>
              {!detail.reliable && detail.status === "ok" && <p className="bad">Inputs are stale or incomplete — do not rely on this.</p>}
              {detail.horizon_status === "experimental_forecast" && <p className="bad">EXPERIMENTAL forecast hour; not validated.</p>}
              {detail.explanation.terrain_factors.length > 0 && (
                <ul className="factors">
                  {detail.explanation.terrain_factors.map((f) => (
                    <li key={f.feature}><span className={`tag ${f.kind === "proxy" ? "not_verified" : ""}`}>{f.kind.replace(/_/g, " ")}</span> {f.text}
                      <span className="barbg"><span className="barfill cat-moderate" style={{ width: `${f.rank_percentile}%` }} /></span></li>
                  ))}
                </ul>
              )}
              {detail.explanation.rainfall && <p className="muted small">{detail.explanation.rainfall.text}
                {detail.explanation.rainfall.intensity_mm_per_hour !== null && ` Now: ${detail.explanation.rainfall.intensity_mm_per_hour} mm/h; 24 h: ${detail.explanation.rainfall.accumulation_mm ?? "?"} mm.`}</p>}
              <p className="muted small">Rainfall hour: {fmtTime(detail.observation_time)} · target: {fmtTime(detail.target_time)} · data {detail.data_freshness} · model {detail.model_version}</p>
              <p className="muted small">Uncertainty: {detail.uncertainty.reason}</p>
              <details><summary className="muted small">Limitations</summary><ul className="small">{detail.limitations.map((l) => <li key={l}>{l}</li>)}</ul></details>
            </>
          )}
          <dl className="feat small">
            <dt>Elevation</dt><dd>{fmt(props.elevation_m_mean, "m")}</dd>
            <dt>Height vs surroundings</dt><dd>{fmt(props.rel_elev_m_mean, "m")}</dd>
            <dt>Depression depth</dt><dd>{fmt(props.depression_depth_m_max, "m")}</dd>
            <dt>Slope</dt><dd>{fmt(props.slope_deg_mean, "°")}</dd>
          </dl>
          <p className="muted small">Terrain values come from a 30 m surface model that includes buildings and trees.</p>
        </>
      )}
    </div>
  );
}
const fmt = (v: unknown, u: string) => (typeof v === "number" ? `${v.toFixed(1)} ${u}` : "no data");
