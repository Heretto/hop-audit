import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { AuditsPage } from './audits-page';
import { RunsService } from './runs.service';
import { sampleRun } from './testing';

describe('AuditsPage', () => {
  function render(site?: string) {
    const runs = [
      sampleRun({ id: 'r1', site_id: 's1', number: 2 }),
      sampleRun({
        id: 'r2',
        site_id: 's2',
        site_name: 'Developer Portal',
        number: 6,
        status: 'completed',
      }),
    ];
    TestBed.configureTestingModule({
      imports: [AuditsPage],
      providers: [provideRouter([]), { provide: RunsService, useValue: { all: () => of(runs) } }],
    });
    const fixture = TestBed.createComponent(AuditsPage);
    if (site) fixture.componentRef.setInput('site', site);
    fixture.detectChanges();
    return { page: fixture.componentInstance, el: fixture.nativeElement as HTMLElement };
  }

  it('lists every run with its status', () => {
    const { el } = render();
    expect(el.textContent).toContain('#2 · Heretto Help Center');
    expect(el.textContent).toContain('#6 · Developer Portal');
    expect(el.textContent).toContain('Running · 61%');
    expect(el.textContent).toContain('across your sites');
  });

  it("narrows to one site's runs", () => {
    const { page, el } = render('s2');
    expect(page.rows()!.map((r) => r.id)).toEqual(['r2']);
    expect(el.textContent).toContain('of Developer Portal');
  });
});
