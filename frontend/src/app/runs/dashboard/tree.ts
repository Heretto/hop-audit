import { PageRow, SectionRow } from '../run.model';

export type Show = 'all' | 'broken' | 'seo' | 'flesch50' | 'failed' | 'findings' | 'focus';
export type Sort = 'path' | 'score' | 'issues';
export const PAGE_LIMIT = 50; // pages shown per open section before "Show all"

export type TreeRow =
  | {
      kind: 'section';
      section: SectionRow;
      open: boolean;
      matching: number;
      findings: number;
      focus: number;
    }
  | { kind: 'page'; page: PageRow }
  | { kind: 'more'; section: string; hidden: number };

const issues = (p: PageRow) =>
  (p.broken_links ?? 0) + (p.seo_issues ?? 0) + (p.anchor_issues ?? 0) + p.findings;

/** "5 findings · 1 on focus", or "" for none. */
export function findingsLabel(findings: number, focus: number): string {
  if (!findings) return '';
  const base = `${findings} finding${findings === 1 ? '' : 's'}`;
  return focus ? `${base} · ${focus} on focus` : base;
}

export function matches(page: PageRow, query: string, show: Show): boolean {
  const q = query.trim().toLowerCase();
  if (q && !`${page.path} ${page.title}`.toLowerCase().includes(q)) return false;
  switch (show) {
    case 'broken':
      return (page.broken_links ?? 0) > 0;
    case 'seo':
      return (page.seo_issues ?? 0) > 0;
    case 'flesch50':
      return page.flesch !== null && page.flesch < 50;
    case 'failed':
      return page.http_status !== 200;
    case 'findings':
      return page.findings > 0;
    case 'focus':
      return page.focus_findings > 0;
    default:
      return true;
  }
}

export function sortPages(pages: PageRow[], sort: Sort): PageRow[] {
  const copy = [...pages];
  if (sort === 'score')
    copy.sort((a, b) => (a.score ?? 101) - (b.score ?? 101) || a.path.localeCompare(b.path));
  else if (sort === 'issues')
    copy.sort((a, b) => issues(b) - issues(a) || a.path.localeCompare(b.path));
  else copy.sort((a, b) => a.path.localeCompare(b.path));
  return copy;
}

export interface TreeState {
  query: string;
  show: Show;
  sort: Sort;
  open: Set<string>; // sections opened by hand
  closed: Set<string>; // sections closed by hand while a filter opens them
  expanded: Set<string>; // sections showing all their pages
}

export function isFiltering(state: Pick<TreeState, 'query' | 'show'>): boolean {
  return !!state.query.trim() || state.show !== 'all';
}

/**
 * Section rows with their pages under the open ones. With a filter, only
 * sections holding matches are listed, and they open unless closed by hand.
 */
export function buildTree(sections: SectionRow[], pages: PageRow[], opts: TreeState): TreeRow[] {
  const filtering = isFiltering(opts);
  const bySection = new Map<string, PageRow[]>();
  const totals = new Map<string, { findings: number; focus: number }>();
  for (const page of pages) {
    const t = totals.get(page.section) ?? { findings: 0, focus: 0 };
    totals.set(page.section, {
      findings: t.findings + page.findings,
      focus: t.focus + page.focus_findings,
    });
    if (!matches(page, opts.query, opts.show)) continue;
    bySection.set(page.section, [...(bySection.get(page.section) ?? []), page]);
  }
  const rows: TreeRow[] = [];
  for (const section of sections) {
    const mine = bySection.get(section.path) ?? [];
    if (filtering && !mine.length) continue;
    const open = filtering ? !opts.closed.has(section.path) : opts.open.has(section.path);
    const t = totals.get(section.path) ?? { findings: 0, focus: 0 };
    rows.push({ kind: 'section', section, open, matching: mine.length, ...t });
    if (!open) continue;
    const sorted = sortPages(mine, opts.sort);
    const shown = opts.expanded.has(section.path) ? sorted : sorted.slice(0, PAGE_LIMIT);
    rows.push(...shown.map((page) => ({ kind: 'page' as const, page })));
    if (shown.length < sorted.length)
      rows.push({ kind: 'more', section: section.path, hidden: sorted.length - shown.length });
  }
  return rows;
}
