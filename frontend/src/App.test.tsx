import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "./App";

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));

function mockFetch(routes: Record<string, () => Promise<Response>>) {
  vi.stubGlobal("fetch", vi.fn((url: string) => (routes[url] ?? (() => json({ message: "nf" }, 404)))()));
}
const renderAt = (path = "/") => render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
afterEach(() => vi.unstubAllGlobals());

test("overview shows API and readiness from backend", async () => {
  mockFetch({
    "/health": () => json({ status: "ok", version: "0.1.0", time: "x" }),
    "/ready": () => json({ status: "ready", checks: [{ name: "database", ok: true, detail: "revision 0001" }] }),
  });
  renderAt();
  expect(screen.getByRole("status")).toBeInTheDocument(); // skeleton while loading
  expect(await screen.findByText(/● ready/)).toBeInTheDocument();
  expect(screen.getByText(/Weather ingestion arrives in Phase 2/)).toBeInTheDocument();
});

test("shows error with working retry when backend is unreachable", async () => {
  let fail = true;
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    if (fail) return Promise.reject(new TypeError("down"));
    return url === "/health" ? json({ status: "ok", version: "0.1.0", time: "x" })
      : json({ status: "ready", checks: [] });
  }));
  renderAt();
  expect(await screen.findByRole("alert")).toHaveTextContent(/Cannot reach/);
  fail = false;
  await userEvent.click(screen.getByRole("button", { name: /retry/i }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
});

test("sources page marks unverified and unavailable honestly", async () => {
  mockFetch({
    "/api/sources": () => json([
      { key: "a", name: "Open-Meteo", url: "https://open-meteo.com", coverage: "g", license: "l", role: "rain", limitations: "modelled", label: "live_forecast", verification: "not_verified", last_checked: null },
      { key: "b", name: "Hotspots", url: "", coverage: "g", license: "?", role: "r", limitations: "none open", label: "unavailable", verification: "unavailable", last_checked: null },
    ]),
  });
  renderAt("/sources");
  expect(await screen.findByText("Open-Meteo")).toBeInTheDocument();
  expect(screen.getByText("not verified")).toBeInTheDocument();
  expect(screen.getAllByText("unavailable").length).toBeGreaterThan(0);
});

test("unbuilt sections are disabled with an explanation", () => {
  mockFetch({});
  renderAt();
  const item = screen.getByText(/Risk map/).closest("span")!;
  expect(item).toHaveAttribute("aria-disabled", "true");
  expect(item).toHaveAttribute("title", expect.stringMatching(/planned for Phase 4/));
});
