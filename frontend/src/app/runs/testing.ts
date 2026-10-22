import { Preview, RunDetail } from './run.model';

export function sampleRun(overrides: Partial<RunDetail> = {}): RunDetail {
  return {
    id: 'r1',
    site_id: 's1',
    site_name: 'Heretto Help Center',
    number: 15,
    status: 'running',
    trigger: 'manual',
    scope: { mode: 'sections', sections: ['/authoring', '/api'], pages: [] },
    analyses: ['readability', 'links'],
    page_count: 372,
    created_by: 'patrick@heretto.com',
    created_at: '2026-10-22T09:14:00Z',
    started_at: '2026-10-22T09:14:00Z',
    finished_at: null,
    stages: [
      {
        key: 'discover',
        label: 'Discover',
        status: 'done',
        done: 608,
        total: 608,
        detail: 'sitemap.xml read',
      },
      { key: 'crawl', label: 'Crawl', status: 'running', done: 372, total: 608, detail: '' },
      {
        key: 'readability',
        label: 'Readability',
        status: 'pending',
        done: 0,
        total: 0,
        detail: '',
      },
      { key: 'links', label: 'Links', status: 'pending', done: 0, total: 0, detail: '' },
    ],
    progress: 61,
    help_center_ids: ['hc-en', 'hc-de'],
    reuse_crawl: true,
    recheck_external: false,
    focus: '',
    tokens: {},
    error: null,
    ...overrides,
  };
}

export function samplePreview(overrides: Partial<Preview> = {}): Preview {
  return {
    site_pages: 1284,
    changed: 61,
    sections: [
      { path: '/api', count: 296 },
      { path: '/authoring', count: 312 },
      { path: '/glossary', count: 14 },
    ],
    help_centers: [
      {
        id: 'hc-en',
        name: 'US English',
        language: 'en',
        is_primary: true,
        pages: 1284,
        blocked: null,
      },
      {
        id: 'hc-de',
        name: 'Deutsch',
        language: 'de',
        is_primary: false,
        pages: 1102,
        blocked: null,
      },
      {
        id: 'hc-ja',
        name: '日本語',
        language: 'ja',
        is_primary: false,
        pages: 0,
        blocked: 'help.x.com refused (HTTP 403)',
      },
    ],
    last_run_number: 14,
    last_run_at: '2026-10-21T07:42:00Z',
    seconds_per_page: 2,
    tokens_per_page: 1400,
    notes: [],
    ...overrides,
  };
}
