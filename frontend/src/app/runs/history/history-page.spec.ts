import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';
import { SitesService } from '../../sites/sites.service';
import { RunsService } from '../runs.service';
import { listItem } from '../testing';
import { HistoryPage } from './history-page';

const site = { mode: 'site' as const, sections: [], pages: [] };
const runs = [
  listItem({ id: 'r3', number: 3, scope: site, metrics: { score: 82, analyzed_at: 'x' } }),
  listItem({ id: 'r2', number: 2, scope: site, metrics: { score: 79, analyzed_at: 'x' } }),
  listItem({ id: 'r1', number: 1, status: 'failed', metrics: {} }),
  listItem({
    id: 'z1',
    site_id: 's2',
    site_name: 'Developer Portal',
    number: 6,
    status: 'running',
    progress: 61,
    metrics: {},
  }),
];
const comparison = {
  a: runs[1],
  b: runs[0],
  rows: [{ key: 'score', label: 'Site score', a: 79, b: 82, delta: 3, better: 'up' as const }],
  changed_pages: [{ url: 'u', path: '/authoring/x', page_id: 'p1', a: 67, b: 86, delta: 19 }],
};

describe('HistoryPage', () => {
  function render(siteId?: string) {
    const service = { all: vi.fn(() => of(runs)), compare: vi.fn(() => of(comparison)) };
    TestBed.configureTestingModule({
      imports: [HistoryPage],
      providers: [
        provideRouter([]),
        { provide: RunsService, useValue: service },
        {
          provide: SitesService,
          useValue: { list: () => of([{ id: 's1', name: 'Heretto Help Center' }]) },
        },
      ],
    });
    const fixture = TestBed.createComponent(HistoryPage);
    if (siteId) fixture.componentRef.setInput('site', siteId);
    fixture.detectChanges();
    TestBed.tick();
    fixture.detectChanges();
    return {
      fixture,
      page: fixture.componentInstance,
      service,
      el: fixture.nativeElement as HTMLElement,
    };
  }

  it("charts one site's whole-site scores and compares its latest two runs", () => {
    const { page, service, el } = render('s1');
    expect(page.points().map((p) => p.score)).toEqual([79, 82]);
    expect(page.selected()).toEqual(['r2', 'r3']);
    expect(service.compare).toHaveBeenCalledWith('r2', 'r3');
    expect(el.textContent).toContain('Compare #2 → #3');
    expect(el.textContent).toContain('/authoring/x');
    expect(el.textContent).toContain('Score over time');
  });

  it('lists every site without a chart', () => {
    const { page, el } = render();
    expect(page.rows()).toHaveLength(4);
    expect(page.points()).toEqual([]);
    expect(el.textContent).toContain('Running · 61%');
  });

  it('only pairs analyzed runs of one site, earlier first', () => {
    const { page } = render();
    const [r3, r2, r1, z1] = runs;
    expect(page.canSelect(r1)).toBe(false); // failed
    expect(page.canSelect(z1)).toBe(false); // running
    page.selected.set([]);
    page.toggle(r3);
    page.toggle(r2);
    expect(page.selected()).toEqual(['r2', 'r3']);
    page.toggle(r3);
    expect(page.selected()).toEqual(['r2']);
  });

  it('switches site through the URL', () => {
    const { page } = render();
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    page.pickSite('s1');
    expect(navigate).toHaveBeenCalledWith(['/audits'], { queryParams: { site: 's1' } });
  });
});
