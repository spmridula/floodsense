/** Pure map logic (no WebGL): colours, legends, merging live risk into the cell GeoJSON. Fully unit-tested. */

export type Feature = { type: "Feature"; id?: string; properties: Record<string, number | string | boolean | null>; geometry: { type: "Polygon"; coordinates: number[][][] } };
export type FC = { type: "FeatureCollection"; water_masked?: boolean; features: Feature[] };
export type CellRisk = { cell_id: string; score: number | null; category: string | null };

export type LayerId = "risk" | "susceptibility" | "depression" | "rel_elev" | "flow_acc" | "elevation";

export const CATEGORY_COLORS: Record<string, string> = { low: "#14b8a6", moderate: "#f59e0b", high: "#f97316", critical: "#ef4444" };
export const UNSCORED_COLOR = "#475569";
export const WATER_COLOR = "#2b6cb0";
const RAMP = ["#1e3a5f", "#2b7a9b", "#2fb4a8", "#f2c14e", "#ef4444"]; // low danger -> high danger

export type LayerDef = {
  label: string; prop: string; unit: string; kind: "category" | "continuous";
  dangerWhen: "high" | "low" | null; note: string;
};

export const LAYERS: Record<LayerId, LayerDef> = {
  risk: { label: "Flood risk index", prop: "category", unit: "", kind: "category", dangerWhen: null,
    note: "Terrain susceptibility x modelled rainfall. Relative and uncalibrated — not a probability." },
  susceptibility: { label: "Terrain susceptibility", prop: "susceptibility", unit: "0–1", kind: "continuous", dangerWhen: "high",
    note: "Rank-based blend of five terrain proxies. Independent of current rainfall." },
  depression: { label: "Depression depth", prop: "depression_depth_m_max", unit: "m", kind: "continuous", dangerWhen: "high",
    note: "Depth of closed pits after sink-filling. Buildings on the surface model create false pits." },
  rel_elev: { label: "Height vs ~1 km surroundings", prop: "rel_elev_m_mean", unit: "m", kind: "continuous", dangerWhen: "low",
    note: "Negative = lower than surroundings. Lakes and building gaps show up here." },
  flow_acc: { label: "Upslope contributing area", prop: "flow_acc_log10_m2_max", unit: "log10 m²", kind: "continuous", dangerWhen: "high",
    note: "Where surface water would concentrate. Ignores storm drains." },
  elevation: { label: "Elevation", prop: "elevation_m_mean", unit: "m", kind: "continuous", dangerWhen: "low",
    note: "30 m surface model (buildings and trees included)." },
};

export type Stops = { min: number; max: number; stops: [number, string][] };

