import { ClaimGroup, ClaimGroupStatus, ClaimRow } from '../run.model';

/** What the claims list shows: matched = in a group with another article; a number = that group. */
export interface ClaimFilters {
  query: string;
  center: string;
  group: '' | 'matched' | 'single' | number;
}

export const NO_FILTERS: ClaimFilters = { query: '', center: '', group: '' };

export const GROUP_STATUS: Record<ClaimGroupStatus, { cls: string; label: string }> = {
  agree: { cls: 'hop-status-chip-completed', label: 'Same wording' },
  compared: { cls: 'hop-status-chip-running', label: 'Compared' },
  kept: { cls: 'hop-status-chip-pending', label: 'Earlier verdict' },
  failed: { cls: 'hop-status-chip-failed', label: 'Not compared' },
};

export function matchesClaim(c: ClaimRow, f: ClaimFilters): boolean {
  const q = f.query.trim().toLowerCase();
  if (q && ![c.subject, c.statement, c.slug, c.title].some((t) => t.toLowerCase().includes(q))) {
    return false;
  }
  if (f.center && c.help_center_id !== f.center) return false;
  if (f.group === 'matched') return c.group !== null;
  if (f.group === 'single') return c.group === null;
  if (typeof f.group === 'number') return c.group === f.group;
  return true;
}

/** Groups with something to look at first: issues, then failures, then size. */
export function rankGroups(groups: ClaimGroup[]): ClaimGroup[] {
  return [...groups].sort(
    (a, b) =>
      b.issues - a.issues ||
      Number(b.status === 'failed') - Number(a.status === 'failed') ||
      b.claims - a.claims ||
      a.number - b.number,
  );
}
