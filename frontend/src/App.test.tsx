import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "./App";

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const HEALTH = { status: "ok", version: "0.3.0", time: "x" };
const DEMO_RISK = { label: "synthetic_demo", disclaimer: "x", scenario: "cloudburst", minute: 90, model_version: "baseline-0.1.0", score_semantics: "NOT a probability of flooding.", max_mm_per_hour: 69.9, max_accumulation_mm: 41.2, cells_total: 100, cells_scored: 100, category_counts: { low: 40, moderate: 30, high: 20, critical: 10 } };
const READY = { status: "ready", checks: [{ name: "database", ok: true, detail: "revision 0002" }] };
const snap = (o: object = {}) => ({
  label: "live_forecast", label_explanation: "Modelled precipitation from Open-Meteo (grid estimate), not a rain-gauge observation.",
  attribution: "Weather data by Open-Meteo.com", freshness: "fresh", fetched_at: "2026-10-21T12:30:00Z", age_seconds: 120,
  latest_valid_time: "2026-10-21T12:00:00Z", last_run_status: "success", last_error: null,
  summary: { points: 25, points_with_value: 25, mean_mm_per_hour: 1.2, max_mm_per_hour: 4.5 }, points: [], ...o,
});

type Handler = (init?: RequestInit) => Promise<Response>;
function mockFetch(routes: Record<string, Handler>) {
  const fn = vi.fn((url: string, init?: RequestInit) => (routes[url] ?? (() => json({ message: "nf" }, 404)))(init));
  vi.stubGlobal("fetch", fn);
  return fn;
}
const RISK = (o: object = {}) => ({
  status: "ok", reliable: true, model_version: "baseline-0.1.0", score_semantics: "Relative risk index from 0 to 1. It is NOT a probability of flooding and has not been calibrated against observed flood events.",
  horizon_hours: 0, horizon_status: "current_estimate", data_freshness: "fresh", observation_time: "2026-10-21T12:00:00Z", target_time: "2026-10-21T12:00:00Z",
  prediction_time: "2026-10-21T12:30:00Z", warnings: [], uncertainty: { available: false, reason: "x" }, cells_total: 100, cells_scored: 100, cells_without_terrain_data: 0,
  category_counts: { low: 60, moderate: 25, high: 10, critical: 5 }, ...o,
});
const base = { "/health": () => json(HEALTH), "/ready": () => json(READY), "/api/risk/summary?horizon=0": () => json(RISK()) };
const renderAt = (path = "/") => render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
afterEach(() => vi.unstubAllGlobals());

test("overview shows readiness and live rainfall with freshness, label and attribution", async () => {
  mockFetch({ ...base, "/api/weather/latest": () => json(snap()) });
  renderAt();
  expect(await screen.findByText(/● ready/)).toBeInTheDocument();
  const card = await screen.findByLabelText("Live rainfall");
  expect(within(card).getByText("fresh")).toBeInTheDocument();
  expect(within(card).getByText(/modelled/i, { selector: "em" })).toBeInTheDocument();
  expect(card).toHaveTextContent("4.5");
  expect(card).toHaveTextContent(/not a rain-gauge observation/);
  expect(card).toHaveTextContent(/Open-Meteo\.com/);
  const risk = await screen.findByLabelText("Flood risk");
  expect(await within(risk).findByText("critical")).toBeInTheDocument();
  expect(risk).toHaveTextContent(/NOT a probability/);
  expect(risk).toHaveTextContent(/uncalibrated/);
  expect(risk).toHaveTextContent(/relative within Hyderabad/);
});

test("risk card: unavailable rainfall shows no categories; missing cell table shows retryable error", async () => {
  let table = false;
  mockFetch({ ...base, "/api/weather/latest": () => json(snap()), "/api/risk/summary?horizon=0": () => (table
    ? json(RISK({ status: "unavailable", reliable: false, cells_scored: 0, category_counts: { low: 0, moderate: 0, high: 0, critical: 0 } }))
    : json({ message: "cells_res9.gpkg not found. Run: python -m app.cli build-cells" }, 503)) });
  renderAt();
  expect(await screen.findByText(/Run: python -m app.cli build-cells/)).toBeInTheDocument();
  table = true;
  await userEvent.click(screen.getAllByRole("button", { name: /retry/i }).pop()!);
  const risk = await screen.findByLabelText("Flood risk");
  await waitFor(() => expect(risk).toHaveTextContent(/nothing is shown rather than guessed/));
  expect(within(risk).queryByLabelText("Cells by category")).not.toBeInTheDocument();
});

