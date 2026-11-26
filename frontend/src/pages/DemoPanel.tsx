import { useEffect, useState } from "react";
import { api, DemoFrame, DemoList, DemoRisk } from "../api";
import CategoryBars from "../CategoryBars";

export default function DemoPanel() {
  const [list, setList] = useState<DemoList | null>(null);
  const [id, setId] = useState("cloudburst");
  const [minute, setMinute] = useState(90);
  const [frame, setFrame] = useState<DemoFrame | null>(null);
  const [risk, setRisk] = useState<DemoRisk | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [riskError, setRiskError] = useState<string | null>(null);

  useEffect(() => { api.demoList().then(setList).catch((e: Error) => setError(e.message)); }, []);
  useEffect(() => { api.demoFrame(id, minute).then((f) => { setFrame(f); setError(null); }).catch((e: Error) => setError(e.message)); }, [id, minute]);
  useEffect(() => {
    api.demoRisk(id, minute).then((r) => { setRisk(r); setRiskError(null); }).catch((e: Error) => { setRisk(null); setRiskError(e.message); });
  }, [id, minute]);

  const sc = list?.scenarios.find((s) => s.id === id);
  return (
    <div className="card demo" aria-label="Synthetic demo">
      <div className="demo-banner" role="note">{list?.disclaimer ?? "SYNTHETIC DEMO DATA — not real rainfall."}</div>
      <h3>Demo scenario <span className="tag synthetic_demo">synthetic</span></h3>
      {error && <p className="bad" role="alert">{error}</p>}
      {list && (
        <>
          <label>Scenario{" "}
            <select value={id} onChange={(e) => setId(e.target.value)}>
              {list.scenarios.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
          {sc && <p className="muted">{sc.description}</p>}
          <label>Minute {minute}{" "}
            <input type="range" min={0} max={sc?.duration_minutes ?? 180} step={sc?.step_minutes ?? 15}
                   value={minute} onChange={(e) => setMinute(Number(e.target.value))} aria-label="Scenario minute" />
          </label>
        </>
      )}
      {frame && <p className="big">{frame.summary.max_mm_per_hour} <small>mm/h max (synthetic)</small> · {frame.summary.mean_mm_per_hour} <small>mean</small></p>}
      <h3>Risk engine response <span className="tag synthetic_demo">synthetic rain, real engine</span></h3>
      {riskError && <p className="bad" role="alert">{riskError}</p>}
      {risk && (
        <>
          <CategoryBars counts={risk.category_counts} total={risk.cells_scored} />
          <p className="muted small">Rain so far in this scenario: up to {risk.max_accumulation_mm} mm. {risk.score_semantics}</p>
        </>
      )}
    </div>
  );
}
