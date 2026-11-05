import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { DeliverablesView } from '../run.model';
import { RunsService } from '../runs.service';
import { sampleCopy, sampleDeliverables } from '../testing';
import {
  DeliverablesPage,
  elapsed,
  imperativeTag,
  joinSender,
  POLL_MS,
  splitSender,
} from './deliverables-page';

describe('DeliverablesPage', () => {
  function render(view: DeliverablesView = sampleDeliverables()) {
    const saved = (change: object) => of({ ...view, ...change } as DeliverablesView);
    const runs = {
      deliverables: vi.fn(() => of(view)),
      buildDeliverables: vi.fn(() => of(sampleDeliverables())),
      updateDeliverables: vi.fn((_id: string, change: object) => saved(change)),
      setLogo: vi.fn(() => of(view)),
      sheetHtml: vi.fn((_id: string, kind: string) => of(`<div>${kind} sheet</div>`)),
      sheetPdf: vi.fn(() => of(new Blob(['%PDF']))),
      reportFile: vi.fn(() => of(new Blob(['%PDF']))),
    };
    TestBed.configureTestingModule({
      imports: [DeliverablesPage],
      providers: [provideRouter([]), { provide: RunsService, useValue: runs }],
    });
    const fixture = TestBed.createComponent(DeliverablesPage);
    fixture.componentRef.setInput('runId', 'r1');
    fixture.detectChanges();
    return {
      fixture,
      page: fixture.componentInstance,
      runs,
      el: fixture.nativeElement as HTMLElement,
    };
  }

  it('reads the sender as name and title, as the one-sheet prints it', () => {
    expect(splitSender('Pat Smith, Account Executive, East')).toEqual({
      sender_name: 'Pat Smith',
      sender_title: 'Account Executive, East',
    });
    expect(splitSender(' ')).toEqual({ sender_name: '', sender_title: '' });
    expect(joinSender('Pat', '')).toBe('Pat');
    expect(joinSender('Pat', 'AE')).toBe('Pat, AE');
  });

  it('tags each why line by its imperative', () => {
    const [ret, risk, ai] = sampleCopy().why;
    expect(imperativeTag(ret)).toEqual({ cls: 'ret', label: 'Customer Retention' });
    expect(imperativeTag(risk)).toEqual({ cls: 'risk', label: 'Risk' });
    expect(imperativeTag(ai)).toEqual({ cls: 'risk', label: 'Risk · AI' });
  });

  it('shows the steps, the four deliverables, the copy and the checklist', () => {
    const { el, runs } = render();
    const text = el.textContent!;
    expect([...el.querySelectorAll('.step strong')].map((s) => s.textContent)).toEqual([
      'Assess',
      'Triage',
      'Build',
      'Hand off',
    ]);
    expect(el.querySelector('.step.now')!.textContent).toContain(
      '2 placeholders · 3 quotes to spot-check',
    );
    expect([...el.querySelectorAll('.deliverable h3')].map((h) => h.textContent)).toEqual([
      'Lead one-sheet',
      'Executive brief',
      'Full findings report',
      'Internal summary',
    ]);
    expect(runs.sheetHtml).toHaveBeenCalledTimes(2);
    expect(el.querySelectorAll('app-sheet-frame').length).toBe(2); // live thumbnails
    expect(text).toContain(
      "Written by Collateral Writer from the findings and the prospect's industry (lending).",
    );
    expect(text).toContain('20 / 26'); // headline line 1
    expect(text).toContain('Each line traces to findings: T-03, U-02; C-01.');
    expect(el.querySelector('.tag.ret')!.textContent).toBe('Customer Retention');
    expect(el.querySelector('.tag.risk')).not.toBeNull();
    expect(text).toContain('Full findings · 63 issues · 9 for review');
    const spot = el.querySelector('a[href="/audits/r1/pages/p9"]')!;
    expect(spot.textContent).toBe('T-03 (fr/paiement-automatique)');
    expect(el.querySelector('.unverified')!.textContent).toBe('unverified');
    expect(el.querySelector('a[href="/audits/r1/deliverables/lead"]')).not.toBeNull();
  });

  it('flags copy over its budget as you type', async () => {
    const { page, fixture, el } = render();
    const field = el.querySelector<HTMLInputElement>('.grid-2 input')!;
    field.value = 'A headline that runs far past its budget';
    field.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    await fixture.whenStable();
    expect(page.draft!.headline_line1).toBe('A headline that runs far past its budget');
    expect(page.budget(page.draft!.headline_line1, 'headline_line1')).toEqual({
      text: '40 / 26',
      over: true,
    });
    expect(el.querySelector('.budget.over')!.textContent).toContain('40 / 26');
  });

  it('saves edited copy on blur, and only when it changed', () => {
    const { page, runs } = render();
    page.saveCopy();
    expect(runs.updateDeliverables).not.toHaveBeenCalled();
    page.draft!.exec_headline = 'Governed content for regulated lending';
    page.saveCopy();
    expect(runs.updateDeliverables).toHaveBeenCalledWith('r1', {
      copy: expect.objectContaining({ exec_headline: 'Governed content for regulated lending' }),
    });
    expect(runs.sheetHtml).toHaveBeenCalledTimes(4); // the thumbnails reload
  });

  it('saves the prospect and sender', () => {
    const { page, runs } = render();
    page.sender = 'Pat Smith, Account Executive';
    page.email = ' pat@heretto.com ';
    page.saveProspect();
    expect(runs.updateDeliverables).toHaveBeenCalledWith('r1', {
      prospect: {
        company: 'Lumen Financial',
        sender_name: 'Pat Smith',
        sender_title: 'Account Executive',
        sender_email: 'pat@heretto.com',
      },
    });
  });

  it('ticks a hand-off check, and records measured heights once', () => {
    const { page, runs } = render();
    page.toggle(sampleDeliverables().checklist[1]);
    expect(runs.updateDeliverables).toHaveBeenCalledWith('r1', { spot_checked: true });
    page.toggle(sampleDeliverables().checklist[0]); // not a tick-box
    expect(runs.updateDeliverables).toHaveBeenCalledTimes(1);
    page.measured('lead', 1041); // unchanged
    page.measured('exec', 1060);
    expect(runs.updateDeliverables).toHaveBeenLastCalledWith('r1', { heights: { exec: 1060 } });
  });

  it('builds when nothing is built yet, and asks before a rebuild', () => {
    let { page, runs } = render(sampleDeliverables({ copy: null }));
    page.build();
    expect(runs.buildDeliverables).toHaveBeenCalledWith('r1');
    TestBed.resetTestingModule();
    ({ page, runs } = render());
    const open = vi
      .spyOn(TestBed.inject(MatDialog), 'open')
      .mockReturnValue({ afterClosed: () => of(false) } as never);
    page.build();
    expect(open).toHaveBeenCalled();
    expect(runs.buildDeliverables).not.toHaveBeenCalled();
  });

  it('says why deliverables are unavailable', () => {
    const { el } = render(
      sampleDeliverables({
        available: false,
        reason:
          "Content integrity hasn't run for this audit, so there are no findings to build from.",
        copy: null,
      }),
    );
    expect(el.textContent).toContain("Content integrity hasn't run for this audit");
    expect(el.querySelector('.callout a[href="/audits/r1"]')).not.toBeNull();
    const build = [...el.querySelectorAll<HTMLButtonElement>('.page-actions button')].find((b) =>
      b.textContent!.includes('Build deliverables'),
    )!;
    expect(build.disabled).toBe(true);
    expect(el.querySelectorAll('app-sheet-frame').length).toBe(0);
  });

  it('uploads a logo after checking its type and size', () => {
    const { page, runs } = render();
    const snack = vi.spyOn(page['snack'], 'open');
    const field = (file: File) => ({ target: { files: [file], value: 'x' } }) as unknown as Event;
    page.uploadLogo(field(new File(['x'], 'logo.gif', { type: 'image/gif' })));
    expect(snack).toHaveBeenCalledWith('Use a PNG, JPEG or SVG file.', 'Dismiss');
    page.uploadLogo(
      field(new File([new Uint8Array(600 * 1024)], 'logo.png', { type: 'image/png' })),
    );
    expect(snack).toHaveBeenCalledWith('The logo file is over 512 KB.', 'Dismiss');
    expect(runs.setLogo).not.toHaveBeenCalled();
    page.removeLogo();
    expect(runs.setLogo).toHaveBeenCalledWith('r1', null);
  });

  it('downloads both PDFs, and says why one failed', async () => {
    URL.createObjectURL = vi.fn(() => 'blob:x');
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {}); // jsdom can't navigate
    const { page, runs } = render();
    page.downloadPdfs();
    expect(runs.sheetPdf.mock.calls.map((c) => (c as unknown[])[1])).toEqual(['lead', 'exec']);
    const blob = new Blob([
      JSON.stringify({ detail: 'The executive brief overflows the page by 44 px' }),
    ]);
    runs.sheetPdf.mockReturnValue(throwError(() => ({ error: blob })));
    const snack = vi.spyOn(page['snack'], 'open');
    page.sheetPdf('exec');
    await vi.waitFor(() =>
      expect(snack).toHaveBeenCalledWith(
        'The executive brief overflows the page by 44 px',
        'Dismiss',
      ),
    );
    click.mockRestore();
  });

  it('formats elapsed time', () => {
    expect(elapsed(0)).toBe('0:00');
    expect(elapsed(65_400)).toBe('1:05');
    expect(elapsed(-5)).toBe('0:00');
  });

  it('follows a build in the background until it finishes', async () => {
    vi.useFakeTimers();
    try {
      const started = new Date(Date.now() - 42_000).toISOString();
      const log = [
        { at: started, level: 'info' as const, message: 'Build started by pat@heretto.com.' },
        {
          at: started,
          level: 'info' as const,
          message: 'Asking Collateral Writer (claude) for the copy.',
        },
      ];
      const building = sampleDeliverables({
        copy: null,
        status: 'building',
        started_at: started,
        log,
      });
      const { page, runs, el, fixture } = render(sampleDeliverables({ copy: null }));
      runs.buildDeliverables.mockReturnValue(of(building));
      runs.deliverables.mockReturnValue(of(building));
      page.build();
      fixture.detectChanges();
      expect(page.building()).toBe(true);
      expect(el.querySelector('.build')!.textContent).toContain('Building the one-sheets');
      expect(el.querySelector('.build')!.textContent).toContain('0:42 elapsed');
      expect(el.querySelectorAll('.build-log li').length).toBe(2);
      expect(el.querySelector('mat-progress-bar')).not.toBeNull();

      vi.advanceTimersByTime(POLL_MS);
      expect(runs.deliverables).toHaveBeenCalledTimes(2); // the first load, then a poll

      const done = sampleDeliverables({
        log: [...log, { at: started, level: 'info', message: 'Done: the one-sheets are built.' }],
      });
      runs.deliverables.mockReturnValue(of(done));
      const snack = vi.spyOn(page['snack'], 'open');
      vi.advanceTimersByTime(POLL_MS);
      fixture.detectChanges();
      expect(page.building()).toBe(false);
      expect(snack).toHaveBeenCalledWith('The one-sheets are built.', undefined, {
        duration: 4000,
      });
      expect(runs.sheetHtml).toHaveBeenCalledTimes(2); // the new sheets load
      expect(el.querySelector('.build')).toBeNull();
      expect(el.querySelector('.log-details summary')!.textContent).toContain(
        'Last build: 3 steps',
      );
      vi.advanceTimersByTime(POLL_MS * 3);
      expect(runs.deliverables).toHaveBeenCalledTimes(3); // polling stopped
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows why a build failed, with its log', () => {
    const { el } = render(
      sampleDeliverables({
        copy: null,
        status: 'failed',
        error: "The Collateral Writer couldn't write the copy: Anthropic returned HTTP 400",
        log: [
          {
            at: '2026-11-05T14:41:00Z',
            level: 'info',
            message: 'Build started by pat@heretto.com.',
          },
          { at: '2026-11-05T14:41:30Z', level: 'error', message: 'Anthropic returned HTTP 400' },
        ],
      }),
    );
    expect(el.querySelector('.callout.error')!.textContent).toContain('HTTP 400');
    expect(el.querySelector('.build-log li.error')!.textContent).toContain(
      'Anthropic returned HTTP 400',
    );
    expect(el.querySelector<HTMLDetailsElement>('.log-details')!.open).toBe(true);
  });
});
