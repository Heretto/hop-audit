import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  convertToParamMap,
  provideRouter,
  Router,
  UrlTree,
} from '@angular/router';
import { firstValueFrom, Observable, of, throwError } from 'rxjs';
import { RunsService } from '../runs/runs.service';
import { listItem } from '../runs/testing';
import { siteHomeGuard } from './site-home.guard';

describe('siteHomeGuard', () => {
  async function target(runs: Observable<unknown>) {
    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: RunsService, useValue: { forSite: () => runs } }],
    });
    const route = { paramMap: convertToParamMap({ id: 's1' }) } as ActivatedRouteSnapshot;
    const result = TestBed.runInInjectionContext(() =>
      siteHomeGuard(route, {} as never),
    ) as Observable<UrlTree>;
    return TestBed.inject(Router).serializeUrl(await firstValueFrom(result));
  }

  it('opens the newest completed audit', async () => {
    expect(
      await target(of([listItem({ id: 'r9', status: 'running' }), listItem({ id: 'r8' })])),
    ).toBe('/audits/r8');
  });

  it('opens a running first audit, or Run audit when there is none', async () => {
    expect(await target(of([listItem({ id: 'r1', status: 'running' })]))).toBe(
      '/audits/r1/progress',
    );
    TestBed.resetTestingModule();
    expect(await target(of([]))).toBe('/sites/s1/run');
    TestBed.resetTestingModule();
    expect(await target(throwError(() => new Error('x')))).toBe('/sites');
  });
});
