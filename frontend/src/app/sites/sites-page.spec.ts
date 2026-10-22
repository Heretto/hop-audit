import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { provideRouter } from '@angular/router';
import { HopAgentService } from '@heretto/hop-ui';
import { of } from 'rxjs';
import { SiteSummary } from './site.model';
import { siteDetails, SitesPage } from './sites-page';
import { SitesService } from './sites.service';
import { sampleRun } from '../runs/testing';
import { sampleSite } from './testing';

const summary = (id: string, name: string, extra: Partial<SiteSummary> = {}): SiteSummary => {
  const s = sampleSite();
  return {
    id,
    name,
    start_url: s.start_url,
    purpose: 'own',
    help_centers: s.help_centers,
    crawl: s.crawl,
    ...extra,
  };
};

describe('siteDetails', () => {
  it('summarizes hosts, languages, sitemap and purpose', () => {
    const s = summary('1', 'A', {
      purpose: 'prospect',
      crawl: { ...sampleSite().crawl, sitemap_url: 'https://help.heretto.com/sitemap.xml' },
    });
    expect(siteDetails(s)).toBe('help.heretto.com · de, en · sitemap.xml · prospect review');
  });
});

describe('SitesPage', () => {
  function render(rows: SiteSummary[], confirm = true) {
    const sites = { list: vi.fn(() => of(rows)), delete: vi.fn(() => of(undefined)) };
    const agents = {
      listAgents: vi.fn(() => of([{ is_active: true }, { is_active: false }, { is_active: true }])),
    };
    TestBed.configureTestingModule({
      imports: [SitesPage],
      providers: [
        provideRouter([]),
        { provide: SitesService, useValue: sites },
        { provide: HopAgentService, useValue: agents },
        { provide: MatDialog, useValue: { open: () => ({ afterClosed: () => of(confirm) }) } },
      ],
    });
    const fixture = TestBed.createComponent(SitesPage);
    fixture.detectChanges();
    return { fixture, sites, el: fixture.nativeElement as HTMLElement };
  }

  it('lists sites with their details and counts active agents', () => {
    const { el } = render([summary('1', 'Heretto Help Center'), summary('2', 'Developer Portal')]);
    expect(el.textContent).toContain('Heretto Help Center');
    expect(el.textContent).toContain('help.heretto.com · de, en');
    expect(el.textContent).toContain('Not audited');
    expect(el.querySelector('a[href="/sites/1/edit"]')).not.toBeNull();
    expect(el.textContent).toMatch(/2\s*Analysis agents configured/);
  });

  it("shows each site's latest run, with progress for a running one", () => {
    const { el } = render([
      summary('1', 'Running site', { last_run: sampleRun({ status: 'running', progress: 61 }) }),
      summary('2', 'Done site', {
        last_run: sampleRun({
          id: 'r2',
          status: 'completed',
          progress: 100,
          finished_at: new Date().toISOString(),
          started_at: new Date(Date.now() - 42 * 60_000).toISOString(),
        }),
      }),
    ]);
    expect(el.textContent).toContain('Running · 61%');
    expect(el.querySelector('a[href="/audits/r1"][aria-label="View progress"]')).not.toBeNull();
    expect(el.querySelector('a[href="/sites/2/run"]')).not.toBeNull();
    expect(el.textContent).toContain('#15 · /authoring, /api');
    expect(el.textContent).toContain('Audit #15 of Done site completed 42 min after it started.');
    expect(el.textContent).toMatch(/744\s*Pages under audit/);
  });

  it('shows the score and broken links from the last completed audit', () => {
    const { el } = render([
      summary('1', 'Scored site', {
        last_run: sampleRun({ status: 'running', progress: 10 }),
        last_completed: sampleRun({
          id: 'r0',
          status: 'completed',
          metrics: { score: 82, broken: 37 },
        }),
      }),
    ]);
    expect(el.querySelector('.score-chip.good')?.textContent?.trim()).toBe('82');
    expect(el.textContent).toContain('37');
    expect(el.querySelector('a.site-name')?.getAttribute('href')).toBe('/sites/1');
  });

  it('shows the empty state', () => {
    const { el } = render([]);
    expect(el.textContent).toContain('No sites yet');
    expect(el.querySelector('a[href="/sites/new"]')).not.toBeNull();
  });

  it('deletes after confirmation', () => {
    const { fixture, sites } = render([summary('1', 'A'), summary('2', 'B')]);
    fixture.componentInstance.confirmDelete(summary('1', 'A'));
    expect(sites.delete).toHaveBeenCalledWith('1');
    expect(fixture.componentInstance.rows()!.map((s) => s.id)).toEqual(['2']);
  });

  it('keeps the site when the dialog is cancelled', () => {
    const { fixture, sites } = render([summary('1', 'A')], false);
    fixture.componentInstance.confirmDelete(summary('1', 'A'));
    expect(sites.delete).not.toHaveBeenCalled();
    expect(fixture.componentInstance.rows()!.length).toBe(1);
  });
});