/** Linear-interpolated quantile of an ascending array. */
export function quantile(sorted: number[], q: number): number {
  if (sorted.length === 0) return NaN;
  const pos = (sorted.length - 1) * Math.min(1, Math.max(0, q));
  const lo = Math.floor(pos), hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

/** Colour stops spanning the 2nd–98th percentile (outliers must not wash out the scale). Danger is always the hot end. */
export function continuousStops(values: (number | null | undefined)[], dangerWhen: "high" | "low"): Stops | null {
  const v = values.filter((x): x is number => typeof x === "number" && Number.isFinite(x)).sort((a, b) => a - b);
  if (v.length === 0) return null;
  const lo = quantile(v, 0.02), hi = quantile(v, 0.98);
  if (!(hi > lo)) return { min: lo, max: lo, stops: [[lo, RAMP[2]]] };
  const colors = dangerWhen === "high" ? RAMP : [...RAMP].reverse();
  return { min: lo, max: hi, stops: colors.map((c, i) => [lo + ((hi - lo) * i) / (RAMP.length - 1), c] as [number, string]) };
}

/** MapLibre `fill-color` expression for a layer. Water is always water; missing data is always grey (never a default colour). */
export function fillColorExpression(layer: LayerId, stops: Stops | null): unknown {
  const water = ["==", ["get", "is_water"], true];        // null-safe: a missing property is "not water", never an expression error
  if (LAYERS[layer].kind === "category") {
    return ["case", water, WATER_COLOR, ["match", ["coalesce", ["get", "category"], "none"], ...Object.entries(CATEGORY_COLORS).flat(), UNSCORED_COLOR]];
  }
  const prop = LAYERS[layer].prop;
  if (!stops) return ["case", water, WATER_COLOR, UNSCORED_COLOR];
  const color = stops.stops.length === 1
    ? stops.stops[0][1]
    : ["interpolate", ["linear"], ["get", prop], ...stops.stops.flat()];
  return ["case", water, WATER_COLOR, ["==", ["typeof", ["get", prop]], "number"], color, UNSCORED_COLOR];
}

export type LegendItem = { color: string; label: string };
export function legendFor(layer: LayerId, stops: Stops | null, waterMasked: boolean): { title: string; items: LegendItem[]; gradient?: { from: string; to: string; min: string; max: string } } {
  const def = LAYERS[layer];
  const extras: LegendItem[] = [{ color: waterMasked ? WATER_COLOR : "transparent", label: waterMasked ? "Water body (not scored)" : "Water not masked yet" }, { color: UNSCORED_COLOR, label: "No data / not scored" }];
  if (def.kind === "category") {
    return { title: def.label, items: [...Object.entries(CATEGORY_COLORS).map(([k, c]) => ({ color: c, label: k })), ...extras] };
  }
  if (!stops) return { title: def.label, items: extras };
  const fmt = (n: number) => (Math.abs(n) >= 100 ? n.toFixed(0) : n.toFixed(2));
  const cold = stops.stops[0][1], hot = stops.stops[stops.stops.length - 1][1];
  return { title: `${def.label}${def.unit ? ` (${def.unit})` : ""}`, items: extras,
           gradient: { from: cold, to: hot, min: `${fmt(stops.min)}${def.dangerWhen === "low" ? " (danger)" : ""}`, max: `${fmt(stops.max)}${def.dangerWhen === "high" ? " (danger)" : ""}` } };
}

/** Join per-cell risk results onto the static geometry. Cells absent from `risk` get null (grey), never a made-up value. */
export function mergeRisk(fc: FC, risk: CellRisk[] | null): FC {
  const by = new Map((risk ?? []).map((r) => [r.cell_id, r]));
  return { ...fc, features: fc.features.map((f) => {
    const r = by.get(String(f.properties.cell_id));
    return { ...f, properties: { ...f.properties, category: r?.category ?? null, score: r?.score ?? null } };
  }) };
}

export function tooltipText(p: Feature["properties"], layer: LayerId): string {
  if (p.is_water) return "Water body — not scored";
  const def = LAYERS[layer];
  if (layer === "risk") {
    return p.category ? `${p.category} · index ${Number(p.score).toFixed(2)}` : "No risk score (missing rainfall or terrain data)";
  }
  const v = p[def.prop];
  return typeof v === "number" ? `${def.label}: ${v.toFixed(2)} ${def.unit}` : `${def.label}: no data`;
}

export function boundsOf(fc: FC): [[number, number], [number, number]] | null {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const f of fc.features) for (const [x, y] of f.geometry.coordinates[0]) { minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y); }
  return Number.isFinite(minX) ? [[minX, minY], [maxX, maxY]] : null;
}

/** Layer specs for the cell grid and hotspots. Used by the map component AND validated against MapLibre's own parser in tests. */
export function buildLayers(layer: LayerId, stops: Stops | null, selectedId: string | null) {
  return [
    { id: "cells-fill", type: "fill", source: "cells", paint: { "fill-color": fillColorExpression(layer, stops), "fill-opacity": 0.72 } },
    { id: "cells-line", type: "line", source: "cells", paint: { "line-color": "#0b1220", "line-width": 0.4, "line-opacity": 0.5 } },
    { id: "cells-selected", type: "line", source: "cells", paint: { "line-color": "#ffffff", "line-width": 2.5 }, filter: selectedFilter(selectedId) },
    { id: "hotspots-circle", type: "circle", source: "hotspots", paint: { "circle-radius": 6, "circle-color": "#a855f7", "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } },
  ] as const;
}
export const selectedFilter = (id: string | null) => ["==", ["get", "cell_id"], id ?? ""];
