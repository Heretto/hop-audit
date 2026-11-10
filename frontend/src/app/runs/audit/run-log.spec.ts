import { TestBed } from '@angular/core/testing';
import { LogEntry, Stage } from '../run.model';
import { counts, MAX_STEPS, RunLog, sections } from './run-log';

let id = 0;
function entry(
  stage: string,
  level: LogEntry['level'],
  message: string,
  at = '09:00:00',
): LogEntry {
  return { id: ++id, at: `2026-10-22T${at}Z`, stage, level, message };
}

const STAGES: Stage[] = [
  { key: 'discover', label: 'Discover', status: 'done', done: 7, total: 7, detail: '' },
  { key: 'crawl', label: 'Crawl', status: 'running', done: 2, total: 7, detail: '' },
  { key: 'readability', label: 'Readability', status: 'pending', done: 0, total: 0, detail: '' },
];

const LOG: LogEntry[] = [
  entry('discover', 'info', 'Read sitemap.xml: 7 URLs.', '09:00:00'),
  entry('discover', 'info', 'Scope kept 7.', '09:00:05'),
  entry('crawl', 'info', 'Fetching up to 7 pages.', '09:00:06'),
  entry('crawl', 'detail', '/a: 200, 12 KB, 300 ms, 410 words.', '09:00:07'),
  entry('crawl', 'warn', '/b returned 503 once; retried.', '09:00:40'),
  entry('crawl', 'detail', '/b: 200, 9 KB, 900 ms, 120 words.', '09:01:06'),
  entry('run', 'info', 'Paused by me@x.com.', '09:01:10'),
];

function render(entries = LOG, stages = STAGES) {
  const fixture = TestBed.createComponent(RunLog);
  fixture.componentRef.setInput('entries', entries);
  fixture.componentRef.setInput('stages', stages);
  fixture.detectChanges();
  return { fixture, page: fixture.componentInstance, el: fixture.nativeElement as HTMLElement };
}

describe('RunLog', () => {
  it('groups the log by stage, in the order stages first logged', () => {
    const all = sections(LOG, STAGES);
    expect(all.map((s) => [s.key, s.label, s.status])).toEqual([
      ['discover', 'Discover', 'done'],
      ['crawl', 'Crawl', 'running'],
      ['run', 'Run', null],
    ]);
    const crawl = all[1];
    expect([crawl.main.length, crawl.steps, crawl.warnings, crawl.errors]).toEqual([2, 2, 1, 0]);
    expect(crawl.from).toBe('2026-10-22T09:00:06Z');
    expect(crawl.to).toBe('2026-10-22T09:01:06Z');
    expect(counts(crawl)).toBe('2 entries · 2 steps · 1 warning');
    expect(counts(all[2])).toBe('1 entry');
    expect(sections([entry('content_integrity', 'info', 'x')], [])[0].label).toBe(
      'content integrity',
    );
  });

  it('opens sections with problems, the running stage and the latest; collapses the rest', () => {
    const { el } = render();
    const heads = [...el.querySelectorAll('.head')];
    expect(heads.map((h) => h.getAttribute('aria-expanded'))).toEqual(['false', 'true', 'true']);
    expect(heads[1].textContent).toContain('Running');
    expect(heads[1].textContent).toContain('2 entries · 2 steps · 1 warning');
    expect(heads[1].textContent).toContain('1 min');
    expect(el.querySelector('.section.has-warn .head')).toBe(heads[1]);
  });

  it('opens and closes a section, and all of them', () => {
    const { fixture, page, el } = render();
    (el.querySelector('.head') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(el.querySelector('#log-discover')!.textContent).toContain('Read sitemap.xml');
    page.setAll(false);
    fixture.detectChanges();
    expect(el.querySelectorAll('.body').length).toBe(0);
    page.setAll(true);
    fixture.detectChanges();
    expect(el.querySelectorAll('.body').length).toBe(3);
  });

  it('shows a section’s steps on request, in order with its entries', () => {
    const { fixture, el } = render();
    const crawl = el.querySelector('#log-crawl')!;
    expect([...crawl.querySelectorAll('li')].map((li) => li.className)).toEqual(['info', 'warn']);
    const button = crawl.querySelector('.steps button') as HTMLButtonElement;
    expect(button.textContent).toContain('Show 2 steps');
    button.click();
    fixture.detectChanges();
    expect([...crawl.querySelectorAll('li')].map((li) => li.className)).toEqual([
      'info',
      'detail',
      'warn',
      'detail',
    ]);
    expect(button.textContent).toContain('Hide 2 steps');
  });

  it('caps the steps shown and keeps every entry', () => {
    const many = [
      entry('crawl', 'info', 'Start.'),
      ...Array.from({ length: MAX_STEPS + 5 }, (_, i) => entry('crawl', 'detail', `/p${i}: 200.`)),
      entry('crawl', 'error', 'Gave up on /z.'),
    ];
    const { page } = render(many);
    const crawl = page.all()[0];
    page.toggleSteps(crawl);
    const shown = page.shown(crawl);
    expect(shown.length).toBe(MAX_STEPS + 2);
    expect(shown[1].message).toBe('/p5: 200.');
    expect(shown.at(-1)!.level).toBe('error');
  });

  it('says when nothing is logged yet', () => {
    const { el } = render([]);
    expect(el.textContent).toContain('Nothing logged yet.');
  });
});
