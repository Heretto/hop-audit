import {
  ClaimsView,
  Dashboard,
  Finding,
  IntegrityRow,
  IntegrityView,
  PageDetail,
  PageRow,
  Preview,
  ReportView,
  RunDetail,
  RunListItem,
} from './run.model';

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
    metrics: {},
    help_center_ids: ['hc-en', 'hc-de'],
    reuse_crawl: true,
    recheck_external: false,
    force_reevaluate: false,
    focus: '',
    tokens: {},
    agent_stats: {},
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

export function samplePage(overrides: Partial<PageRow> = {}): PageRow {
  return {
    id: 'p1',
    url: 'https://help.heretto.com/authoring/reuse/conrefs',
    path: '/authoring/reuse/conrefs',
    title: 'Reuse content with conrefs',
    section: '/authoring',
    help_center_id: 'hc-en',
    http_status: 200,
    error: null,
    word_count: 1842,
    flesch: 44.2,
    broken_links: 2,
    redirects: 1,
    anchor_issues: 1,
    seo_issues: 3,
    score: 61,
    findings: 0,
    focus_findings: 0,
    ...overrides,
  };
}

export function sampleDashboard(overrides: Partial<Dashboard> = {}): Dashboard {
  return {
    run: sampleRun({
      status: 'completed',
      finished_at: '2026-10-22T09:56:00Z',
      progress: 100,
      metrics: {
        score: 82,
        pages: 1284,
        new_pages: 6,
        flesch: 58.4,
        broken: 37,
        seo_issues: 112,
        compared_with: 14,
      },
    }),
    compared: sampleRun({
      id: 'r0',
      number: 14,
      status: 'completed',
      metrics: { score: 79, pages: 1278, flesch: 57.2, broken: 51, seo_issues: 103 },
    }),
    sections: [
      { path: '/api', pages: 2, flesch: 48.9, broken: 3, seo_issues: 4, score: 71 },
      { path: '/authoring', pages: 3, flesch: 55.7, broken: 2, seo_issues: 4, score: 79 },
    ],
    analyzed: true,
    ...overrides,
  };
}

export function samplePageDetail(overrides: Partial<PageDetail> = {}): PageDetail {
  return {
    ...samplePage(),
    run_id: 'r1',
    run_number: 15,
    site_id: 's1',
    site_name: 'Heretto Help Center',
    help_center_name: 'US English',
    language: 'en',
    lastmod: '2026-09-30T00:00:00Z',
    fetched_at: '2026-10-22T09:16:00Z',
    reused_from_id: null,
    content_hash: '3f2a9c1e7b4d5a6f8e0c2b1d9a7f6e5c4b3a2918f7e6d5c4b3a2918f7e6d5c19',
    grade: 12.8,
    words_per_sentence: 25.9,
    passive_pct: 18,
    sentences: 71,
    seo: [
      { key: 'title', label: 'Title', status: 'warn', detail: '71 chars (aim for 30–60)' },
      { key: 'description', label: 'Meta description', status: 'error', detail: 'Missing' },
      { key: 'h1', label: 'H1', status: 'ok', detail: '1' },
    ],
    links_internal: 3,
    links_external: 1,
    content: {
      title: 'Reuse content with conrefs | Authoring | Heretto Help Center',
      description: null,
      canonical: null,
      robots: '',
      lang: 'en',
      og: {},
      headings: [
        [1, 'Reuse content with conrefs'],
        [2, 'Push conrefs'],
        [4, 'Limits'],
      ],
      images: [],
      breadcrumb: [],
      text: 'Reuse content with conrefs\nA conref pulls content in.',
    },
    links: [
      {
        url: 'https://help.heretto.com/a',
        text: 'ok link',
        internal: true,
        outcome: 'ok',
        status: 200,
        final_url: null,
        note: '',
        fix: '',
        suggestion: '',
      },
      {
        url: 'https://help.heretto.com/authoring/reuse/conref-push',
        text: 'conref push',
        internal: true,
        outcome: 'broken',
        status: 404,
        final_url: null,
        note: 'HTTP 404',
        fix: 'relink',
        suggestion: 'Relink to /authoring/reuse/conref-push-and-pull.',
      },
      {
        url: 'https://help.heretto.com/publishing/presets#filters',
        text: 'filters',
        internal: true,
        outcome: 'anchor',
        status: 200,
        final_url: null,
        note: '#filters not found on the target page',
        fix: 'anchor',
        suggestion: 'Link to #filters-and-presets.',
      },
      {
        url: 'https://docs.oasis-open.org/dita',
        text: 'DITA spec',
        internal: false,
        outcome: 'broken',
        status: 410,
        final_url: null,
        note: 'HTTP 410',
        fix: 'remove',
        suggestion: 'The external page is gone: link to its replacement, or remove the link.',
      },
    ],
    section_flesch: 55.7,
    previous_score: 64,
    previous_run_number: 14,
    agent_findings: [],
    integrity_findings: [],
    ...overrides,
  };
}

