import { samplePage } from '../testing';
import { buildTree, matches, PAGE_LIMIT, sortPages, TreeState } from './tree';

const sections = [
  { path: '/api', pages: 2, flesch: 50, broken: 1, seo_issues: 1, score: 70 },
  { path: '/authoring', pages: 2, flesch: 60, broken: 0, seo_issues: 0, score: 90 },
];
const pages = [
  samplePage({
    id: 'a1',
    section: '/api',
    path: '/api/b',
    title: 'Beta',
    score: 50,
    broken_links: 1,
    seo_issues: 0,
  }),
  samplePage({
    id: 'a2',
    section: '/api',
    path: '/api/a',
    title: 'Alpha',
    score: 90,
    broken_links: 0,
    seo_issues: 4,
  }),
  samplePage({
    id: 't1',
    section: '/authoring',
    path: '/authoring/x',
    title: 'Topic',
    flesch: 70,
    broken_links: 0,
    seo_issues: 0,
  }),
  samplePage({
    id: 't2',
    section: '/authoring',
    path: '/authoring/y',
    http_status: 404,
    error: 'HTTP 404',
    flesch: null,
    broken_links: null,
  }),
];
const state = (over: Partial<TreeState> = {}): TreeState => ({
  query: '',
  show: 'all',
  sort: 'path',
  open: new Set(),
  closed: new Set(),
  expanded: new Set(),
  ...over,
});
const kinds = (rows: ReturnType<typeof buildTree>) =>
  rows.map((r) =>
    r.kind === 'section' ? r.section.path : r.kind === 'page' ? r.page.id : `more:${r.hidden}`,
  );

describe('page tree', () => {
  it('lists sections closed, and pages under the open ones', () => {
    expect(kinds(buildTree(sections, pages, state()))).toEqual(['/api', '/authoring']);
    expect(kinds(buildTree(sections, pages, state({ open: new Set(['/api']) })))).toEqual([
      '/api',
      'a2',
      'a1',
      '/authoring',
    ]);
  });

  it('filters by text and issue, opening matching sections unless closed', () => {
    expect(kinds(buildTree(sections, pages, state({ query: 'topic' })))).toEqual([
      '/authoring',
      't1',
    ]);
    expect(kinds(buildTree(sections, pages, state({ show: 'broken' })))).toEqual(['/api', 'a1']);
    expect(
      kinds(buildTree(sections, pages, state({ show: 'failed', closed: new Set(['/authoring']) }))),
    ).toEqual(['/authoring']);
    expect(matches(pages[1], '', 'seo')).toBe(true);
    expect(matches(pages[0], '', 'flesch50')).toBe(true);
  });

  it('sorts by score or issues', () => {
    expect(sortPages(pages.slice(0, 2), 'score').map((p) => p.id)).toEqual(['a1', 'a2']);
    expect(sortPages(pages.slice(0, 2), 'issues').map((p) => p.id)).toEqual(['a2', 'a1']);
  });

  it('shows the first pages of a large section, then all on request', () => {
    const many = Array.from({ length: PAGE_LIMIT + 5 }, (_, i) =>
      samplePage({ id: `p${i}`, section: '/api', path: `/api/${String(i).padStart(3, '0')}` }),
    );
    const open = new Set(['/api']);
    expect(kinds(buildTree(sections, many, state({ open }))).at(-2)).toBe('more:5');
    expect(
      buildTree(sections, many, state({ open, expanded: new Set(['/api']) })).filter(
        (r) => r.kind === 'page',
      ),
    ).toHaveLength(PAGE_LIMIT + 5);
  });
});
