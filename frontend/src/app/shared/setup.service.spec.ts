import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { SetupService } from './setup.service';

describe('SetupService', () => {
  it('posts to /api/v1/setup', () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    const http = TestBed.inject(HttpTestingController);
    let result: unknown;
    TestBed.inject(SetupService)
      .ensure()
      .subscribe((r) => (result = r));

    const req = http.expectOne('/api/v1/setup');
    expect(req.request.method).toBe('POST');
    req.flush({ agents_seeded_at: '2026-10-22T00:00:00Z', seeded_agents: { seo: 'a1' } });
    expect(result).toEqual({
      agents_seeded_at: '2026-10-22T00:00:00Z',
      seeded_agents: { seo: 'a1' },
    });
    http.verify();
  });
});
