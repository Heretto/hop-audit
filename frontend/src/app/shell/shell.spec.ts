import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { SetupService } from '../shared/setup.service';
import { NAV_ITEMS, Shell } from './shell';

describe('Shell', () => {
  function create(ensure: () => unknown) {
    TestBed.configureTestingModule({
      providers: [{ provide: SetupService, useValue: { ensure } }],
    });
    return TestBed.runInInjectionContext(() => new Shell());
  }

  it('lists Sites, Audits, Agents, Credentials in order (hop-core adds Account and Administration)', () => {
    expect(NAV_ITEMS.map((i) => i.label)).toEqual(['Sites', 'Audits', 'Agents', 'Credentials']);
    expect(NAV_ITEMS.map((i) => i.route)).toEqual(['/sites', '/audits', '/agents', '/credentials']);
  });

  it('runs organization setup on load', () => {
    const ensure = vi.fn(() => of({ agents_seeded_at: 'x', seeded_agents: {} }));
    create(ensure).ngOnInit();
    expect(ensure).toHaveBeenCalledOnce();
  });

  it('logs rather than throws when setup fails', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    create(() => throwError(() => new Error('boom'))).ngOnInit();
    expect(error).toHaveBeenCalled();
    error.mockRestore();
  });
});
