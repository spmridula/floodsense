import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "../App";

const h = vi.hoisted(() => ({ maps: [] as any[], failConstruct: false }));   // eslint-disable-line @typescript-eslint/no-explicit-any
vi.mock("maplibre-gl", () => {
  class MapMock {
    handlers: Record<string, ((e?: unknown) => void)[]> = {}; layerHandlers: Record<string, ((e?: unknown) => void)[]> = {};
    sources: Record<string, { spec: unknown; setData: ReturnType<typeof vi.fn> }> = {}; layers: { id: string; paint?: Record<string, unknown> }[] = [];
    paint: Record<string, unknown> = {}; filters: Record<string, unknown> = {}; canvas = { style: {} as Record<string, string> };
    fitBounds = vi.fn(); remove = vi.fn(); queryRenderedFeatures = vi.fn((): unknown[] => []);
    constructor() { if (h.failConstruct) throw new Error("no webgl"); h.maps.push(this); }
    on(ev: string, a: unknown, b?: (e?: unknown) => void) {
      if (typeof a === "function") (this.handlers[ev] ||= []).push(a as never); else (this.layerHandlers[`${ev}:${a}`] ||= []).push(b!);
      return this;
    }
    addControl() {} addSource(id: string, spec: unknown) { this.sources[id] = { spec, setData: vi.fn() }; } getSource(id: string) { return this.sources[id]; }
    addLayer(l: { id: string }) { this.layers.push(l); } setPaintProperty(l: string, p: string, v: unknown) { this.paint[`${l}.${p}`] = v; }
    setFilter(l: string, f: unknown) { this.filters[l] = f; } getCanvas() { return this.canvas; }
    fire(ev: string, e?: unknown) { (this.handlers[ev] ?? []).forEach((f) => f(e)); }
  }
  class Chain { setLngLat() { return this; } setText() { return this; } addTo() { return this; } remove() { return this; } }
  return { Map: MapMock, NavigationControl: class {}, ScaleControl: class {}, Popup: Chain };
});

const json = (b: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(b), { status }));
const HEX = (id: string, p: Record<string, unknown> = {}, x = 78.4) => ({ type: "Feature", id, properties: { cell_id: id, is_water: false, susceptibility: 0.5, low_coverage: false,
  elevation_m_mean: 540, rel_elev_m_mean: -3, depression_depth_m_max: 2.5, flow_acc_log10_m2_max: 5.5, slope_deg_mean: 2, water_fraction: null, ...p },
  geometry: { type: "Polygon", coordinates: [[[x, 17.4], [x + 0.01, 17.4], [x + 0.01, 17.41], [x, 17.4]]] } });
const GEO = { type: "FeatureCollection", water_masked: true, features: [HEX("c1", { susceptibility: 0.9, depression_depth_m_max: 8 }), HEX("c2", { susceptibility: 0.2, depression_depth_m_max: 1 }, 78.42),
  HEX("lake", { is_water: true, susceptibility: null, water_fraction: 0.9, depression_depth_m_max: 0.4 }, 78.44)] };
const RISK = (o: object = {}) => ({ status: "ok", reliable: true, data_freshness: "fresh", observation_time: "2026-11-08T13:00:00Z", target_time: "2026-11-08T13:00:00Z", horizon_hours: 0,
  horizon_status: "current_estimate", warnings: [], cells: [{ cell_id: "c1", susceptibility: 0.9, score: 0.7, category: "critical" }, { cell_id: "c2", susceptibility: 0.2, score: 0.1, category: "low" }, { cell_id: "lake", susceptibility: null, score: null, category: null }], ...o });
