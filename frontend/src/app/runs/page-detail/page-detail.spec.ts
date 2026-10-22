import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { RunsService } from '../runs.service';
import { sampleFinding, samplePageDetail } from '../testing';
import { PageDetailPage, readabilityBand } from './page-detail';

describe('PageDetailPage', () => {
  function render(page = samplePageDetail()) {
    TestBed.configureTestingModule({
      imports: [PageDetailPage],
      providers: [provideRouter([]), { provide: RunsService, useValue: { page: () => of(page) } }],
    });
    const fixture = TestBed.createComponent(PageDetailPage);
    fixture.componentRef.setInput('runId', 'r1');
    fixture.componentRef.setInput('pageId', 'p1');
    fixture.detectChanges();
    return { fixture, page: fixture.componentInstance, el: fixture.nativeElement as HTMLElement };
  }

  it('bands readability like the dashboard', () => {
    expect(readabilityBand(65).label).toBe('Plain');
    expect(readabilityBand(55).label).toBe('Fairly difficult');
    expect(readabilityBand(44.2)).toEqual({ label: 'Difficult', sev: 'error' });
    expect(readabilityBand(null).label).toBe('Not measured');
  });

  it('shows the page, its readability and its change since the last audit', () => {
    const { el, page } = render();
    const text = el.textContent!;
    expect(text).toContain('Reuse content with conrefs');
    expect(text).toContain('Heretto Help Center · Audit #15');
    expect(text).toContain('score 64 in #14 (−3)');
    expect(text).toContain('44.2');
    expect(text).toContain('section avg 55.7');
    expect(text).toContain('Difficult');
    expect(page.change()).toBe('−3');
  });

  it('lists problem links first, external ones in full', () => {
    const { fixture, page, el } = render();
    expect(page.links().map((l) => l.outcome)).toEqual(['broken', 'broken', 'anchor']);
    expect(page.target(page.links()[0])).toBe('/authoring/reuse/conref-push');
    expect(el.textContent).toContain('2 broken');
    page.allLinks.set(true);
    fixture.detectChanges();
    expect(page.links()).toHaveLength(4);
  });

  it('shows SEO checks and the issue count', () => {
    const { el, page } = render();
    expect(page.seoIssues()).toBe(2);
    expect(el.textContent).toContain('Missing');
    expect(el.textContent).toContain('71 chars (aim for 30–60)');
  });

  it('lists open findings worst first, dismissed ones apart, and updates in place', () => {
    const { fixture, page, el } = render(
      samplePageDetail({
        agent_findings: [
          sampleFinding({ id: 'low', severity: 'Low', title: 'Low one' }),
          sampleFinding({ id: 'gone', dismissed: true, title: 'Dismissed one' }),
          sampleFinding({ id: 'high', severity: 'High', title: 'High one' }),
          sampleFinding({ id: 'focus', severity: 'Low', on_focus: true, title: 'Focus one' }),
        ],
      }),
    );
    expect(page.findings().open.map((f) => f.id)).toEqual(['high', 'focus', 'low']);
    expect(page.findings().dismissed.map((f) => f.id)).toEqual(['gone']);
    expect(el.textContent).toContain('Agent findings · 3');
    page.replace(sampleFinding({ id: 'low', severity: 'Low', dismissed: true }));
    fixture.detectChanges();
    expect(page.findings().open).toHaveLength(2);
  });

  it('explains pages that could not be scored or read', () => {
    const { el } = render(
      samplePageDetail({ flesch: null, language: 'ja', error: 'HTTP 404', seo: null }),
    );
    expect(el.textContent).toContain('ja has no Flesch formula');
    expect(el.textContent).toContain("couldn't be read: HTTP 404");
    expect(el.textContent).toContain("SEO wasn't part of this audit");
  });
});