test("risk card: forecast horizon is flagged experimental and stale inputs are flagged unreliable", async () => {
  mockFetch({ ...base, "/api/weather/latest": () => json(snap()),
    "/api/risk/summary?horizon=2": () => json(RISK({ horizon_hours: 2, horizon_status: "experimental_forecast", reliable: false, warnings: ["Weather data is stale; results should not be relied on."] })) });
  renderAt();
  const risk = await screen.findByLabelText("Flood risk");
  await userEvent.selectOptions(within(risk).getByLabelText("Risk horizon"), "2");
  expect(await within(risk).findByText(/EXPERIMENTAL/)).toBeInTheDocument();
  expect(within(risk).getByRole("alert")).toHaveTextContent(/stale or incomplete/);
  expect(risk).toHaveTextContent(/Weather data is stale/);
});

test("unavailable weather shows nothing numeric, only an explanation", async () => {
  mockFetch({ ...base, "/api/weather/latest": () => json(snap({ freshness: "unavailable", fetched_at: null, age_seconds: null, latest_valid_time: null,
    summary: { points: 0, points_with_value: 0, mean_mm_per_hour: null, max_mm_per_hour: null } })) });
  renderAt();
  const card = await screen.findByLabelText("Live rainfall");
  expect(card).toHaveTextContent(/No weather data has been fetched yet/);
  expect(card).not.toHaveTextContent("mm/h max");
});

test("data stored for a different study area is explained, not shown as current", async () => {
  mockFetch({ ...base, "/api/weather/latest": () => json(snap({ freshness: "unavailable", note: "Stored weather data is for a different study area or grid spacing. Refresh to fetch data for the current configuration.",
    summary: { points: 0, points_with_value: 0, mean_mm_per_hour: null, max_mm_per_hour: null } })) });
  renderAt();
  const card = await screen.findByLabelText("Live rainfall");
  expect(card).toHaveTextContent(/different study area/);
  expect(card).not.toHaveTextContent("mm/h max");
});

test("stale data is flagged loudly and a failed last refresh keeps old values visible", async () => {
  mockFetch({ ...base, "/api/weather/latest": () => json(snap({ freshness: "stale", age_seconds: 20000, last_run_status: "failed", last_error: "provider HTTP 503" })) });
  renderAt();
  const card = await screen.findByLabelText("Live rainfall");
  expect(card).toHaveTextContent(/Data is stale/);
  expect(within(card).getByRole("alert")).toHaveTextContent(/provider HTTP 503.*previous data/);
  expect(card).toHaveTextContent("4.5");
});

test("refresh button posts, reloads, and shows cooldown (429) message without hiding data", async () => {
  let calls = 0;
  const fn = mockFetch({ ...base, "/api/weather/latest": () => json(snap()),
    "/api/weather/refresh": () => (++calls === 1 ? json({ status: "updated", message: "Stored 150 readings for 25/25 points." })
      : json({ message: "Data is only 5s old; upstream is not re-queried within 300s." }, 429)) });
  renderAt();
  const btn = await screen.findByRole("button", { name: /refresh now/i });
  await userEvent.click(btn);
  expect(await screen.findByText(/Stored 150 readings/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /refresh now/i }));
  expect(await screen.findByText(/not re-queried within 300s/)).toBeInTheDocument();
  expect(screen.getByLabelText("Live rainfall")).toHaveTextContent("4.5");
  expect(fn.mock.calls.filter(([u, i]) => u === "/api/weather/refresh" && (i as RequestInit).method === "POST")).toHaveLength(2);
});

test("weather endpoint down shows retryable error", async () => {
  let up = false;
  mockFetch({ ...base, "/api/weather/latest": () => (up ? json(snap()) : json({ message: "boom" }, 500)) });
  renderAt();
  expect(await screen.findByText(/Could not load weather status/)).toBeInTheDocument();
  up = true;
  await userEvent.click(screen.getByRole("button", { name: /retry/i }));
  expect(await screen.findByLabelText("Live rainfall")).toBeInTheDocument();
});

test("demo mode is visibly synthetic and replaces the live card", async () => {
  mockFetch({ ...base, "/api/weather/latest": () => json(snap()),
    "/api/demo/scenarios": () => json({ label: "synthetic_demo", disclaimer: "SYNTHETIC DEMO DATA — an invented storm.",
      scenarios: [{ id: "cloudburst", name: "Cloudburst (synthetic)", description: "d", duration_minutes: 180, step_minutes: 15, frames: 13 }] }),
    "/api/demo/scenarios/cloudburst/frames/90": () => json({ label: "synthetic_demo", disclaimer: "x", scenario: "cloudburst", minute: 90, summary: { mean_mm_per_hour: 3.3, max_mm_per_hour: 69.9 } }),
    "/api/demo/risk?scenario=cloudburst&minute=90": () => json(DEMO_RISK) });
  renderAt();
  await screen.findByLabelText("Live rainfall");
  await userEvent.click(screen.getByRole("tab", { name: /demo/i }));
  const demo = await screen.findByLabelText("Synthetic demo");
  expect(await within(demo).findByText(/SYNTHETIC DEMO DATA/)).toBeInTheDocument();
  expect(demo).toHaveTextContent("69.9");
  expect(demo).toHaveTextContent(/synthetic rain, real engine/);
  const bars = await within(demo).findByLabelText("Cells by category");       // the real engine's response to the invented storm
  expect(bars).toHaveTextContent("critical");
  expect(demo).toHaveTextContent(/NOT a probability/);
  expect(demo).toHaveTextContent(/41\.2 mm/);
  expect(screen.queryByLabelText("Live rainfall")).not.toBeInTheDocument();
});

