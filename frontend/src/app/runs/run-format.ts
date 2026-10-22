import { RunScope, RunStatus, RunSummary } from './run.model';

/** "Whole site", "/authoring, /api", "Changed pages", "3 listed pages". */
export function scopeLabel(scope: RunScope): string {
  switch (scope.mode) {
    case 'sections':
      return scope.sections.length > 3
        ? `${scope.sections.length} sections`
        : scope.sections.join(', ') || 'No sections';
    case 'changed':
      return 'Changed pages';
    case 'pages':
      return `${scope.pages.length} listed page${scope.pages.length === 1 ? '' : 's'}`;
    default:
      return 'Whole site';
  }
}

/** "42 min", "1 h 5 min", "35 s"; elapsed so far for a run still going. */
export function duration(
  run: Pick<RunSummary, 'started_at' | 'finished_at'>,
  now = Date.now(),
): string {
  if (!run.started_at) return '—';
  const end = run.finished_at ? Date.parse(run.finished_at) : now;
  return formatSeconds((end - Date.parse(run.started_at)) / 1000);
}

export function formatSeconds(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const minutes = Math.round(s / 60);
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  return minutes % 60 ? `${h} h ${minutes % 60} min` : `${h} h`;
}

/** "about 6 min", "about 1.5 h". */
export function estimate(seconds: number): string {
  const minutes = Math.max(1, Math.round(seconds / 60));
  return minutes < 60 ? `about ${minutes} min` : `about ${(minutes / 60).toFixed(1)} h`;
}

/** "1.80M", "84k", "900". */
export function tokens(n: number): string {
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `${Math.round(n / 1e3)}k`;
  return `${Math.round(n)}`;
}

export interface Chip {
  cls: string;
  label: string;
}

/** The hop-ui status chip for a run, or for a site never audited. */
export function statusChip(run: Pick<RunSummary, 'status' | 'progress'> | null): Chip {
  const chips: Record<RunStatus, Chip> = {
    queued: { cls: 'hop-status-chip-pending', label: 'Queued' },
    running: { cls: 'hop-status-chip-running', label: `Running · ${run?.progress ?? 0}%` },
    paused: { cls: 'hop-status-chip-pending', label: 'Paused' },
    completed: { cls: 'hop-status-chip-completed', label: 'Completed' },
    failed: { cls: 'hop-status-chip-failed', label: 'Failed' },
    cancelled: { cls: '', label: 'Cancelled' },
  };
  return run ? chips[run.status] : { cls: '', label: 'Not audited' };
}
