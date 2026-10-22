import { FormControl } from '@angular/forms';
import { sampleSite } from '../testing';
import { helpCenterGroup, httpUrl, siteForm, toSiteInput } from './site-form';

describe('site form', () => {
  it('puts the primary help center first', () => {
    const form = siteForm(sampleSite());
    expect(form.controls.help_centers.controls.map((g) => g.controls.name.value)).toEqual([
      'US English',
      'Deutsch',
    ]);
  });

  it('round-trips a site into the API payload', () => {
    const site = sampleSite();
    const form = siteForm(site);
    form.controls.crawl.controls.exclude.setValue('  /archive/**\n\n*.pdf ');
    form.controls.name.setValue('  Renamed ');
    const body = toSiteInput(form, site.prospect);
    expect(body.name).toBe('Renamed');
    expect(body.help_centers).toEqual([
      {
        id: 'hc-en',
        name: 'US English',
        url: 'https://help.heretto.com/',
        language: 'en',
        is_primary: true,
      },
      {
        id: 'hc-de',
        name: 'Deutsch',
        url: 'https://help.heretto.com/de/',
        language: 'de',
        is_primary: false,
      },
    ]);
    expect(body.crawl.include).toEqual(['/docs/**']);
    expect(body.crawl.exclude).toEqual(['/archive/**', '*.pdf']);
    expect(body.analyses).toEqual(site.analyses);
    expect(body.integrity_categories).toEqual(['C', 'U', 'T']);
    expect(body.agent_assignments).toEqual({
      readability: null,
      links: null,
      seo: 'agent-seo',
      content_integrity: null,
      summary: null,
      deliverables: null,
    });
    expect(body.prospect.company).toBe('Lumen');
  });

  it('omits ids for new help centers and orders analyses canonically', () => {
    const form = siteForm(sampleSite({ analyses: ['summary', 'links'] }));
    form.controls.help_centers.push(
      helpCenterGroup({ name: 'FR', url: 'https://a.com/fr', language: 'fr' }),
    );
    const body = toSiteInput(form, sampleSite().prospect);
    expect(body.help_centers[2]).toEqual({
      name: 'FR',
      url: 'https://a.com/fr',
      language: 'fr',
      is_primary: false,
    });
    expect(body.analyses).toEqual(['links', 'summary']);
  });

  it('validates URLs', () => {
    const check = (v: string) => httpUrl(new FormControl(v, { nonNullable: true }));
    expect(check('')).toBeNull();
    expect(check('https://a.com/x')).toBeNull();
    expect(check('a.com')).toEqual({ httpUrl: true });
    expect(check('ftp://a.com')).toEqual({ httpUrl: true });
  });

  it('rejects duplicate help-center URLs', () => {
    const form = siteForm(sampleSite());
    form.controls.help_centers.at(1).controls.url.setValue('https://help.heretto.com');
    expect(form.controls.help_centers.hasError('duplicateUrl')).toBe(true);
  });

  it('needs a category while content integrity is on', () => {
    const form = siteForm(sampleSite({ integrity_categories: [] }));
    expect(form.hasError('noCategories')).toBe(true);
    form.controls.analyses.controls.content_integrity.setValue(false);
    expect(form.hasError('noCategories')).toBe(false);
  });

  it('bounds crawl numbers', () => {
    const crawl = siteForm(sampleSite()).controls.crawl.controls;
    crawl.concurrency.setValue(17);
    expect(crawl.concurrency.invalid).toBe(true);
    crawl.max_pages.setValue(0);
    expect(crawl.max_pages.invalid).toBe(true);
  });
});
