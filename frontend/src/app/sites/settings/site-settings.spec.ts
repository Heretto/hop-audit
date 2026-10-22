import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { HopAgentService } from '@heretto/hop-ui';
import { of, throwError } from 'rxjs';
import { Discovery, SiteInput } from '../site.model';
import { SitesService } from '../sites.service';
import { sampleSite } from '../testing';
import { SiteSettings } from './site-settings';

const found: Discovery = {
  status: 'ok',
  message: 'Sitemap found',
  sitemap_url: 'https://help.heretto.com/sitemap.xml',
  sitemap_count: 1,
  url_count: 1284,
  last_modified: '2026-10-20T00:00:00Z',
  sections: [
    { path: '/authoring', count: 312 },
    { path: '/api', count: 296 },
  ],
  alternates: [
    { language: 'en', url: 'https://help.heretto.com/' },
    { language: 'de', url: 'https://help.heretto.com/de/' },
    { language: 'ja', url: 'https://help.heretto.com/ja/' },
  ],
};

describe('SiteSettings', () => {
  function render(id?: string, defaults: Partial<SiteInput> = {}) {
    const blank = sampleSite({ name: '', start_url: '', help_centers: [], ...defaults });
    const sites = {
      defaults: vi.fn(() => of(blank)),
      get: vi.fn(() => of({ ...sampleSite(), id: 's1' })),
      detect: vi.fn(() => of(found)),
      create: vi.fn((body: SiteInput) => of({ ...body, id: 'new' })),
      update: vi.fn((sid: string, body: SiteInput) => of({ ...body, id: sid })),
    };
    TestBed.configureTestingModule({
      imports: [SiteSettings],
      providers: [
        provideRouter([]),
        { provide: SitesService, useValue: sites },
        {
          provide: HopAgentService,
          useValue: {
            listAgents: () =>
              of([
                {
                  id: 'agent-seo',
                  name: 'SEO Analyst',
                  ai_configuration: { model: 'gpt-5' },
                  is_active: true,
                },
              ]),
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(SiteSettings);
    if (id) fixture.componentRef.setInput('id', id);
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    fixture.detectChanges();
    return {
      fixture,
      page: fixture.componentInstance,
      sites,
      navigate,
      el: fixture.nativeElement as HTMLElement,
    };
  }

  it('starts a new site from the defaults with one primary help center', () => {
    const { page, sites, el } = render();
    expect(sites.defaults).toHaveBeenCalled();
    expect(page.title()).toBe('New site');
    expect(page.form()!.controls.help_centers.length).toBe(1);
    expect(sites.detect).not.toHaveBeenCalled();
    expect(el.textContent).toContain('Help centers and languages');
  });

  it('fills the primary help center from the start URL and detects the sitemap', () => {
    const { fixture, page, sites, el } = render();
    page.form()!.controls.start_url.setValue('https://help.heretto.com/');
    page.startUrlChanged();
    fixture.detectChanges();
    const primary = page.form()!.controls.help_centers.at(0).controls;
    expect(primary.url.value).toBe('https://help.heretto.com/');
    expect(primary.name.value).toBe('help.heretto.com');
    expect(primary.language.value).toBe('en');
    expect(sites.detect).toHaveBeenCalledWith('https://help.heretto.com/', '', true);
    expect(el.textContent).toContain('1,284 URLs in 2 sections');
    expect(el.textContent).toContain('/authoring');
  });

  it('adds help centers detected from hreflang', () => {
    const { page } = render();
    page.form()!.controls.start_url.setValue('https://help.heretto.com/');
    page.startUrlChanged();
    expect(page.missingAlternates().map((a) => a.language)).toEqual(['de', 'ja']);
    page.addDetected();
    const rows = page.form()!.controls.help_centers.controls.map((g) => g.getRawValue());
    expect(rows.slice(1).map((r) => [r.name, r.language])).toEqual([
      ['Deutsch', 'de'],
      ['日本語', 'ja'],
    ]);
    expect(page.missingAlternates()).toEqual([]);
  });

  it('reports a blocked site', () => {
    const { fixture, page, sites, el } = render();
    sites.detect.mockReturnValue(
      of({ ...found, status: 'blocked', message: 'help.x.com refused the request (HTTP 403)' }),
    );
    page.form()!.controls.start_url.setValue('https://help.x.com/');
    page.startUrlChanged();
    fixture.detectChanges();
    expect(el.textContent).toContain(
      'refused the request (HTTP 403). The audit will report this help center as blocked',
    );
  });

  it('lists problems instead of saving an invalid form', () => {
    const { page, sites } = render();
    page.save();
    expect(sites.create).not.toHaveBeenCalled();
    expect(page.errors()).toContain('Site: a name is required.');
    expect(page.errors()).toContain(
      'Help centers: each needs a name, an http(s) URL and a language.',
    );
  });

  it('creates a site and returns to the list', () => {
    const { page, sites, navigate } = render();
    const f = page.form()!;
    f.controls.name.setValue('Docs');
    f.controls.start_url.setValue('https://help.heretto.com/');
    page.startUrlChanged();
    page.save();
    expect(sites.create).toHaveBeenCalledOnce();
    const body = sites.create.mock.calls[0][0];
    expect(body.help_centers).toEqual([
      {
        name: 'help.heretto.com',
        url: 'https://help.heretto.com/',
        language: 'en',
        is_primary: true,
      },
    ]);
    expect(navigate).toHaveBeenCalledWith(['/sites']);
  });

  it('edits an existing site, keeping ids and the primary choice', () => {
    const { page, sites } = render('s1');
    expect(sites.get).toHaveBeenCalledWith('s1');
    expect(page.title()).toBe('Heretto Help Center');
    expect(sites.detect).toHaveBeenCalled();
    page.makePrimary(1);
    page.save();
    const [id, body] = sites.update.mock.calls[0];
    expect(id).toBe('s1');
    expect(
      body.help_centers.map((h: { id?: string; is_primary: boolean }) => [h.id, h.is_primary]),
    ).toEqual([
      ['hc-de', true],
      ['hc-en', false],
    ]);
  });

  it('shows the API validation message when saving fails', () => {
    const { page, sites, navigate } = render('s1');
    sites.update.mockReturnValue(
      throwError(() => ({
        error: { detail: [{ loc: ['body', 'name'], msg: 'Value error, is required' }] },
      })),
    );
    page.save();
    expect(page.errors()).toEqual(['name: is required']);
    expect(page.saving()).toBe(false);
    expect(navigate).not.toHaveBeenCalled();
  });

  it('labels agents with their model', () => {
    const { page } = render();
    expect(page.agentLabel({ id: 'a', name: 'SEO Analyst', ai_configuration: null } as never)).toBe(
      'SEO Analyst · no AI configuration',
    );
  });

  it('shows the next scheduled run', () => {
    const { page } = render();
    page.form()!.controls.schedule.patchValue({
      frequency: 'weekly',
      day: 1,
      time: '07:00',
      timezone: 'UTC',
    });
    expect(page.scheduleText()).toMatch(/^Tue, .* 07:00 UTC$/);
    page.form()!.controls.schedule.controls.frequency.setValue('manual');
    expect(page.scheduleText()).toBeNull();
  });
});
