import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { provideRouter } from '@angular/router';
import { HopAgentService } from '@heretto/hop-ui';
import { of } from 'rxjs';
import { SiteSummary } from './site.model';
import { siteDetails, SitesPage } from './sites-page';
import { SitesService } from './sites.service';
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