export function listItem(overrides: Partial<RunListItem>): RunListItem {
  return sampleRun({ status: 'completed', progress: 100, ...overrides });
}

export function sampleFinding(overrides: Partial<Finding> = {}): Finding {
  return {
    id: 'f1',
    analysis: 'readability',
    agent_id: 'a1',
    agent_name: 'Readability Reviewer',
    model: 'claude-sonnet-4-5',
    severity: 'High',
    title: 'Three sentences over 45 words',
    body: 'Split each into the action, then a note.',
    quote: 'If the target element is inside a map that has been branched…',
    suggestion: 'Push the conref. If the branch is locked, the push is rejected.',
    on_focus: false,
    target: null,
    page_count: 1,
    dismissed: false,
    dismissed_reason: '',
    ...overrides,
  };
}

export function sampleIntegrity(overrides: Partial<IntegrityRow> = {}): IntegrityRow {
  return {
    id: 'c1',
    code: 'C-01',
    category: 'C',
    severity: 'High',
    locale: 'US English',
    help_center_ids: ['hc-en'],
    title: 'Credit reporting: "may lower your score" vs. "not reported"',
    quotes: [
      {
        label: 'A',
        text: 'Late payments may lower your score.',
        slug: 'late-payments',
        note: '',
        page_id: 'p1',
        verified: true,
        url: 'https://help.lumen.com/late-payments',
      },
      {
        label: 'B',
        text: 'Loans are not reported at this time.',
        slug: 'credit-faq',
        note: '',
        page_id: 'p2',
        verified: true,
      },
    ],
    why: 'A customer reads opposite answers.',
    proposed_tier: 'firm',
    proposed_reason: '',
    tier: 'firm',
    triage_note: '',
    example_rank: null,
    first_seen: 15,
    carried_from: null,
    agent_name: 'Content Integrity Reviewer',
    ...overrides,
  };
}

export function sampleIntegrityView(overrides: Partial<IntegrityView> = {}): IntegrityView {
  return {
    run: sampleRun({ status: 'completed', progress: 100 }),
    purpose: 'prospect',
    triage: { status: 'pending' },
    findings: [
      sampleIntegrity(),
      sampleIntegrity({
        id: 't3',
        code: 'T-03',
        category: 'T',
        title: 'French reverses AutoPay',
        locale: 'Français vs. US English',
      }),
      sampleIntegrity({
        id: 'o4',
        code: 'O-04',
        category: 'O',
        severity: 'Medium',
        title: 'Future tense for a shipped feature',
      }),
      sampleIntegrity({
        id: 'd1',
        code: 'D-01',
        category: 'D',
        severity: 'Medium',
        tier: 'review',
        proposed_tier: 'review',
        triage_note: 'Likely rounding.',
        title: 'APR stated two ways',
      }),
      sampleIntegrity({
        id: 'o6',
        code: 'O-06',
        category: 'O',
        severity: 'Low',
        tier: 'drop',
        proposed_tier: 'drop',
        title: 'Promotion ended two days ago',
      }),
    ],
    help_centers: [
      {
        id: 'hc-en',
        name: 'US English',
        language: 'en',
        is_primary: true,
        articles: 142,
        pages: 142,
      },
      {
        id: 'hc-fr',
        name: 'Français',
        language: 'fr',
        is_primary: false,
        articles: 91,
        pages: 103,
      },
    ],
    resolved: [],
    ...overrides,
  };
}