const DETAIL = { status: "ok", reliable: true, cell_id: "c1", lat: 17.4, lon: 78.4, category: "critical", score: 0.7, susceptibility: 0.9, hazard: 0.8, model_version: "baseline-0.1.0",
  score_semantics: "NOT a probability", horizon_hours: 0, horizon_status: "current_estimate", data_freshness: "fresh", observation_time: "2026-11-08T13:00:00Z", target_time: "2026-11-08T13:00:00Z",
  prediction_time: "2026-11-08T13:20:00Z", warnings: [], uncertainty: { available: false, reason: "Not calibrated, so no uncertainty interval." }, limitations: ["Surface model artefacts."],
  explanation: { summary: "Risk index 0.70 (critical) = terrain susceptibility 0.90 x rainfall severity 0.80.", rainfall: { intensity_mm_per_hour: 40, accumulation_mm: 80, text: "Modelled rainfall, not a gauge reading." },
    terrain_factors: [{ feature: "rel_elev_m_mean", label: "Height relative to surroundings", value: -8, unit: "m", kind: "proxy", weight: 0.25, rank_percentile: 95, contribution: 0.23, text: "Height relative to surroundings: -8.0 m - lower than 95% of cells (proxy)." }] } };

type Handler = (init?: RequestInit) => Promise<Response>;
function routes(over: Record<string, Handler> = {}) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const table: Record<string, Handler> = {
    "/api/cells/geojson": () => json(GEO), "/api/risk/cells?horizon=0": () => json(RISK()), "/api/risk/cells/c1?horizon=0": () => json(DETAIL),
    "/api/hotspots": (i) => (i?.method === "POST" ? json({ id: "s1", lat: 17.4, lon: 78.4, name: "Underpass", added_at: "x" }, 201) : json({ hotspots: [], note: "", file: "f" })),
    "/api/demo/scenarios": () => json({ label: "synthetic_demo", disclaimer: "SYNTHETIC", scenarios: [{ id: "cloudburst", name: "Cloudburst (synthetic)", description: "d", duration_minutes: 180, step_minutes: 15, frames: 13 }] }),
    "/api/demo/risk/cells?scenario=cloudburst&minute=90": () => json({ label: "synthetic_demo", disclaimer: "SYNTHETIC DEMO DATA — an invented storm.", scenario: "cloudburst", minute: 90,
      cells: [{ cell_id: "c1", susceptibility: 0.9, score: 0.5, category: "high" }] }), ...over };
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => { calls.push({ url, init }); return (table[url] ?? (() => json({ message: "nf" }, 404)))(init); }));
  return calls;
}
const open = async () => {
  render(<MemoryRouter initialEntries={["/map"]}><App /></MemoryRouter>);
  await screen.findByRole("region", { name: "Flood risk map" });
  const m = h.maps[h.maps.length - 1];
  m.fire("load");
  return m;
};
beforeEach(() => { h.maps.length = 0; h.failConstruct = false; });
afterEach(() => vi.unstubAllGlobals());

test("map adds cell and hotspot layers, colours by risk category, and shows legend and data status", async () => {
  routes();
  const m = await open();
  expect(Object.keys(m.sources)).toEqual(["cells", "hotspots"]);
  expect(m.layers.map((l: { id: string }) => l.id)).toEqual(["cells-fill", "cells-line", "cells-selected", "hotspots-circle"]);
  expect(JSON.stringify(m.layers[0].paint["fill-color"])).toContain('"match"');
  const feats = m.sources.cells.spec.data.features;
  expect(feats.find((f: { id: string }) => f.id === "c1").properties.category).toBe("critical");
  expect(feats.find((f: { id: string }) => f.id === "lake").properties.category).toBeNull();   // water is never given a category
  expect(m.fitBounds).toHaveBeenCalled();
  const legend = screen.getByLabelText("Legend");
  expect(legend).toHaveTextContent(/critical/); expect(legend).toHaveTextContent(/Water body \(not scored\)/);
  expect(await screen.findByLabelText("Data status")).toHaveTextContent("fresh");
});

test("clicking a cell selects it, highlights it and shows the traceable explanation", async () => {
  routes();
  const m = await open();
  m.queryRenderedFeatures.mockReturnValue([{ properties: { cell_id: "c1" } }]);
  m.fire("click", { point: { x: 1, y: 1 }, lngLat: { lat: 17.4, lng: 78.4 } });
  const panel = await screen.findByLabelText("Cell details");
  expect(await within(panel).findByText(/Risk index 0.70 \(critical\)/)).toBeInTheDocument();
  expect(panel).toHaveTextContent(/not a gauge reading/); expect(panel).toHaveTextContent(/Not calibrated/);
  expect(panel).toHaveTextContent(/lower than 95% of cells/); expect(panel).toHaveTextContent(/proxy/);
  expect(panel).toHaveTextContent(/surface model that includes buildings/);
  await waitFor(() => expect(m.filters["cells-selected"]).toEqual(["==", ["get", "cell_id"], "c1"]));
  m.queryRenderedFeatures.mockReturnValue([]);                                              // click on empty space clears
  m.fire("click", { point: { x: 9, y: 9 }, lngLat: { lat: 17.5, lng: 78.5 } });
  await waitFor(() => expect(screen.getByLabelText("Cell details")).toHaveTextContent(/Click a hexagon/));
});

