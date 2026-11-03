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
  agent_findings: number;
  focus_findings: number;
  tokens: number;
  integrity: IntegrityMetrics;
  compared_with: number | null;
  analyzed_at: string;
}

/** Content-integrity counts (backend integrity.metrics); shown only once confirmed. */
export type Severity = 'High' | 'Medium' | 'Low';

export interface IntegrityMetrics {
  candidates: number;
  firm: number;
  review: number;
  drop: number;
  high: number;
  medium: number;
  low: number;
  by_category: Record<string, number>;
  /** Each category's firm findings by severity; absent on audits analyzed before it was recorded. */
  severity_by_category?: Record<string, Partial<Record<Severity, number>>>;
  /** The most severe firm finding; absent on audits analyzed before it was recorded. */
  top?: { code: string; title: string; severity: string } | null;
  resolved: string[];
  confirmed: boolean;
}

/** One agent's work in a run (backend analysis._review). */
export interface AgentStats {
  name: string;
  model: string;
  provider: string;
  tokens: number;
  findings: number;
  errors: number;
  retries: number;
  status: 'done' | 'stopped';
}

export interface RunListItem extends RunSummary {
  site_name: string;
}

export interface RunDetail extends RunListItem {
  help_center_ids: string[];
  reuse_crawl: boolean;
  recheck_external: boolean;
  force_reevaluate: boolean;
  focus: string;
  tokens: Record<string, number>;
  agent_stats: Record<string, AgentStats>;
  error: string | null;
}

export interface RunInput {
  scope: RunScope;
  analyses: string[];
  help_center_ids: string[];
  reuse_crawl: boolean;
  recheck_external: boolean;
  force_reevaluate: boolean;
  focus: string;
  /** Content-integrity categories for this run; omitted when it doesn't run. */
  integrity_categories?: string[];
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
  findings: number;
  focus_findings: number;
}

export interface Finding {
  id: string;
  analysis: 'readability' | 'seo' | 'links';
  agent_id: string | null;
  agent_name: string;
  model: string;
  severity: 'High' | 'Medium' | 'Low';
  title: string;
  body: string;
  quote: string;
  suggestion: string;
  on_focus: boolean;
  target: string | null;
  page_count: number;
  dismissed: boolean;
  dismissed_reason: string;
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
  fix: '' | 'relink' | 'anchor' | 'restore' | 'remove';
  suggestion: string;
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
  content_hash: string | null;
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
  agent_findings: Finding[];
  integrity_findings: IntegrityRow[];
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

export type Tier = 'firm' | 'review' | 'drop';

export interface Quote {
  label: string;
  text: string;
  slug: string;
  note: string;
  page_id: string | null;
  verified: boolean;
  /** The article on the site, when its page is in this audit. */
  url?: string | null;
}

export interface IntegrityRow {
  id: string;
  code: string;
  category: string;
  severity: 'High' | 'Medium' | 'Low';
  locale: string;
  help_center_ids: string[];
  title: string;
  quotes: Quote[];
  why: string;
  proposed_tier: Tier;
  proposed_reason: string;
  tier: Tier;
  triage_note: string;
  example_rank: number | null;
  first_seen: number;
  carried_from: number | null;
  agent_name: string;
}

export interface Triage {
  status: 'pending' | 'in_progress' | 'confirmed';
  confirmed_at?: string | null;
  confirmed_by?: string;
}

export interface IntegrityView {
  run: RunDetail;
  purpose: 'own' | 'prospect';
  triage: Triage;
  findings: IntegrityRow[];
  help_centers: {
    id: string;
    name: string;
    language: string;
    is_primary: boolean;
    articles: number;
    pages: number;
  }[];
  resolved: string[];
}

/** Short category names for counts (backend catalog.INTEGRITY_CATEGORIES). */
export const CATEGORY_NAMES: Record<string, string> = {
  C: 'Contradictions',
  U: "Instructions that don't match",
  T: 'Translation defects',
  TM: 'Terminology inconsistency',
  D: 'Disclosure and legal text',
  L: 'Retired products',
  S: 'Scope errors',
  O: 'Outdated content',
  N: 'Links and duplicates',
  X: 'Structure and publishing errors',
};

/** A statement the content-integrity reviewer took from an article (verified on the page). */
export interface ClaimRow {
  page_id: string;
  url: string;
  slug: string;
  title: string;
  help_center_id: string;
  subject: string;
  statement: string;
  /** Number of the statement group it was matched into, if any. */
  group: number | null;
}

/** agree: one wording, not sent; compared: sent this run; kept: earlier verdict reused. */
export type ClaimGroupStatus = 'agree' | 'compared' | 'kept' | 'failed';

export interface ClaimGroup {
  number: number;
  subject: string;
  status: ClaimGroupStatus;
  /** Candidates the reviewer raised on this group. */
  issues: number;
  claims: number;
  articles: number;
}

export interface ClaimsView {
  run: RunDetail;
  /** How statements were matched across articles; null when that pass didn't run. */
  method: string | null;
  help_centers: { id: string; name: string }[];
  claims: ClaimRow[];
  groups: ClaimGroup[];
}