test("backend unreachable shows error with working retry", async () => {
  let fail = true;
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    if (fail) return Promise.reject(new TypeError("down"));
    return url === "/health" ? json(HEALTH) : url === "/ready" ? json(READY) : url.startsWith("/api/risk") ? json(RISK()) : json(snap());
  }));
  renderAt();
  expect((await screen.findAllByRole("alert"))[0]).toHaveTextContent(/Cannot reach/);
  fail = false;
  await userEvent.click(screen.getAllByRole("button", { name: /retry/i })[0]);
  await waitFor(() => expect(screen.getByLabelText("Live rainfall")).toBeInTheDocument());
});

test("sources page marks unverified, verified and unavailable honestly", async () => {
  mockFetch({ "/api/sources": () => json([
    { key: "a", name: "Open-Meteo", url: "https://open-meteo.com", coverage: "g", license: "l", role: "rain", limitations: "modelled", label: "live_forecast", verification: "verified", last_checked: "2026-10-21T10:00:00Z" },
    { key: "b", name: "Hotspots", url: "", coverage: "g", license: "?", role: "r", limitations: "none open", label: "unavailable", verification: "unavailable", last_checked: null },
    { key: "c", name: "DEM", url: "", coverage: "g", license: "?", role: "r", limitations: "x", label: "historical", verification: "not_verified", last_checked: null },
  ]) });
  renderAt("/sources");
  expect(await screen.findByText("Open-Meteo")).toBeInTheDocument();
  expect(screen.getByText("verified")).toBeInTheDocument();
  expect(screen.getByText("not verified")).toBeInTheDocument();
  expect(screen.getAllByText("never").length).toBe(2);
});

test("unbuilt sections are disabled with an explanation", () => {
  mockFetch({});
  renderAt();
  const item = screen.getByText(/Route planner/).closest("span")!;
  expect(item).toHaveAttribute("aria-disabled", "true");
  expect(item).toHaveAttribute("title", expect.stringMatching(/planned for Phase 5/));
});

test("a malformed risk response is contained to the risk panel; rainfall panel keeps working", async () => {
  mockFetch({ ...base, "/api/weather/latest": () => json(snap()), "/api/risk/summary?horizon=0": () => json({ unexpected: true }) });
  renderAt();
  expect(await screen.findByText(/Unexpected response from the risk API/)).toBeInTheDocument();
  expect(await screen.findByLabelText("Live rainfall")).toHaveTextContent("4.5");
});

test("a render crash inside a panel shows a contained error, not a blank page", async () => {
  const spy = vi.spyOn(console, "error").mockImplementation(() => {});
  mockFetch({ ...base, "/api/weather/latest": () => json({ ...snap(), summary: null }) });   // WeatherCard dereferences summary -> throws
  renderAt();
  expect(await screen.findByText(/Rainfall panel could not be displayed/)).toBeInTheDocument();
  expect(await screen.findByLabelText("Flood risk")).toBeInTheDocument();                      // sibling panel unaffected
  expect(screen.getByRole("heading", { name: "Overview" })).toBeInTheDocument();
  spy.mockRestore();
});

test("timestamps show local time and explicit UTC", async () => {
  const { fmtTime } = await import("./format");
  expect(fmtTime("2026-11-08T13:00:00Z")).toContain("(13:00 UTC)");
  expect(fmtTime(null)).toBe("—");
  expect(fmtTime("not a date")).toBe("—");
});

test("demo risk failure (cell table missing) is explained inside the demo panel only", async () => {
  mockFetch({ ...base, "/api/weather/latest": () => json(snap()),
    "/api/demo/scenarios": () => json({ label: "synthetic_demo", disclaimer: "SYNTHETIC DEMO DATA", scenarios: [{ id: "cloudburst", name: "C", description: "d", duration_minutes: 180, step_minutes: 15, frames: 13 }] }),
    "/api/demo/scenarios/cloudburst/frames/90": () => json({ label: "synthetic_demo", disclaimer: "x", scenario: "cloudburst", minute: 90, summary: { mean_mm_per_hour: 1, max_mm_per_hour: 2 } }),
    "/api/demo/risk?scenario=cloudburst&minute=90": () => json({ message: "cells_res9.gpkg not found. Run: python -m app.cli build-cells" }, 503) });
  renderAt();
  await screen.findByLabelText("Live rainfall");
  await userEvent.click(screen.getByRole("tab", { name: /demo/i }));
  expect(await screen.findByText(/Run: python -m app.cli build-cells/)).toBeInTheDocument();
});
