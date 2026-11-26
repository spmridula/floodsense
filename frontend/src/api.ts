import type { FC } from "./map/mapLogic";
export type Health = { status: string; version: string; time: string };
export type Ready = { status: string; checks: { name: string; ok: boolean; detail?: string | null }[] };
export type Source = {
  key: string; name: string; url: string; coverage: string; license: string; role: string;
  limitations: string; label: string; verification: string; last_checked: string | null;
};

export type WeatherPoint = { point_id: string; lat: number; lon: number; valid_time: string; precipitation_mm: number | null; was_forecast_when_fetched: boolean };
export type WeatherSnapshot = {
  label: string; label_explanation: string; attribution: string; note?: string | null;
  freshness: "fresh" | "aging" | "stale" | "unavailable";
  fetched_at: string | null; age_seconds: number | null; latest_valid_time: string | null;
  last_run_status: string | null; last_error: string | null;
  summary: { points: number; points_with_value: number; mean_mm_per_hour: number | null; max_mm_per_hour: number | null };
  points: WeatherPoint[];
};
export type DemoScenario = { id: string; name: string; description: string; duration_minutes: number; step_minutes: number; frames: number };
export type DemoList = { label: string; disclaimer: string; scenarios: DemoScenario[] };
export type DemoFrame = { label: string; disclaimer: string; scenario: string; minute: number; summary: { mean_mm_per_hour: number; max_mm_per_hour: number } };

export type RiskSummary = {
  status: "ok" | "unavailable"; reliable: boolean; model_version: string; score_semantics: string;
  horizon_hours: number; horizon_status: "current_estimate" | "experimental_forecast"; data_freshness: string;
  observation_time: string | null; target_time: string | null; prediction_time: string; warnings: string[];
  uncertainty: { available: boolean; reason: string };
  cells_total: number; cells_scored: number; cells_without_terrain_data: number;
  category_counts: { low: number; moderate: number; high: number; critical: number };
};

export type DemoRisk = {
  label: string; disclaimer: string; scenario: string; minute: number; model_version: string; score_semantics: string;
  max_mm_per_hour: number; max_accumulation_mm: number; cells_total: number; cells_scored: number;
  category_counts: { low: number; moderate: number; high: number; critical: number };
};

export type RiskCellsResp = {
  status: string; reliable: boolean; data_freshness: string; observation_time: string | null; target_time: string | null;
  horizon_hours: number; horizon_status: string; warnings: string[];
  cells: { cell_id: string; susceptibility: number | null; score: number | null; category: string | null }[];
};
export type CellFactor = { feature: string; label: string; value: number; unit: string; kind: string; weight: number; rank_percentile: number; contribution: number; text: string };
export type CellDetail = {
  status: string; reliable: boolean; cell_id: string; lat: number; lon: number; category: string | null; score: number | null;
  susceptibility: number | null; hazard?: number | null; model_version: string; score_semantics: string; horizon_hours: number;
  horizon_status: string; data_freshness: string; observation_time: string | null; target_time: string | null; prediction_time: string;
  warnings: string[]; uncertainty: { available: boolean; reason: string }; limitations: string[];
  explanation: { summary: string; terrain_factors: CellFactor[];
    rainfall: { intensity_mm_per_hour: number | null; accumulation_mm: number | null; text: string } | null };
};
export type Hotspot = { id: string; lat: number; lon: number; name: string; added_at: string };
export type DemoCellsResp = { label: string; disclaimer: string; scenario: string; minute: number; cells: RiskCellsResp["cells"] };

export class ApiError extends Error {}

async function get<T>(path: string, okStatuses: number[] = [200], method = "GET", body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method, headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Cannot reach the FloodSense backend. Is it running?");
  }
  if (!okStatuses.includes(res.status)) {
    const body = await res.json().catch(() => null);
    throw new ApiError(body?.message ?? `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => get<Health>("/health"),
  ready: () => get<Ready>("/ready", [200, 503]),
  sources: () => get<Source[]>("/api/sources"),
  risk: (horizon: number) => get<RiskSummary>(`/api/risk/summary?horizon=${horizon}`),
  cellsGeoJson: () => get<FC>("/api/cells/geojson"),
  riskCells: (h: number) => get<RiskCellsResp>(`/api/risk/cells?horizon=${h}`),
  riskCell: (id: string, h: number) => get<CellDetail>(`/api/risk/cells/${encodeURIComponent(id)}?horizon=${h}`),
  demoCells: (id: string, m: number) => get<DemoCellsResp>(`/api/demo/risk/cells?scenario=${id}&minute=${m}`),
  hotspots: () => get<{ hotspots: Hotspot[]; note: string; file: string }>("/api/hotspots"),
  addHotspot: (lat: number, lon: number, name: string) => get<Hotspot>("/api/hotspots", [201], "POST", { lat, lon, name }),
  deleteHotspot: (id: string) => get<{ deleted: string }>(`/api/hotspots/${encodeURIComponent(id)}`, [200], "DELETE"),
  weather: () => get<WeatherSnapshot>("/api/weather/latest"),
  refreshWeather: () => get<{ message: string }>("/api/weather/refresh", [200], "POST"),
  demoList: () => get<DemoList>("/api/demo/scenarios"),
  demoRisk: (id: string, minute: number) => get<DemoRisk>(`/api/demo/risk?scenario=${id}&minute=${minute}`),
  demoFrame: (id: string, minute: number) => get<DemoFrame>(`/api/demo/scenarios/${id}/frames/${minute}`),
};
