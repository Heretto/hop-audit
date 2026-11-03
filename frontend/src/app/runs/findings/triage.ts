import { CATEGORY_NAMES, IntegrityRow, Tier } from '../run.model';

export interface Recount {
  firm: number;
  review: number;
  drop: number;
  candidates: number;
  high: number;
  medium: number;
  low: number;
  categories: { code: string; label: string; n: number }[];
}

/** Counts as the triage stands; firm + review + dropped = candidates. */
export function recount(findings: IntegrityRow[]): Recount {
  const firm = findings.filter((f) => f.tier === 'firm');
  const byCategory = new Map<string, number>();
  for (const f of firm) byCategory.set(f.category, (byCategory.get(f.category) ?? 0) + 1);
  return {
    firm: firm.length,
    review: findings.filter((f) => f.tier === 'review').length,
    drop: findings.filter((f) => f.tier === 'drop').length,
    candidates: findings.length,
    high: firm.filter((f) => f.severity === 'High').length,
    medium: firm.filter((f) => f.severity === 'Medium').length,
    low: firm.filter((f) => f.severity === 'Low').length,
    categories: [...byCategory.entries()]
      .map(([code, n]) => ({ code, label: CATEGORY_NAMES[code] ?? code, n }))
      .sort((a, b) => b.n - a.n || a.code.localeCompare(b.code)),
  };
}

/** One-sheet examples in the order picked: three, then a backup. */
export function examples(findings: IntegrityRow[]): IntegrityRow[] {
  return findings
    .filter((f) => f.tier === 'firm' && f.example_rank !== null)
    .sort((a, b) => a.example_rank! - b.example_rank!);
}

export function exampleHint(n: number): string {
  if (n < 3) return `pick ${3 - n} more`;
  if (n === 3) return "add a backup in case a quote doesn't verify";
  if (n === 4) return '3 for the one-sheet plus a backup';
  return 'too many: keep 3 plus a backup';
}

export interface Filters {
  query: string;
  category: string; // '' = all
  tier: Tier | '';
  severity: string;
}

export function matches(f: IntegrityRow, filters: Filters): boolean {
  if (filters.category && f.category !== filters.category) return false;
  if (filters.tier && f.tier !== filters.tier) return false;
  if (filters.severity && f.severity !== filters.severity) return false;
  const q = filters.query.trim().toLowerCase();
  if (!q) return true;
  const haystack = [
    f.code,
    f.title,
    f.why,
    f.triage_note,
    ...f.quotes.flatMap((x) => [x.text, x.slug]),
  ];
  return haystack.join(' ').toLowerCase().includes(q);
}

/** Most of a slug kept at the end when it's shortened in the middle. */
export const SLUG_TAIL = 24;

/**
 * A slug split for middle truncation: the head shrinks with an ellipsis when
 * space runs out, the tail (its last segment, or last characters) stays whole.
 */
export function splitSlug(slug: string): [head: string, tail: string] {
  const cut = slug.lastIndexOf('/', slug.length - 2) + 1;
  const start = slug.length - cut <= SLUG_TAIL ? cut : slug.length - SLUG_TAIL;
  return [slug.slice(0, start), slug.slice(start)];
}
