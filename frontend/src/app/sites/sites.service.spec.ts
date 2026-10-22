import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { apiErrors, SitesService } from './sites.service';
import { sampleSite } from './testing';

describe('SitesService', () => {
  let service: SitesService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(SitesService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('uses the /api/v1/sites collection without a trailing slash', () => {
    const site = sampleSite();
    service.list().subscribe();
    service.defaults().subscribe();
    service.get('s1').subscribe();
    service.create(site).subscribe();
    service.update('s1', site).subscribe();
    service.delete('s1').subscribe();
    service.detect('https://a.com/', '', false).subscribe();

    const calls = http.match(() => true).map((r) => `${r.request.method} ${r.request.url}`);
    expect(calls).toEqual([
      'GET /api/v1/sites',
      'GET /api/v1/sites/defaults',
      'GET /api/v1/sites/s1',
      'POST /api/v1/sites',
      'PUT /api/v1/sites/s1',
      'DELETE /api/v1/sites/s1',
      'POST /api/v1/sites/detect',
    ]);
  });

  it('sends detection options', () => {
    service.detect('https://a.com/', 'https://a.com/s.xml', false).subscribe();
    const req = http.expectOne('/api/v1/sites/detect');
    expect(req.request.body).toEqual({
      start_url: 'https://a.com/',
      sitemap_url: 'https://a.com/s.xml',
      respect_robots: false,
    });
    req.flush({});
  });
});

describe('apiErrors', () => {
  it('reads FastAPI validation details', () => {
    const error = {
      error: {
        detail: [
          {
            loc: ['body', 'help_centers'],
            msg: 'Value error, exactly one help center must be primary',
          },
          { loc: ['body'], msg: 'Value error, bad' },
        ],
      },
    };
    expect(apiErrors(error)).toEqual([
      'help_centers: exactly one help center must be primary',
      'bad',
    ]);
  });

  it('reads string details and falls back for anything else', () => {
    expect(apiErrors({ error: { detail: 'Site not found' } })).toEqual(['Site not found']);
    expect(apiErrors(new Error('x'))).toEqual(['Something went wrong. Try again.']);
  });
});
