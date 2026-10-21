export type Health = { status: string; version: string; time: string };
export type Ready = { status: string; checks: { name: string; ok: boolean; detail?: string | null }[] };
export type Source = {
  key: string; name: string; url: string; coverage: string; license: string; role: string;
  limitations: string; label: string; verification: string; last_checked: string | null;
};

export class ApiError extends Error {}

async function get<T>(path: string, okStatuses: number[] = [200]): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { headers: { Accept: "application/json" } });
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
};
