import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';
import { SitesService } from '../../sites/sites.service';
import { sampleSite } from '../../sites/testing';
import { RunsService } from '../runs.service';
import { sampleDashboard, samplePage, sampleRun } from '../testing';
import { DashboardPage } from './dashboard-page';

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
      control: vi.fn(() => of(dashboard.run)),
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
      resolved: [],
      confirmed: false,
    };
    let { page, el } = render(pending);
    let kpi = page.kpis().find((k) => k.label === 'Confirmed integrity issues')!;
    expect(kpi.value).toBe('—');
    expect(kpi.delta).toBe('27 candidates to triage');
    expect(el.textContent).toContain('nothing counts until you confirm the triage');

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
    expect(el.textContent).toContain('1 resolved since the previous audit');
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
    expect(runs.control).toHaveBeenCalledWith('r1', 'analyze');
    expect(navigate).toHaveBeenCalledWith(['/audits', 'r1', 'progress']);
  });

  it('sends active runs to their progress view', () => {
    const { navigate } = render(sampleDashboard({ run: sampleRun({ status: 'running' }) }));
    expect(navigate).toHaveBeenCalledWith(['/audits', 'r1', 'progress'], { replaceUrl: true });
  });

  it('exports the pages as CSV', () => {
    URL.createObjectURL = vi.fn(() => 'blob:x');
    URL.revokeObjectURL = vi.fn();
    const { page, runs } = render();
    page.exportCsv();
    expect(runs.pagesCsv).toHaveBeenCalledWith('r1');
    expect(URL.createObjectURL).toHaveBeenCalled();
  });
});
