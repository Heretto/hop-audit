import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { ACTIVE } from '../runs/run.model';
import { RunsService } from '../runs/runs.service';

/**
 * /sites/:id opens the site's latest results: the newest completed audit's
 * dashboard, a running audit's progress, or Run audit when there's none yet.
 */
export const siteHomeGuard: CanActivateFn = (route) => {
  const router = inject(Router);
  const id = route.paramMap.get('id')!;
  return inject(RunsService)
    .forSite(id)
    .pipe(
      map((runs) => {
        const done = runs.find((r) => r.status === 'completed');
        if (done) return router.createUrlTree(['/audits', done.id]);
        const active = runs.find((r) => ACTIVE.includes(r.status));
        if (active) return router.createUrlTree(['/audits', active.id, 'progress']);
        return router.createUrlTree(['/sites', id, 'run']);
      }),
      catchError(() => of(router.createUrlTree(['/sites']))),
    );
};
