export const CATS = ["low", "moderate", "high", "critical"] as const;
export type Counts = Record<(typeof CATS)[number], number>;

export default function CategoryBars({ counts, total }: { counts: Counts; total: number }) {
  const t = Math.max(1, total);
  return (
    <div className="bars" role="list" aria-label="Cells by category">
      {CATS.map((c) => (
        <div key={c} role="listitem" className="barrow">
          <span className={`catdot cat-${c}`} aria-hidden /> <span className="catname">{c}</span>
          <span className="barbg"><span className={`barfill cat-${c}`} style={{ width: `${(100 * counts[c]) / t}%` }} /></span>
          <span className="muted">{counts[c]}</span>
        </div>
      ))}
    </div>
  );
}
