import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { HopAgentService } from '@heretto/hop-ui';
import { of, throwError } from 'rxjs';
import { SitesService } from '../../sites/sites.service';
import { sampleSite } from '../../sites/testing';
import { RunsService } from '../runs.service';
import { samplePreview, sampleRun } from '../testing';
import { listedPages, RunAudit } from './run-audit';

describe('RunAudit', () => {
  function render(preview = samplePreview()) {
    const site = {
      ...sampleSite({
        agent_assignments: {
          readability: 'a1',
          seo: 'a2',
          content_integrity: 'a3',
          summary: 'a1',
        },
      }),
      id: 's1',
    };
    const runs = {
      preview: vi.fn(() => of(preview)),
      forSite: vi.fn(() => of([sampleRun({ status: 'completed' })])),
      start: vi.fn(() => of(sampleRun({ id: 'new-run' }))),
    };
    TestBed.configureTestingModule({
      imports: [RunAudit],
      providers: [
        provideRouter([]),
        { provide: RunsService, useValue: runs },
        { provide: SitesService, useValue: { get: () => of(site) } },
        {
          provide: HopAgentService,
          useValue: {
            listAgents: () =>
              of([
                { id: 'a1', name: 'Readability Reviewer' },
                { id: 'a3', name: 'Content Integrity Reviewer' },
              ]),
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(RunAudit);
    fixture.componentRef.setInput('id', 's1');
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

  it('reads lines of pages', () => {
    expect(listedPages(' /a \n\n/b\n/a')).toEqual(['/a', '/b']);
  });

  it("starts with the whole site and the site's analyses", () => {
    const { page, el } = render();
    expect(page.mode()).toBe('site');
    expect(page.pageCount()).toBe(1284);
    expect([...page.analyses()]).toEqual([
      'readability',
      'links',
      'seo',
      'content_integrity',
      'summary',
    ]);
    expect([...page.helpCenters()]).toEqual(['hc-en', 'hc-de']); // the blocked one is left out
    expect(page.reuse).toBe(true);
    expect(page.agentCount()).toBe(3);
    expect(el.textContent).toContain('Run audit: Heretto Help Center');
    expect(el.textContent).toMatch(/Readability\s*· Readability Reviewer/);
    expect(el.textContent).toMatch(/Links\s*· checked by HOP Audit/);
    expect(el.textContent).toContain('blocked: help.x.com refused (HTTP 403)');
  });

  it('counts pages and estimates as the scope changes', () => {
    const { page } = render();
    page.mode.set('sections');
    expect(page.pageCount()).toBe(0);
    expect(page.scopeText()).toBe('No sections chosen');
    expect(page.canStart()).toBe(false);
    page.toggle(page.sections, '/api');
    page.toggle(page.sections, '/authoring');
    expect(page.pageCount()).toBe(608);
    expect(page.scopeText()).toBe('2 of 3 sections');
    expect(page.duration()).toBe('about 20 min'); // 608 × 2 s
    expect(page.tokenText()).toBe('851k'); // 608 × 1,400, links excluded from the token share
    page.selectAll(false);
    expect(page.sections().size).toBe(0);

    page.mode.set('changed');
    expect(page.pageCount()).toBe(61);
    page.mode.set('pages');
    page.pagesText.set('/a\n/b\n');
    expect(page.pageCount()).toBe(2);
  });

  it('needs a help center for content integrity', () => {
    const { page } = render();
    page.helpCenters.set(new Set());
    expect(page.canStart()).toBe(false);
    page.toggle(page.analyses, 'content_integrity');
    expect(page.canStart()).toBe(true);
  });

  it('starts the run and opens it', () => {
    const { page, runs, navigate } = render();
    page.mode.set('sections');
    page.toggle(page.sections, '/api');
    page.toggle(page.analyses, 'seo');
    page.focus = '  renamed workspaces  ';
    page.forceReevaluate = true;
    page.start();
    expect(runs.start).toHaveBeenCalledWith('s1', {
      scope: { mode: 'sections', sections: ['/api'], pages: [] },
      analyses: ['readability', 'links', 'content_integrity', 'summary'],
      help_center_ids: ['hc-en', 'hc-de'],
      reuse_crawl: true,
      recheck_external: false,
      force_reevaluate: true,
      focus: 'renamed workspaces',
    });
    expect(navigate).toHaveBeenCalledWith(['/audits', 'new-run']);
  });

  it('shows why a run could not start', () => {
    const { page, runs } = render();
    runs.start.mockReturnValue(
      throwError(() => ({ error: { detail: 'Audit #15 of this site is still running' } })),
    );
    page.start();
    expect(page.errors()).toEqual(['Audit #15 of this site is still running']);
    expect(page.starting()).toBe(false);
  });

  it('turns reuse off when there is no earlier audit', () => {
    const { page, el } = render(samplePreview({ last_run_number: null, last_run_at: null }));
    expect(page.reuse).toBe(false);
    page.mode.set('changed');
    TestBed.tick();
    expect(el.textContent).toContain('No completed audit yet');
  });
});