test("selecting a water cell explains it is not scored and never asks the API for a score", async () => {
  const calls = routes();
  const m = await open();
  m.queryRenderedFeatures.mockReturnValue([{ properties: { cell_id: "lake" } }]);
  m.fire("click", { point: {}, lngLat: { lat: 17.4, lng: 78.44 } });
  expect(await screen.findByText(/Water body \(90% water\)/)).toBeInTheDocument();
  await new Promise((r) => setTimeout(r, 50));                                               // give any (wrongly) triggered request time to fire
  expect(calls.some((c) => c.url.includes("/api/risk/cells/lake"))).toBe(false);
});

test("switching layer recolours the map with a gradient and a danger-labelled legend", async () => {
  routes();
  const m = await open();
  await userEvent.click(screen.getByLabelText("Depression depth"));
  await waitFor(() => expect(JSON.stringify(m.paint["cells-fill.fill-color"])).toContain('"interpolate"'));
  expect(screen.getByLabelText("Legend")).toHaveTextContent(/\(danger\)/);
  await userEvent.click(screen.getByLabelText("Flood risk index"));
  await waitFor(() => expect(JSON.stringify(m.paint["cells-fill.fill-color"])).toContain('"match"'));
});

test("no rainfall data: explains why and falls back to terrain susceptibility instead of an empty risk map", async () => {
  routes({ "/api/risk/cells?horizon=0": () => json(RISK({ status: "unavailable", reliable: false, data_freshness: "unavailable", cells: [] })) });
  const m = await open();
  expect(await screen.findByText(/no risk index. Showing terrain susceptibility instead/i)).toBeInTheDocument();
  await waitFor(() => expect(JSON.stringify(m.paint["cells-fill.fill-color"] ?? "")).toContain("interpolate"));
});

test("stale data is flagged unreliable on the map", async () => {
  routes({ "/api/risk/cells?horizon=0": () => json(RISK({ data_freshness: "stale", reliable: false, warnings: ["Weather data is stale; results should not be relied on."] })) });
  await open();
  const chip = await screen.findByLabelText("Data status");
  expect(chip).toHaveTextContent("stale"); expect(chip).toHaveTextContent("unreliable"); expect(chip).toHaveTextContent(/Weather data is stale/);
});

test("demo mode shows the synthetic banner, loads synthetic per-cell results and hides forecast horizons", async () => {
  routes();
  const m = await open();
  await userEvent.click(screen.getByRole("tab", { name: /demo/i }));
  expect(await screen.findByText(/SYNTHETIC DEMO DATA — an invented storm/)).toBeInTheDocument();
  expect(screen.queryByLabelText("Risk horizon")).not.toBeInTheDocument();
  await waitFor(() => expect(m.sources.cells.setData).toHaveBeenCalled());
  const merged = m.sources.cells.setData.mock.calls.at(-1)[0].features;
  expect(merged.find((f: { id: string }) => f.id === "c1").properties.category).toBe("high");
  m.queryRenderedFeatures.mockReturnValue([{ properties: { cell_id: "c1" } }]);
  m.fire("click", { point: {}, lngLat: { lat: 17.4, lng: 78.4 } });
  expect(await screen.findByText(/synthetic rain/)).toBeInTheDocument();
});

