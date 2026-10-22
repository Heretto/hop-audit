import { RunSummary } from '../runs/run.model';

/** Shapes of the /sites API (backend/schemas/site.py) and the catalogs the screens show. */

export type Purpose = 'own' | 'prospect';
export type AnalysisKey = 'readability' | 'links' | 'seo' | 'content_integrity' | 'summary';
export type AssignmentKey = AnalysisKey | 'deliverables';

export interface HelpCenter {
  id?: string;
  name: string;
  url: string;
  language: string;
  is_primary: boolean;
}

export interface CrawlRules {
  sitemap_url: string;
  section_grouping: 'path' | 'sitemap' | 'breadcrumb';
  include: string[];
  exclude: string[];
  max_pages: number;
  max_depth: number;
  delay_ms: number;
  concurrency: number;
  respect_robots: boolean;
  follow_links: boolean;
  render_js: boolean;
}

export interface Schedule {
  frequency: 'manual' | 'weekly' | 'monthly';
  /** Weekly: 0 = Monday … 6 = Sunday. Monthly: day of the month, 1–28. */
  day: number;
  time: string;
  timezone: string;
}

export interface Prospect {
  company: string;
  prepared_for: string;
  sender_name: string;
  sender_title: string;
  sender_email: string;
}

export interface SiteInput {
  name: string;
  start_url: string;
  description: string;
  purpose: Purpose;
  help_centers: HelpCenter[];
  crawl: CrawlRules;
  analyses: AnalysisKey[];
  integrity_categories: string[];
  focus: string;
  agent_assignments: Partial<Record<AssignmentKey, string | null>>;
  schedule: Schedule;
  prospect: Prospect;
}

export interface Site extends SiteInput {
  id: string;
  created_at?: string;
  updated_at?: string;
}

export interface SiteSummary {
  id: string;
  name: string;
  start_url: string;
  purpose: Purpose;
  help_centers: HelpCenter[];
  crawl: CrawlRules;
  last_run?: RunSummary | null;
}

export interface Discovery {
  status: 'ok' | 'no_sitemap' | 'blocked' | 'unreachable';
  message: string;
  sitemap_url: string | null;
  sitemap_count: number;
  url_count: number;
  last_modified: string | null;
  sections: { path: string; count: number }[];
  alternates: { language: string; url: string }[];
}

/** The API's order; ANALYSES below is in the settings screen's layout order. */
export const ANALYSIS_KEYS: AnalysisKey[] = [
  'readability',
  'links',
  'seo',
  'content_integrity',
  'summary',
];

export const ANALYSES: { key: AnalysisKey; label: string; description: string }[] = [
  {
    key: 'readability',
    label: 'Readability',
    description: 'Flesch Reading Ease per page, sentence length, passive voice, jargon.',
  },
  {
    key: 'links',
    label: 'Links',
    description: "Broken links, redirects, internal vs external, anchors that don't resolve.",
  },
  {
    key: 'seo',
    label: 'SEO and metadata',
    description: 'Titles, descriptions, canonical, heading structure, image alt text.',
  },
  {
    key: 'summary',
    label: 'Summary report',
    description: 'Site-wide findings, trends against the previous audit, recommended fixes.',
  },
  {
    key: 'content_integrity',
    label: 'Content integrity',
    description:
      'Content that is wrong, conflicting, outdated, or missing its scope, with exact quotes and article slugs. ' +
      'Differences where both versions are accurate are never counted. Every finding gets an ID, a severity ' +
      "(High: a customer could act on it or it's compliance-sensitive; Medium: confusing or outdated; " +
      'Low: cosmetic) and a triage tier you confirm before anything is built.',
  },
];

export const ASSIGNMENTS: { key: AssignmentKey; label: string }[] = [
  { key: 'readability', label: 'Readability' },
  { key: 'links', label: 'Links' },
  { key: 'seo', label: 'SEO and metadata' },
  { key: 'content_integrity', label: 'Content integrity' },
  { key: 'summary', label: 'Summary report' },
  { key: 'deliverables', label: 'Prospect deliverables' },
];

export const CATEGORIES: { code: string; label: string }[] = [
  { code: 'C', label: 'Contradictions, between and within articles' },
  { code: 'U', label: "Instructions that don't match the app or each other" },
  { code: 'T', label: 'Translation defects, each language vs. primary' },
  { code: 'TM', label: 'Terminology inconsistency' },
  { code: 'D', label: 'Disclosure and legal text that conflicts' },
  { code: 'L', label: 'Retired products shown without scope' },
  { code: 'S', label: 'Scope errors: product rules stated as general' },
  { code: 'O', label: 'Outdated content and stale announcements' },
  { code: 'N', label: 'Links to the wrong locale, duplicates' },
  { code: 'X', label: 'Structure and publishing errors, internal notes published' },
];

/** Languages offered for a help center; others (from hreflang or a saved site) are added as needed. */
export const LANGUAGES = [
  'en',
  'en-US',
  'en-GB',
  'en-CA',
  'en-AU',
  'de',
  'de-CH',
  'fr',
  'fr-CA',
  'es',
  'es-MX',
  'it',
  'pt-BR',
  'pt-PT',
  'nl',
  'sv',
  'da',
  'nb',
  'fi',
  'pl',
  'cs',
  'hu',
  'ro',
  'ru',
  'uk',
  'tr',
  'el',
  'ar',
  'he',
  'hi',
  'th',
  'id',
  'vi',
  'ja',
  'ko',
  'zh-CN',
  'zh-TW',
];

/** "German", "French (Canada)": the language's name in English. */
export function languageName(tag: string): string {
  try {
    return new Intl.DisplayNames(['en'], { type: 'language' }).of(tag) ?? tag;
  } catch {
    return tag;
  }
}

/** "Deutsch", "日本語": the language's name in itself, for a help center's default name. */
export function nativeLanguageName(tag: string): string {
  try {
    const name = new Intl.DisplayNames([tag], { type: 'language' }).of(tag) ?? tag;
    return name.charAt(0).toLocaleUpperCase(tag) + name.slice(1);
  } catch {
    return tag;
  }
}
