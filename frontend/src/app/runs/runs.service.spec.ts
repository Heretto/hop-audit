import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { RunsService } from './runs.service';

describe('RunsService', () => {
  it('calls the run endpoints', () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    const service = TestBed.inject(RunsService);
    const http = TestBed.inject(HttpTestingController);
    const body = {
      scope: { mode: 'site' as const, sections: [], pages: [] },
      analyses: [],
      help_center_ids: [],
      reuse_crawl: true,
      recheck_external: false,
      focus: '',
    };
    service.preview('s1').subscribe();
    service.start('s1', body).subscribe();
    service.forSite('s1').subscribe();
    service.all().subscribe();
    service.get('r1').subscribe();
    service.log('r1').subscribe();
    service.control('r1', 'pause').subscribe();
    expect(http.match(() => true).map((r) => `${r.request.method} ${r.request.url}`)).toEqual([
      'GET /api/v1/sites/s1/runs/preview',
      'POST /api/v1/sites/s1/runs',
      'GET /api/v1/sites/s1/runs',
      'GET /api/v1/runs',
      'GET /api/v1/runs/r1',
      'GET /api/v1/runs/r1/log',
      'POST /api/v1/runs/r1/pause',
    ]);
  });
});
