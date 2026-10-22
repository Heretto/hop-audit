import { RunListItem } from '../run.model';

/** Completed, analyzed runs: the ones that have a score and can be compared. */
export function scored(runs: RunListItem[]): RunListItem[] {
  return runs.filter(
    (r) => r.status === 'completed' && r.metrics.score !== undefined && r.metrics.score !== null,
  );
}

/** Whole-site runs for the score chart, oldest first. */
export function chartPoints(runs: RunListItem[]): { number: number; score: number; id: string }[] {
  return scored(runs)
    .filter((r) => r.scope.mode === 'site')
    .sort((a, b) => a.number - b.number)
    .map((r) => ({ number: r.number, score: r.metrics.score!, id: r.id }));
}

/** Each scored run's change from the scored run before it, for the same site. */
export function scoreDeltas(runs: RunListItem[]): Map<string, number> {
  const out = new Map<string, number>();
  const bySite = new Map<string, RunListItem[]>();
  for (const r of scored(runs)) bySite.set(r.site_id, [...(bySite.get(r.site_id) ?? []), r]);
  for (const list of bySite.values()) {
    list.sort((a, b) => a.number - b.number);
    list.forEach((r, i) => {
      if (i > 0) out.set(r.id, r.metrics.score! - list[i - 1].metrics.score!);
    });
  }
  return out;
}

/** The latest two scored runs of a site, earlier first, as the default comparison. */
export function defaultPair(runs: RunListItem[]): [string, string] | null {
  const list = scored(runs).sort((a, b) => b.number - a.number);
  return list.length >= 2 ? [list[1].id, list[0].id] : null;
}

/** CSV of a comparison's metric rows. */
export function comparisonCsv(
  rows: { label: string; a: number | null; b: number | null; delta: number | null }[],
  a: number,
  b: number,
): string {
  const cell = (v: number | null) => (v === null ? '' : String(v));
  return [
    `Metric,#${a},#${b},Change`,
    ...rows.map((r) => `"${r.label}",${cell(r.a)},${cell(r.b)},${cell(r.delta)}`),
  ].join('\n');
}
