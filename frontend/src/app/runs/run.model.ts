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
  metrics: Partial<RunMetrics>;
  progress: number;
}

/** A run's headline numbers (backend scoring.run_metrics); empty until analyzed. */
export interface RunMetrics {
  score: number | null;
  pages: number;
  pages_failed: number;
  new_pages: number | null;
  flesch: number | null;
  under_50: number;
  broken: number;
  redirects: number;
  anchors: number;
  blocked_links: number;
  links: number;
  seo_issues: number;
  compared_with: number | null;
  analyzed_at: string;
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

export interface SectionRow {
  path: string;
  pages: number;
  flesch: number | null;
  broken: number;
  seo_issues: number;
  score: number | null;
}

export interface Dashboard {
  run: RunDetail;
  compared: RunSummary | null;
  sections: SectionRow[];
  analyzed: boolean;
}

export interface PageRow {
  id: string;
  url: string;
  path: string;
  title: string;
  section: string;
  help_center_id: string;
  http_status: number | null;
  error: string | null;
  word_count: number;
  flesch: number | null;
  broken_links: number | null;
  redirects: number | null;
  anchor_issues: number | null;
  seo_issues: number | null;
  score: number | null;
}

export interface SeoCheck {
  key: string;
  label: string;
  status: 'ok' | 'warn' | 'error';
  detail: string;
}

export interface LinkRow {
  url: string;
  text: string;
  internal: boolean;
  outcome: 'ok' | 'redirect' | 'broken' | 'blocked' | 'anchor';
  status: number | null;
  final_url: string | null;
  note: string;
}

export interface PageContent {
  title: string;
  description: string | null;
  canonical: string | null;
  robots: string;
  lang: string;
  og: Record<string, string>;
  headings: [number, string][];
  images: { src: string; alt: string | null }[];
  breadcrumb: string[];
  text: string;
  final_url?: string | null;
  [key: string]: unknown;
}

export interface PageDetail extends PageRow {
  run_id: string;
  run_number: number;
  site_id: string;
  site_name: string;
  help_center_name: string;
  language: string;
  lastmod: string | null;
  fetched_at: string | null;
  reused_from_id: string | null;
  grade: number | null;
  words_per_sentence: number | null;
  passive_pct: number | null;
  sentences: number | null;
  seo: SeoCheck[] | null;
  links_internal: number | null;
  links_external: number | null;
  content: PageContent;
  links: LinkRow[];
  section_flesch: number | null;
  previous_score: number | null;
  previous_run_number: number | null;
}

export interface CompareRow {
  key: string;
  label: string;
  a: number | null;
  b: number | null;
  delta: number | null;
  better: 'up' | 'down' | 'flat';
}

export interface Comparison {
  a: RunSummary;
  b: RunSummary;
  rows: CompareRow[];
  changed_pages: {
    url: string;
    path: string;
    page_id: string;
    a: number;
    b: number;
    delta: number;
  }[];
}
