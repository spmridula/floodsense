import { CATEGORY_COLORS, FC, LAYERS, UNSCORED_COLOR, WATER_COLOR, boundsOf, continuousStops, fillColorExpression, legendFor, mergeRisk, quantile, tooltipText } from "./mapLogic";

const feat = (id: string, p: Record<string, number | string | boolean | null> = {}, x = 78.4, y = 17.4) => ({
  type: "Feature" as const, id, properties: { cell_id: id, is_water: false, ...p },
  geometry: { type: "Polygon" as const, coordinates: [[[x, y], [x + 0.01, y], [x + 0.01, y + 0.01], [x, y]]] },
});
const fc = (...f: ReturnType<typeof feat>[]): FC => ({ type: "FeatureCollection", features: f });

test("quantile interpolates and handles edges", () => {
  expect(quantile([1, 2, 3, 4, 5], 0.5)).toBe(3);
  expect(quantile([0, 10], 0.25)).toBe(2.5);
  expect(quantile([7], 0.9)).toBe(7);
  expect(quantile([1, 2, 3], 5)).toBe(3);               // clamped
  expect(Number.isNaN(quantile([], 0.5))).toBe(true);
});

test("continuous stops clip outliers, ignore nulls/NaN, and put danger at the hot end", () => {
  const vals = [...Array.from({ length: 100 }, (_, i) => i), 100000, null, undefined, NaN];
  const s = continuousStops(vals, "high")!;
  expect(s.max).toBeLessThan(200);                       // the 100000 outlier does not stretch the scale
  expect(s.stops).toHaveLength(5);
  expect(s.stops.map((x) => x[0])).toEqual([...s.stops.map((x) => x[0])].sort((a, b) => a - b));
  expect(new Set(s.stops.map((x) => x[0])).size).toBe(5);  // strictly increasing, as MapLibre requires
  const low = continuousStops(vals, "low")!;
  expect(low.stops[0][1]).toBe(s.stops[4][1]);           // reversed: lowest values are the hot colour
  expect(low.stops[4][1]).toBe(s.stops[0][1]);
});

test("degenerate inputs: no data -> null, constant data -> single stop", () => {
  expect(continuousStops([null, undefined, NaN], "high")).toBeNull();
  const c = continuousStops([5, 5, 5], "high")!;
  expect(c.stops).toHaveLength(1);
});

test("risk expression: water first, every category coloured, anything else grey", () => {
  const e = fillColorExpression("risk", null) as unknown[];
  expect(e[0]).toBe("case");
  expect(e[1]).toEqual(["==", ["get", "is_water"], true]);                 // null-safe water test
  expect(e[2]).toBe(WATER_COLOR);
  const match = e[3] as unknown[];
  expect(match[0]).toBe("match");
  expect(match[1]).toEqual(["coalesce", ["get", "category"], "none"]);     // match needs a string; null category must not error
  for (const [k, c] of Object.entries(CATEGORY_COLORS)) expect(match).toEqual(expect.arrayContaining([k, c]));
  expect(match[match.length - 1]).toBe(UNSCORED_COLOR);
});

test("continuous expression: water, numeric check, interpolate, grey fallback; no-stops -> grey", () => {
  const s = continuousStops([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10], "high")!;
  const e = fillColorExpression("depression", s) as unknown[];
  expect(JSON.stringify(e)).toContain('"interpolate"');
  expect(JSON.stringify(e)).toContain('["typeof",["get","depression_depth_m_max"]]');
  expect(e[e.length - 1]).toBe(UNSCORED_COLOR);
  expect(fillColorExpression("elevation", null)).toEqual(["case", ["==", ["get", "is_water"], true], WATER_COLOR, UNSCORED_COLOR]);
  const flat = fillColorExpression("rel_elev", continuousStops([3, 3], "low")) as unknown[];
  expect(JSON.stringify(flat)).not.toContain("interpolate");           // single colour, no invalid one-stop interpolation
});

test("every layer definition is consistent", () => {
  for (const [id, d] of Object.entries(LAYERS)) {
    expect(d.label && d.note && d.prop).toBeTruthy();
    expect(d.kind === "category" ? d.dangerWhen === null : d.dangerWhen !== null).toBe(true);
    expect(() => fillColorExpression(id as keyof typeof LAYERS, continuousStops([1, 2, 3], d.dangerWhen ?? "high"))).not.toThrow();
  }
});

test("legend: categories, gradient with danger end labelled, water-not-masked flagged", () => {
  const cat = legendFor("risk", null, true);
  expect(cat.items.map((i) => i.label)).toEqual(["low", "moderate", "high", "critical", "Water body (not scored)", "No data / not scored"]);
  const g = legendFor("rel_elev", continuousStops([-10, -5, 0, 5, 10, 15, 20], "low"), false);
  expect(g.gradient!.min).toContain("(danger)");
  expect(g.gradient!.max).not.toContain("danger");
  expect(g.items[0].label).toBe("Water not masked yet");
  expect(legendFor("flow_acc", null, true).gradient).toBeUndefined();
});

test("mergeRisk joins by cell id, leaves unknown cells null, does not mutate input", () => {
  const base = fc(feat("a"), feat("b"), feat("c"));
  const out = mergeRisk(base, [{ cell_id: "a", score: 0.5, category: "high" }, { cell_id: "zzz", score: 1, category: "critical" }]);
  expect(out.features.map((f) => f.properties.category)).toEqual(["high", null, null]);
  expect(out.features[0].properties.score).toBe(0.5);
  expect(base.features[0].properties.category).toBeUndefined();
  expect(mergeRisk(base, null).features.every((f) => f.properties.category === null)).toBe(true);
});

test("tooltips are honest about water and missing data", () => {
  expect(tooltipText({ is_water: true }, "risk")).toMatch(/Water body/);
  expect(tooltipText({ is_water: false, category: null }, "risk")).toMatch(/No risk score/);
  expect(tooltipText({ is_water: false, category: "high", score: 0.456 }, "risk")).toBe("high · index 0.46");
  expect(tooltipText({ is_water: false, depression_depth_m_max: 3.14159 }, "depression")).toBe("Depression depth: 3.14 m");
  expect(tooltipText({ is_water: false, depression_depth_m_max: null }, "depression")).toMatch(/no data/);
});

test("bounds of a collection (and empty)", () => {
  expect(boundsOf(fc(feat("a", {}, 78.2, 17.1), feat("b", {}, 78.6, 17.5)))).toEqual([[78.2, 17.1], [78.61, 17.51]]);
  expect(boundsOf(fc())).toBeNull();
});
