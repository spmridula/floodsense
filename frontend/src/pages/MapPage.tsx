import { useCallback, useEffect, useMemo, useState } from "react";
import { api, CellDetail, DemoList, Hotspot, RiskCellsResp } from "../api";
import { fmtTime } from "../format";
import CellPanel from "../map/CellPanel";
import MapView from "../map/MapView";
import { FC, LAYERS, LayerId, WATER_COLOR, continuousStops, legendFor, mergeRisk } from "../map/mapLogic";

const msg = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong.");

export default function MapPage() {
  const [fc, setFc] = useState<FC | null>(null);
  const [fcError, setFcError] = useState<string | null>(null);
  const [mode, setMode] = useState<"live" | "demo">("live");
  const [horizon, setHorizon] = useState(0);
  const [layer, setLayer] = useState<LayerId>("risk");
  const [risk, setRisk] = useState<RiskCellsResp | null>(null);
  const [riskError, setRiskError] = useState<string | null>(null);
  const [demoList, setDemoList] = useState<DemoList | null>(null);
  const [scenario, setScenario] = useState("cloudburst");
  const [minute, setMinute] = useState(90);
  const [demoDisclaimer, setDemoDisclaimer] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<CellDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [spots, setSpots] = useState<Hotspot[]>([]);
  const [markMode, setMarkMode] = useState(false);
  const [markName, setMarkName] = useState("");
  const [markMsg, setMarkMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    setFcError(null);
    api.cellsGeoJson().then(setFc).catch((e) => setFcError(msg(e)));
    api.hotspots().then((h) => setSpots(h.hotspots)).catch(() => setSpots([]));
  }, [nonce]);

  useEffect(() => {
    if (mode !== "live") return;
    setRiskError(null);
    api.riskCells(horizon).then(setRisk).catch((e) => { setRisk(null); setRiskError(msg(e)); });
  }, [mode, horizon, nonce]);

  useEffect(() => { if (mode === "demo" && !demoList) api.demoList().then(setDemoList).catch((e) => setRiskError(msg(e))); }, [mode, demoList]);
  useEffect(() => {
    if (mode !== "demo") return;
    setRiskError(null);
    api.demoCells(scenario, minute).then((d) => { setRisk({ status: "ok", reliable: true, data_freshness: "synthetic", observation_time: null, target_time: null, horizon_hours: 0,
      horizon_status: "synthetic_demo", warnings: [], cells: d.cells }); setDemoDisclaimer(d.disclaimer); }).catch((e) => { setRisk(null); setRiskError(msg(e)); });
  }, [mode, scenario, minute]);

  const loadDetail = useCallback(() => {
    const isWater = Boolean(fc?.features.find((f) => f.properties.cell_id === selected)?.properties.is_water);
    if (!selected || mode !== "live" || isWater) { setDetail(null); setDetailError(null); return; }   // water cells are never scored: no request
    setDetailLoading(true); setDetailError(null);
    api.riskCell(selected, horizon).then(setDetail).catch((e) => { setDetail(null); setDetailError(msg(e)); }).finally(() => setDetailLoading(false));
  }, [selected, horizon, mode, fc]);
  useEffect(loadDetail, [loadDetail]);

  const unavailable = mode === "live" && risk !== null && risk.status !== "ok";
  const effective: LayerId = layer === "risk" && unavailable ? "susceptibility" : layer;
  const merged = useMemo(() => (fc ? mergeRisk(fc, risk && risk.status === "ok" ? risk.cells : null) : null), [fc, risk]);
  const stops = useMemo(() => {
    const d = LAYERS[effective];
    return fc && d.kind === "continuous" ? continuousStops(fc.features.map((f) => f.properties[d.prop] as number | null), d.dangerWhen!) : null;
  }, [fc, effective]);
  const legend = legendFor(effective, stops, Boolean(fc?.water_masked));
  const selectedProps = useMemo(() => merged?.features.find((f) => f.properties.cell_id === selected)?.properties ?? null, [merged, selected]);

  async function mark(lat: number, lon: number) {
    try {
      await api.addHotspot(lat, lon, markName);
      setMarkMsg({ ok: true, text: "Spot saved." });
      setSpots((await api.hotspots()).hotspots);
    } catch (e) { setMarkMsg({ ok: false, text: msg(e) }); }
  }
  async function remove(id: string) {
    try { await api.deleteHotspot(id); setSpots((await api.hotspots()).hotspots); } catch (e) { setMarkMsg({ ok: false, text: msg(e) }); }
  }

  if (fcError) return (
    <section><h1>Risk map</h1>
      <div className="card error" role="alert"><strong>Cannot draw the map.</strong> {fcError}<div><button onClick={() => setNonce((n) => n + 1)}>Retry</button></div></div></section>
  );
  if (!fc || !merged) return <section><h1>Risk map</h1><div className="skeleton" role="status" aria-label="Loading map data" /></section>;

  const sc = demoList?.scenarios.find((s) => s.id === scenario);
  return (
    <section className="mappage">
      <h1>Risk map</h1>
      <div className="maplayout">
        <aside className="sidecol" aria-label="Map controls">
          <div className="card">
            <h3>Data</h3>
            <div role="tablist" className="modes">
              <button role="tab" aria-selected={mode === "live"} className={mode === "live" ? "on" : ""} onClick={() => setMode("live")}>Live</button>
              <button role="tab" aria-selected={mode === "demo"} className={mode === "demo" ? "on" : ""} onClick={() => setMode("demo")}>Demo (synthetic)</button>
            </div>
            {mode === "live" ? (
              <label>Time{" "}
                <select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} aria-label="Risk horizon">
                  <option value={0}>Latest hour (estimate)</option>
                  {[1, 2, 3].map((h) => <option key={h} value={h}>+{h} h (experimental)</option>)}
                </select>
              </label>
            ) : (
              <>
                <label>Scenario{" "}
                  <select value={scenario} onChange={(e) => setScenario(e.target.value)} aria-label="Demo scenario">
                    {(demoList?.scenarios ?? [{ id: "cloudburst", name: "Cloudburst (synthetic)" }]).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                </label>
                <label>Minute {minute}{" "}
                  <input type="range" min={0} max={sc?.duration_minutes ?? 180} step={sc?.step_minutes ?? 15} value={minute}
                         onChange={(e) => setMinute(Number(e.target.value))} aria-label="Scenario minute" />
                </label>
              </>
            )}
            {mode === "live" && risk && (
              <div className="status-chip" aria-label="Data status">
                <span className={`tag fresh-${risk.data_freshness}`}>{risk.data_freshness}</span>
                {!risk.reliable && risk.status === "ok" && <span className="tag unavailable">unreliable</span>}
                <p className="muted small">Rainfall hour: {fmtTime(risk.observation_time)}</p>
                {risk.horizon_status === "experimental_forecast" && <p className="bad small">EXPERIMENTAL forecast hour; not validated.</p>}
                {risk.warnings.filter((w) => !w.startsWith("EXPERIMENTAL")).map((w) => <p key={w} className="muted small">⚠ {w}</p>)}
              </div>
            )}
            {riskError && <div role="alert"><p className="bad small">{riskError}</p><button onClick={() => setNonce((n) => n + 1)}>Retry</button></div>}
            {unavailable && <p className="bad small" role="note">No rainfall data, so there is no risk index. Showing terrain susceptibility instead.</p>}
          </div>
          <div className="card">
            <h3>Layer</h3>
            <div role="radiogroup" aria-label="Map layer" className="layers">
              {(Object.keys(LAYERS) as LayerId[]).map((id) => (
                <label key={id} className="radio"><input type="radio" name="layer" checked={layer === id} onChange={() => setLayer(id)} /> {LAYERS[id].label}</label>
              ))}
            </div>
            <p className="muted small">{LAYERS[effective].note}</p>
          </div>
          <div className="card" aria-label="Legend">
            <h3>Legend — {legend.title}</h3>
            <ul className="legend">
              {legend.items.map((i) => <li key={i.label}><span className="swatch" style={{ background: i.color }} aria-hidden /> {i.label}</li>)}
            </ul>
            {legend.gradient && (
              <div><div className="gradbar" style={{ background: `linear-gradient(90deg, ${legend.gradient.from}, ${legend.gradient.to})` }} aria-hidden />
                <div className="gradlabels small"><span>{legend.gradient.min}</span><span>{legend.gradient.max}</span></div></div>
            )}
            {!fc.water_masked && <p className="bad small">Lakes are not masked yet: run <code>fetch-water</code> then <code>build-cells</code>.</p>}
          </div>
        </aside>

        <div className="mapbox">
          {mode === "demo" && <div className="demo-banner floating" role="note">{demoDisclaimer || "SYNTHETIC DEMO DATA — an invented storm."}</div>}
          {markMode && <div className="mark-banner" role="status">Marking mode: click the map where you KNOW water collects. Click the button again to stop.</div>}
          <MapView data={merged} layer={effective} stops={stops} selectedId={selected} onSelect={setSelected}
                   markMode={markMode} onMark={mark} hotspots={spots} />
        </div>

        <aside className="sidecol" aria-label="Details">
          <CellPanel id={selected} props={selectedProps} detail={detail} loading={detailLoading} error={detailError}
                     demo={mode === "demo"} demoCategory={(selectedProps?.category as string | null) ?? null} onRetry={loadDetail} />
          <div className="card" aria-label="Known flood spots">
            <h3>Spots you know flood</h3>
            <p className="muted small">Your own reports, saved on this computer and used by <code>risk-backtest</code>. Not official data; a handful of points is anecdotal.</p>
            <input value={markName} maxLength={80} onChange={(e) => setMarkName(e.target.value)} placeholder="Optional label (e.g. underpass at X)" aria-label="Spot label" />
            <button aria-pressed={markMode} onClick={() => { setMarkMode((m) => !m); setMarkMsg(null); }}>{markMode ? "Stop marking" : "Mark a spot on the map"}</button>
            {markMsg && <p className={markMsg.ok ? "ok" : "bad"} role="status">{markMsg.text}</p>}
            <ul className="spots">
              {spots.map((s) => <li key={s.id}><span style={{ color: "#a855f7" }}>●</span> {s.name || `${s.lat.toFixed(4)}, ${s.lon.toFixed(4)}`}
                <button className="linkbtn" onClick={() => remove(s.id)} aria-label={`Delete spot ${s.name || s.id}`}>delete</button></li>)}
            </ul>
            {spots.length === 0 && <p className="muted small">None yet.</p>}
          </div>
        </aside>
      </div>
      <p className="muted small">Basemap © OpenStreetMap contributors. Advisory only — follow official instructions. <span style={{ color: WATER_COLOR }}>■</span> water bodies are not scored.</p>
    </section>
  );
}
