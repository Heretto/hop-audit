import {
  AbstractControl,
  FormArray,
  FormControl,
  FormGroup,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { browserTimeZone } from '../schedule';
import {
  ANALYSES,
  ANALYSIS_KEYS,
  AnalysisKey,
  ASSIGNMENTS,
  AssignmentKey,
  CATEGORIES,
  CrawlRules,
  HelpCenter,
  Prospect,
  Schedule,
  SiteInput,
} from '../site.model';

export function httpUrl(control: AbstractControl<string>): ValidationErrors | null {
  const value = (control.value ?? '').trim();
  if (!value) return null;
  try {
    const url = new URL(value);
    return /^https?:$/.test(url.protocol) && url.host ? null : { httpUrl: true };
  } catch {
    return { httpUrl: true };
  }
}

const text = (value = '', required = false) =>
  new FormControl(value, { nonNullable: true, validators: required ? [Validators.required] : [] });
const url = (value = '', required = false) =>
  new FormControl(value, {
    nonNullable: true,
    validators: required ? [Validators.required, httpUrl] : [httpUrl],
  });
const int = (value: number, min: number, max: number) =>
  new FormControl(value, {
    nonNullable: true,
    validators: [Validators.required, Validators.min(min), Validators.max(max)],
  });
const flag = (value: boolean) => new FormControl(value, { nonNullable: true });

export function helpCenterGroup(hc: Partial<HelpCenter> = {}) {
  return new FormGroup({
    id: new FormControl<string | undefined>(hc.id, { nonNullable: true }),
    name: text(hc.name ?? '', true),
    url: url(hc.url ?? '', true),
    language: text(hc.language ?? 'en', true),
  });
}
export type HelpCenterGroup = ReturnType<typeof helpCenterGroup>;

/** Unique help-center URLs, ignoring a trailing slash. */
function uniqueUrls(array: AbstractControl): ValidationErrors | null {
  const urls = (array as FormArray<HelpCenterGroup>).controls
    .map((g) => g.controls.url.value.trim().replace(/\/$/, ''))
    .filter(Boolean);
  return new Set(urls).size === urls.length ? null : { duplicateUrl: true };
}

/** Content integrity needs at least one category. */
function categoriesWhenIntegrity(group: AbstractControl): ValidationErrors | null {
  const g = group as SiteForm;
  const on = g.controls.analyses.controls.content_integrity.value;
  const any = Object.values(g.controls.categories.controls).some((c) => c.value);
  return on && !any ? { noCategories: true } : null;
}

const lines = (patterns: string[]) => patterns.join('\n');
const patterns = (value: string) =>
  value
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);

export function siteForm(site: SiteInput) {
  const c: CrawlRules = site.crawl;
  const s: Schedule = site.schedule;
  const enabled = new Set(site.analyses);
  const categories = new Set(site.integrity_categories);
  // The primary help center is always the first row.
  const centers = [...site.help_centers].sort(
    (a, b) => Number(b.is_primary) - Number(a.is_primary),
  );
  return new FormGroup(
    {
      name: text(site.name, true),
      start_url: url(site.start_url, true),
      description: text(site.description),
      purpose: new FormControl(site.purpose, { nonNullable: true }),
      help_centers: new FormArray(centers.map(helpCenterGroup), {
        validators: [Validators.minLength(1), uniqueUrls],
      }),
      crawl: new FormGroup({
        sitemap_url: url(c.sitemap_url),
        section_grouping: new FormControl(c.section_grouping, { nonNullable: true }),
        include: text(lines(c.include)),
        exclude: text(lines(c.exclude)),
        max_pages: int(c.max_pages, 1, 100_000),
        max_depth: int(c.max_depth, 0, 50),
        delay_ms: int(c.delay_ms, 0, 60_000),
        concurrency: int(c.concurrency, 1, 16),
        respect_robots: flag(c.respect_robots),
        follow_links: flag(c.follow_links),
        render_js: flag(c.render_js),
        source: new FormControl<'crawl' | 'zendesk'>(c.source ?? 'crawl', { nonNullable: true }),
      }),
      analyses: new FormGroup(
        Object.fromEntries(ANALYSES.map((a) => [a.key, flag(enabled.has(a.key))])) as Record<
          AnalysisKey,
          FormControl<boolean>
        >,
      ),
      categories: new FormGroup(
        Object.fromEntries(
          CATEGORIES.map((cat) => [cat.code, flag(categories.has(cat.code))]),
        ) as Record<string, FormControl<boolean>>,
      ),
      claim_matching: text(site.claim_matching || 'auto'),
      focus: text(site.focus),
      agent_assignments: new FormGroup(
        Object.fromEntries(
          ASSIGNMENTS.map((a) => [
            a.key,
            new FormControl<string | null>(site.agent_assignments[a.key] ?? null),
          ]),
        ) as Record<AssignmentKey, FormControl<string | null>>,
      ),
      schedule: new FormGroup({
        frequency: new FormControl(s.frequency, { nonNullable: true }),
        day: new FormControl(s.day, { nonNullable: true }),
        time: new FormControl(s.time, {
          nonNullable: true,
          validators: [Validators.required, Validators.pattern(/^([01]\d|2[0-3]):[0-5]\d$/)],
        }),
        timezone: text(s.timezone || browserTimeZone()),
      }),
    },
    { validators: categoriesWhenIntegrity },
  );
}
export type SiteForm = ReturnType<typeof siteForm>;

/** The API payload; prospect details are edited on Deliverables and passed through. */
export function toSiteInput(form: SiteForm, prospect: Prospect): SiteInput {
  const v = form.getRawValue();
  return {
    name: v.name.trim(),
    start_url: v.start_url.trim(),
    description: v.description.trim(),
    purpose: v.purpose,
    help_centers: v.help_centers.map((hc, i) => ({
      ...(hc.id ? { id: hc.id } : {}),
      name: hc.name.trim(),
      url: hc.url.trim(),
      language: hc.language,
      is_primary: i === 0,
    })),
    crawl: {
      ...v.crawl,
      sitemap_url: v.crawl.sitemap_url.trim(),
      include: patterns(v.crawl.include),
      exclude: patterns(v.crawl.exclude),
    },
    analyses: ANALYSIS_KEYS.filter((k) => v.analyses[k]),
    integrity_categories: CATEGORIES.map((c) => c.code).filter((code) => v.categories[code]),
    claim_matching: v.claim_matching,
    focus: v.focus.trim(),
    agent_assignments: v.agent_assignments,
    schedule: v.schedule,
    prospect,
  };
}
