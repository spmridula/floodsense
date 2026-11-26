/** Evaluates the map's colour expressions with MapLibre's OWN expression engine (no WebGL needed), so colours are verified, not assumed. */
import { Color, createPropertyExpression, latest, validateStyleMin } from "@maplibre/maplibre-gl-style-spec";
import { CATEGORY_COLORS, UNSCORED_COLOR, WATER_COLOR, buildLayers, continuousStops, fillColorExpression } from "./mapLogic";

/* eslint-disable @typescript-eslint/no-explicit-any */
const spec = (latest as any).paint_fill["fill-color"];

function colorFn(expr: unknown) {
  const r: any = createPropertyExpression(expr, "paint", spec as never);
  if (r.result !== "success") throw new Error(`expression rejected by MapLibre: ${JSON.stringify(r.value)}`);
  return (props: Record<string, unknown>) => {
    const c = r.value.evaluate({ zoom: 10 }, { type: 3, properties: props });
    return [c.r, c.g, c.b].map((v: number) => Math.round(v * 255));
  };
}
const rgb = (hex: string) => { const c: any = Color.parse(hex); return [c.r, c.g, c.b].map((v: number) => Math.round(v * 255)); };
const near = (a: number[], b: number[], tol = 2) => a.every((v, i) => Math.abs(v - b[i]) <= tol);

test("risk colouring: each category, unscored, water, and malformed features all get the intended colour (never black)", () => {
  const f = colorFn(fillColorExpression("risk", null));
  for (const [cat, hex] of Object.entries(CATEGORY_COLORS)) expect(f({ category: cat, is_water: false })).toEqual(rgb(hex));
  expect(f({ category: null, is_water: false })).toEqual(rgb(UNSCORED_COLOR));
  expect(f({ category: "bogus", is_water: false })).toEqual(rgb(UNSCORED_COLOR));
  expect(f({})).toEqual(rgb(UNSCORED_COLOR));                          // property missing entirely: grey, not black
  expect(f({ category: "critical", is_water: true })).toEqual(rgb(WATER_COLOR));   // water always wins
  expect(f({ category: "low", is_water: null })).toEqual(rgb(CATEGORY_COLORS.low));
});

test("continuous colouring: ends take the cold/hot colours, middle blends, nulls and water are handled, danger orientation holds", () => {
  const values = Array.from({ length: 101 }, (_, i) => i);                 // 0..100 -> p2..p98 = 2..98
  const high = colorFn(fillColorExpression("depression", continuousStops(values, "high")));
  const low = colorFn(fillColorExpression("rel_elev", continuousStops(values, "low")));
  const hot = rgb("#ef4444"), cold = rgb("#1e3a5f");
  expect(near(high({ depression_depth_m_max: 100, is_water: false }), hot)).toBe(true);     // clamped above the top stop
  expect(near(high({ depression_depth_m_max: 0, is_water: false }), cold)).toBe(true);
  expect(near(low({ rel_elev_m_mean: 0, is_water: false }), hot)).toBe(true);               // low is dangerous -> hot
  expect(near(low({ rel_elev_m_mean: 100, is_water: false }), cold)).toBe(true);
  const mid = high({ depression_depth_m_max: 50, is_water: false });
  expect(mid).not.toEqual(hot); expect(mid).not.toEqual(cold);
  expect(high({ depression_depth_m_max: null, is_water: false })).toEqual(rgb(UNSCORED_COLOR));
  expect(high({ is_water: false })).toEqual(rgb(UNSCORED_COLOR));
  expect(high({})).toEqual(rgb(UNSCORED_COLOR));
  expect(high({ depression_depth_m_max: 50, is_water: true })).toEqual(rgb(WATER_COLOR));
  expect(colorFn(fillColorExpression("elevation", null))({ elevation_m_mean: 5, is_water: false })).toEqual(rgb(UNSCORED_COLOR));
});

test("every layer's expression is accepted by MapLibre's parser", () => {
  for (const id of ["risk", "susceptibility", "depression", "rel_elev", "flow_acc", "elevation"] as const) {
    expect(() => colorFn(fillColorExpression(id, continuousStops([1, 2, 3, 4, 5, 6], "high")))).not.toThrow();
    expect(() => colorFn(fillColorExpression(id, null))).not.toThrow();
  }
});

test("the full set of map layers and sources validates as a MapLibre style (the same specs the component adds)", () => {
  for (const layer of ["risk", "depression"] as const) {
    const style: any = {
      version: 8,
      sources: {
        osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 19, attribution: "© OpenStreetMap contributors" },
        cells: { type: "geojson", data: { type: "FeatureCollection", features: [] }, promoteId: "cell_id" },
        hotspots: { type: "geojson", data: { type: "FeatureCollection", features: [] } },
      },
      layers: [{ id: "osm", type: "raster", source: "osm", paint: { "raster-brightness-max": 0.6, "raster-saturation": -0.6, "raster-contrast": 0.1 } },
        ...buildLayers(layer, continuousStops([1, 2, 3, 4, 5, 6], "high"), "8928308280fffff")],
    };
    expect(validateStyleMin(style)).toEqual([]);
  }
  expect(validateStyleMin({ version: 8, sources: {}, layers: [{ id: "x", type: "fill", source: "nope", paint: {} }] } as any).length).toBeGreaterThan(0);   // validator is not a no-op
});
