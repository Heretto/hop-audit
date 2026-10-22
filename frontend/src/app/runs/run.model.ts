/** Shapes of the run API (backend/schemas/run.py). */

export type RunStatus = 'queued' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';
export type ScopeMode = 'site' | 'sections' | 'changed' | 'pages';

export interface RunScope {
  mode: ScopeMode;
  sections: string[];
  pages: string[];
}

export interface Stage {
  key: string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'skipped' | 'failed';
  done: number;
  total: number;
  detail: string;
}

export interface RunSummary {
  id: string;
  site_id: string;
  number: number;
  status: RunStatus;
  trigger: 'manual' | 'schedule';
  scope: RunScope;
  analyses: string[];
  page_count: number;
  created_by: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  stages: Stage[];
  progress: number;
}

export interface RunListItem extends RunSummary {
  site_name: string;
}

export interface RunDetail extends RunListItem {
  help_center_ids: string[];
  reuse_crawl: boolean;
  recheck_external: boolean;
  focus: string;
  tokens: Record<string, number>;
  error: string | null;
}

export interface RunInput {
  scope: RunScope;
  analyses: string[];
  help_center_ids: string[];
  reuse_crawl: boolean;
  recheck_external: boolean;
  focus: string;
}

export interface LogEntry {
  at: string;
  stage: string;
  level: 'info' | 'warn' | 'error';
  message: string;
}

export interface Preview {
  site_pages: number;
  changed: number;
  sections: { path: string; count: number }[];
  help_centers: {
    id: string;
    name: string;
    language: string;
    is_primary: boolean;
    pages: number;
    blocked: string | null;
  }[];
  last_run_number: number | null;
  last_run_at: string | null;
  seconds_per_page: number;
  tokens_per_page: number;
  notes: string[];
}

export const ACTIVE: RunStatus[] = ['queued', 'running', 'paused'];
