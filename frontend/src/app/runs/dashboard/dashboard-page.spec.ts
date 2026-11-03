import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';
import { SitesService } from '../../sites/sites.service';
import { sampleSite } from '../../sites/testing';
import { RunsService } from '../runs.service';
import { sampleDashboard, samplePage, sampleRun } from '../testing';
import { DashboardPage, categoryCards } from './dashboard-page';

describe('DashboardPage', () => {
  function render(dashboard = sampleDashboard()) {
    const runs = {
      dashboard: vi.fn(() => of(dashboard)),
      pages: vi.fn(() =>
        of([
          samplePage(),
          samplePage({
            id: 'p2',
            section: '/api',
            path: '/api/jobs',
            title: 'Publish jobs',
            help_center_id: 'hc-de',
          }),
        ]),
      ),
      analyze: vi.fn(() => of(dashboard.run)),
      pagesCsv: vi.fn(() => of(new Blob(['url\n']))),
    };
    TestBed.configureTestingModule({
      imports: [DashboardPage],
      providers: [
        provideRouter([]),
        { provide: RunsService, useValue: runs },
        { provide: SitesService, useValue: { get: () => of({ ...sampleSite(), id: 's1' }) } },
      ],
    });
    const fixture = TestBed.createComponent(DashboardPage);
    fixture.componentRef.setInput('runId', 'r1');
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    fixture.detectChanges();
    return {
      fixture,
      page: fixture.componentInstance,
      runs,
      navigate,
      el: fixture.nativeElement as HTMLElement,
    };
  }

  it('shows KPIs with changes since the compared run', () => {
    const { page, el } = render();
    const kpis = Object.fromEntries(page.kpis().map((k) => [k.label, k]));
    expect(kpis['Site score']).toMatchObject({
      value: '82',
      delta: '+3 vs #14',
      deltaClass: 'good',
    });
    expect(kpis['Pages analyzed']).toMatchObject({ value: '1,284', delta: '+6 new' });
    expect(kpis['Avg Flesch Reading Ease']).toMatchObject({ value: '58.4', delta: '+1.2 vs #14' });
    expect(kpis['Broken links']).toMatchObject({
      value: '37',
      delta: '−14 vs #14',
      deltaClass: 'good',
    });
    expect(kpis['SEO issues']).toMatchObject({ delta: '+9 vs #14', deltaClass: 'bad' });
    expect(el.textContent).toContain('compared with #14');
  });

  it('puts the largest categories on five cards, the rest sharing the last', () => {
    expect(categoryCards({ C: 2, T: 0, X: 5 }).map((c) => [c.label, c.n])).toMatchObject([
      ['Structure and publishing errors', 5],
      ['Contradictions', 2],
    ]);
    const cards = categoryCards({ C: 7, T: 6, L: 4, U: 2, O: 2, X: 1, N: 1 });
    expect(cards.map((c) => c.n)).toMatchObject([7, 6, 4, 2, 4]);
    expect(cards[4]).toMatchObject({
      code: 'O N X',
      label: 'Outdated content, links and duplicates, structure and publishing errors',
      n: 4,
    });
    // The shared card adds up its categories' severities too.
    const split = categoryCards(
      { C: 7, T: 6, L: 4, U: 2, O: 2, X: 1, N: 1 },
      { O: { High: 1, Low: 1 }, X: { Low: 1 }, N: { Medium: 1 } },
    );
    expect(split[4]).toMatchObject({ n: 4, high: 1, medium: 1, low: 2 });
  });

  it('shows integrity counts only once triage is confirmed', () => {
    const pending = sampleDashboard();
    pending.run.metrics.integrity = {
      candidates: 27,
      firm: 21,
      review: 3,
      drop: 3,
      high: 2,
      medium: 15,
      low: 4,
      by_category: { C: 7, T: 6 },
      severity_by_category: { C: { High: 2, Medium: 5 } },
      top: { code: 'C-02', title: 'German note says the opposite', severity: 'High' },
      resolved: [],
      confirmed: false,
    };
    let { page, el } = render(pending);
    // The bars are coloured by severity even before triage: no grey.
    const segments = (i: number) =>
      [...el.querySelectorAll('.cat')[i].querySelectorAll('.bar span')].map((s) => [
        s.className,
        (s as HTMLElement).style.width,
      ]);
    expect(page.categoryRows()[0]).toMatchObject({ code: 'C', n: 7, high: 2, medium: 5, low: 0 });
    expect(segments(0)).toEqual([
      ['high', `${(100 * 2) / 7}%`],
      ['medium', `${(100 * 5) / 7}%`],
    ]);
    // A category whose split wasn't recorded: one plain fill.
    expect(segments(1)).toEqual([['', `${(100 * 6) / 7}%`]]);
    expect([...el.querySelectorAll('.severity .dot')].map((d) => d.className)).toEqual([
      'dot high',
      'dot medium',
      'dot low',
    ]);
    let kpi = page.kpis().find((k) => k.label === 'Confirmed integrity issues')!;
    expect(kpi.value).toBe('—');
    expect(kpi.delta).toBe('27 candidates to triage');
    expect(el.textContent).toContain('nothing counts until you confirm the triage');
    // The cards show the reviewer's proposal, marked as such.
    expect(el.textContent).toContain('Proposed by the reviewer, before triage.');
    expect(el.querySelector('.cats.proposed')).not.toBeNull();
    expect(el.textContent).toMatch(/Contradictions\s*7/);
    expect(el.textContent).toContain('Top finding: C-02, German note says the opposite (High)');

    TestBed.resetTestingModule();
    const confirmed = sampleDashboard();
    confirmed.run.metrics.integrity = {
      ...pending.run.metrics.integrity!,
      confirmed: true,
      resolved: ['X-01'],
    };
    confirmed.compared!.metrics.integrity = {
      ...pending.run.metrics.integrity!,
      firm: 24,
      confirmed: true,
    };
    ({ page, el } = render(confirmed));
    kpi = page.kpis().find((k) => k.label === 'Confirmed integrity issues')!;
    expect(kpi).toMatchObject({ value: '21', delta: '2 High · −3 vs #14', deltaClass: 'good' });
    expect(page.categoryRows().map((r) => r.label)).toEqual([
      'Contradictions',
      'Translation defects',
    ]);
    expect(el.textContent).toContain('21 confirmed, 3 for review, 3 dropped');
    expect(el.textContent).not.toContain('Proposed by the reviewer');
    expect(el.querySelector('.cats:not(.proposed)')).not.toBeNull();
    expect(el.textContent).toContain('1 resolved since the previous audit');
  });

  it('draws the header and toolbar as the v2 mockup does', () => {
    const { el } = render();
    const texts = (selector: string) =>
      [...el.querySelectorAll(selector)].map((b) => {
        const copy = b.cloneNode(true) as Element;
        copy.querySelectorAll('mat-icon').forEach((i) => i.remove()); // the icon's ligature text
        return copy.textContent?.replace(/\s+/g, ' ').trim();
      });
    // Export left the header for the toolbar.
    expect(texts('.page-actions a, .page-actions button')).toEqual([
      'History',
      'Run log',
      'Re-evaluate everything',
      'Run audit',
    ]);
    expect(texts('.toolbar button')).toEqual(['Expand all', 'Collapse all', 'Export CSV']);
    expect(texts('.toolbar .small')).toHaveLength(3);
    // The filter is a placeholder, Show and Sort are named inside their fields.
    expect(el.querySelector<HTMLInputElement>('.toolbar .filter input')?.placeholder).toBe(
      'Filter pages by path or title',
    );
    expect(texts('.toolbar .field-name')).toEqual(['Show', 'Sort']);
    expect(el.querySelector('.toolbar mat-label')).toBeNull();
  });

  it('lists sections and opens them to their pages, with language tags', () => {
    const { fixture, page, el } = render();
    expect(el.textContent).toContain('/authoring');
    expect(el.textContent).not.toContain('Reuse content with conrefs');
    page.toggle('/api', false);
    fixture.detectChanges();
    expect(el.textContent).toContain('Publish jobs');
    expect(el.querySelector('a[href="/audits/r1/pages/p2"]')).not.toBeNull();
    expect(el.querySelector('.lang')?.textContent).toBe('de');
    page.expandAll(false);
    fixture.detectChanges();
    expect(el.textContent).not.toContain('Publish jobs');
  });

  it('filters across sections', () => {
    const { fixture, page, el } = render();
    page.update({ query: 'conrefs' });
    fixture.detectChanges();
    expect(el.textContent).toContain('Reuse content with conrefs');
    expect(page.matchCount()).toBe(1);
  });

  it('offers analysis for runs crawled before analyses existed', () => {
    const { page, runs, navigate, el } = render(sampleDashboard({ analyzed: false }));
    expect(el.textContent).toContain('Analyze now');
    page.analyze();
    expect(runs.analyze).toHaveBeenCalledWith('r1', false);
    expect(navigate).toHaveBeenCalledWith(['/audits', 'r1', 'progress']);
  });

  it('offers to analyze again when an agent review failed', () => {
    const d = sampleDashboard();
    d.run.stages = [
      ...d.run.stages,
      {
        key: 'content_integrity',
        label: 'Content integrity',
        status: 'failed',
        done: 3,
        total: 4,
        detail: '',
      },
    ];
    const { page, runs, el } = render(d);
    expect(page.failedStages()).toEqual(['Content integrity']);
    expect(el.textContent).toContain("Content integrity didn't complete");
    page.analyze();
    expect(runs.analyze).toHaveBeenCalledWith('r1', false);
  });

  it('re-evaluates everything after a confirmation', () => {
    const { page, runs } = render();
    const open = vi
      .spyOn(TestBed.inject(MatDialog), 'open')
      .mockReturnValue({ afterClosed: () => of(true) } as never);
    page.reevaluate();
    expect(open).toHaveBeenCalled();
    expect(runs.analyze).toHaveBeenCalledWith('r1', true);
  });

  it('sends active runs to their progress view', () => {
    const { navigate } = render(sampleDashboard({ run: sampleRun({ status: 'running' }) }));
    expect(navigate).toHaveBeenCalledWith(['/audits', 'r1', 'progress'], { replaceUrl: true });
  });

  it('exports the pages as CSV', () => {
    URL.createObjectURL = vi.fn(() => 'blob:x');
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {}); // jsdom can't navigate
    const { page, runs } = render();
    page.exportCsv();
    expect(runs.pagesCsv).toHaveBeenCalledWith('r1');
    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    click.mockRestore();
  });
});