test("marking a spot posts the click position and label, lists it, and shows server errors", async () => {
  let n = 0;
  const calls = routes({ "/api/hotspots": (i) => {
    if (i?.method === "POST") return ++n === 1 ? json({ id: "s1", lat: 17.4, lon: 78.4, name: "Underpass", added_at: "x" }, 201) : json({ message: "A spot is already marked in this cell." }, 409);
    return json({ hotspots: n ? [{ id: "s1", lat: 17.4, lon: 78.4, name: "Underpass", added_at: "x" }] : [], note: "", file: "f" });
  } });
  const m = await open();
  await userEvent.type(screen.getByLabelText("Spot label"), "Underpass");
  await userEvent.click(screen.getByRole("button", { name: /mark a spot/i }));
  expect(screen.getByText(/Marking mode: click the map/)).toBeInTheDocument();
  m.fire("click", { point: {}, lngLat: { lat: 17.4321, lng: 78.3987 } });
  expect(await screen.findByText("Spot saved.")).toBeInTheDocument();
  const post = calls.find((c) => c.init?.method === "POST")!;
  expect(JSON.parse(post.init!.body as string)).toEqual({ lat: 17.4321, lon: 78.3987, name: "Underpass" });
  expect(await screen.findByText("Underpass", { selector: "li" })).toBeInTheDocument();
  m.fire("click", { point: {}, lngLat: { lat: 17.4321, lng: 78.3987 } });
  expect(await screen.findByText(/already marked/)).toBeInTheDocument();
  expect(m.queryRenderedFeatures).not.toHaveBeenCalled();                                      // marking mode never selects cells
});

test("deleting a spot calls DELETE", async () => {
  let alive = true;
  const calls = routes({ "/api/hotspots": () => json({ hotspots: alive ? [{ id: "s9", lat: 17.4, lon: 78.4, name: "Old", added_at: "x" }] : [], note: "", file: "f" }),
    "/api/hotspots/s9": () => { alive = false; return json({ deleted: "s9" }); } });
  await open();
  await userEvent.click(await screen.findByRole("button", { name: /delete spot Old/i }));
  await waitFor(() => expect(screen.getByText("None yet.")).toBeInTheDocument());
  expect(calls.some((c) => c.url === "/api/hotspots/s9" && c.init?.method === "DELETE")).toBe(true);
});

test("cell table missing: clear message with retry, no map attempted", async () => {
  let ok = false;
  routes({ "/api/cells/geojson": () => (ok ? json(GEO) : json({ message: "cells_res9.gpkg not found. Run: python -m app.cli build-cells" }, 503)) });
  render(<MemoryRouter initialEntries={["/map"]}><App /></MemoryRouter>);
  expect(await screen.findByText(/Run: python -m app.cli build-cells/)).toBeInTheDocument();
  expect(h.maps).toHaveLength(0);
  ok = true;
  await userEvent.click(screen.getByRole("button", { name: /retry/i }));
  expect(await screen.findByRole("region", { name: "Flood risk map" })).toBeInTheDocument();
});

test("WebGL unavailable: readable explanation, and the rest of the page still works", async () => {
  routes(); h.failConstruct = true;
  render(<MemoryRouter initialEntries={["/map"]}><App /></MemoryRouter>);
  expect(await screen.findByText(/needs WebGL/)).toBeInTheDocument();
  expect(screen.getByLabelText("Legend")).toBeInTheDocument();
});

test("water layer missing: legend tells the user how to fix it", async () => {
  routes({ "/api/cells/geojson": () => json({ ...GEO, water_masked: false }) });
  await open();
  expect(await screen.findByText(/Lakes are not masked yet/)).toBeInTheDocument();
});

test("a failing live-risk API shows an error with retry but the terrain map still draws", async () => {
  routes({ "/api/risk/cells?horizon=0": () => json({ message: "boom" }, 500) });
  const m = await open();
  expect(await screen.findByText("boom")).toBeInTheDocument();
  expect(m.sources.cells).toBeDefined();
});

test("a map with every cell the same value draws a single colour rather than an invalid one-stop gradient", async () => {
  routes({ "/api/cells/geojson": () => json({ ...GEO, features: GEO.features.map((f) => ({ ...f, properties: { ...f.properties, depression_depth_m_max: 2 } })) }) });
  const m = await open();
  await userEvent.click(screen.getByLabelText("Depression depth"));
  await waitFor(() => expect(m.paint["cells-fill.fill-color"]).toBeDefined());
  expect(JSON.stringify(m.paint["cells-fill.fill-color"])).not.toContain("interpolate");
});
