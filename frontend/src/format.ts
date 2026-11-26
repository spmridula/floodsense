/** Local time plus explicit UTC, so "hour ending 6:30 pm" (IST is UTC+5:30) is never ambiguous. */
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const utc = d.toISOString().slice(11, 16);
  return `${d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" })} (${utc} UTC)`;
}