export function sampleClaimsView(overrides: Partial<ClaimsView> = {}): ClaimsView {
  const claim = (
    page: string,
    slug: string,
    statement: string,
    group: number | null,
    hc = 'hc-en',
  ) => ({
    page_id: page,
    url: `https://help.x.com/${slug}`,
    slug,
    title: slug.split('/').pop()!,
    help_center_id: hc,
    subject: group === 2 ? 'refund window' : 'late payment fee',
    statement,
    group,
  });
  return {
    run: sampleRun({ status: 'completed' }),
    method: 'embeddings (OpenAI · Team key)',
    help_centers: [
      { id: 'hc-en', name: 'US English' },
      { id: 'hc-fr', name: 'Français' },
    ],
    claims: [
      claim('p1', 'billing/fees', 'The late fee is $10.', 1),
      claim('p2', 'billing/faq', 'The late fee is $15.', 1),
      claim('p1', 'billing/fees', 'Refunds within 30 days.', 2),
      claim('p3', 'billing/refunds', 'Refunds within 30 days.', 2),
      claim('p4', 'fr/billing/fees', 'Les frais sont de 10 $.', null, 'hc-fr'),
    ],
    groups: [
      {
        number: 1,
        subject: 'late payment fee',
        status: 'compared',
        issues: 1,
        claims: 2,
        articles: 2,
      },
      { number: 2, subject: 'refund window', status: 'agree', issues: 0, claims: 2, articles: 2 },
    ],
    ...overrides,
  };
}

export function sampleReport(overrides: Partial<ReportView> = {}): ReportView {
  const sev = (s: string) => [{ kind: 'sev' as const, text: s }];
  const text = (t: string) => [{ kind: 'text' as const, text: t }];
  return {
    run: sampleRun({ status: 'completed' }),
    purpose: 'prospect',
    ready: true,
    reason: '',
    title: 'Lumen Financial — Content Integrity Review',
    subject: 'Lumen Financial',
    as_of: '2026-10-08T07:00:00Z',
    author: 'Patrick Bosek',
    sections: [
      {
        id: 'categories',
        title: 'Findings by category',
        lead: 'Contradictions between articles (19) and … account for 36 of the 63 issues.',
        tables: [
          {
            columns: [
              { label: 'Category', num: false },
              { label: 'Total', num: true },
            ],
            rows: [[text('Contradictions between articles'), text('19')]],
            heading: '',
            total: [text('Total'), text('63')],
            more: '',
          },
        ],
        after: 'High: a customer could act on wrong information.',
      },
      {
        id: 'contradictions',
        title: 'Contradictions between articles (19)',
        lead: '19 findings where two articles give a customer different answers.',
        tables: [
          {
            columns: ['ID', 'Severity', 'Help center', 'Issue', 'Conflicting text (article)'].map(
              (label) => ({ label, num: false }),
            ),
            rows: [
              [
                [{ kind: 'code', text: 'C-01' }],
                sev('High'),
                text('US'),
                text('Credit reporting stated both ways'),
                [
                  { kind: 'quote', text: 'Late payments may lower your credit score.' },
                  { kind: 'slug', text: 'how-late-payments-affect-credit' },
                  { kind: 'br', text: '' },
                  { kind: 'quote', text: 'Loans are not reported.' },
                  { kind: 'note', text: 'translated' },
                  { kind: 'slug', text: 'credit-reporting-faq' },
                ],
              ],
            ],
            heading: '',
            total: null,
            more: '',
          },
        ],
        after: '',
      },
    ],
    appendix: [{ label: 'Broken links', value: '11', detail: '9 internal · 2 external' }],
    counts: { firm: 63, high: 9, review: 9, articles: 329, help_centers: 3 },
    ...overrides,
  };
}
