import { SiteInput } from './site.model';

/** A valid site, as the API returns it. */
export function sampleSite(overrides: Partial<SiteInput> = {}): SiteInput {
  return {
    name: 'Heretto Help Center',
    start_url: 'https://help.heretto.com/',
    description: '',
    purpose: 'own',
    help_centers: [
      {
        id: 'hc-de',
        name: 'Deutsch',
        url: 'https://help.heretto.com/de/',
        language: 'de',
        is_primary: false,
      },
      {
        id: 'hc-en',
        name: 'US English',
        url: 'https://help.heretto.com/',
        language: 'en',
        is_primary: true,
      },
    ],
    crawl: {
      sitemap_url: '',
      section_grouping: 'path',
      include: ['/docs/**'],
      exclude: [],
      max_pages: 2000,
      max_depth: 8,
      delay_ms: 250,
      concurrency: 4,
      respect_robots: true,
      follow_links: true,
      render_js: false,
      source: 'crawl',
    },
    analyses: ['readability', 'links', 'seo', 'content_integrity', 'summary'],
    integrity_categories: ['C', 'U', 'T'],
    claim_matching: 'auto',
    focus: '',
    agent_assignments: { seo: 'agent-seo' },
    schedule: { frequency: 'manual', day: 1, time: '07:00', timezone: 'UTC' },
    prospect: {
      company: 'Lumen',
      prepared_for: '',
      sender_name: '',
      sender_title: '',
      sender_email: '',
    },
    ...overrides,
  };
}
