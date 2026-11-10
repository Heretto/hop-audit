import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of, throwError } from 'rxjs';
import { IntegrityRow, IntegrityView, Tier } from '../run.model';
import { RunsService } from '../runs.service';
import { sampleIntegrityView } from '../testing';
import { FindingsPage, PAGE_SIZE } from './findings-page';

describe('FindingsPage', () => {
  function render(view: IntegrityView = sampleIntegrityView()) {
    const runs = {
      integrity: vi.fn(() => of(view)),
      updateIntegrity: vi.fn(
        (id: string, change: { tier?: Tier; example?: boolean; triage_note?: string }) => {
          const f = view.findings.find((x) => x.id === id)!;
          const saved: IntegrityRow = {
            ...f,
            ...(change.tier ? { tier: change.tier } : {}),
            ...(change.triage_note !== undefined ? { triage_note: change.triage_note.trim() } : {}),
            example_rank: change.example
              ? 1
              : change.example === false || (change.tier && change.tier !== 'firm')
                ? null
                : f.example_rank,
          };
          return of(saved);
        },
      ),
      confirmTriage: vi.fn(() =>
        of({ ...view, triage: { status: 'confirmed' as const, confirmed_by: 'me@x.com' } }),
      ),
      integrityCsv: vi.fn(() => of(new Blob(['code']))),
    };
    TestBed.configureTestingModule({
      imports: [FindingsPage],
      providers: [provideRouter([]), { provide: RunsService, useValue: runs }],
    });
    const fixture = TestBed.createComponent(FindingsPage);
    fixture.componentRef.setInput('runId', 'r1');
    fixture.detectChanges();
    return {
      fixture,
      page: fixture.componentInstance,
      runs,
      el: fixture.nativeElement as HTMLElement,
    };
  }

  it('lists findings with quotes, slugs and notes, and the recount', () => {
    const { el } = render();
    const text = el.textContent!;
    expect(text).toContain('Content integrity findings');
    expect(text).toContain('Not triaged yet');
    expect(text).toContain('233 articles in 2 help centers (US English, Français)');
    expect(text).toContain('found 5 candidates');
    expect(text).toContain('Late payments may lower your score.');
    expect(text).toContain('credit-faq');
    expect(text).toContain('Triage note: Likely rounding.');
    expect(text).toContain('Firm + review + dropped = 5 candidates');
    expect(text).toContain('2 High · 1 Medium · 0 Low');
    expect(text).toContain('91 articles · 103 pages');
  });

  it('lays out each finding with its tier, summary and links to the quoted articles', () => {
    const { el } = render();
    const first = el.querySelector('.finding')!;
    expect(el.querySelector('.list-head')!.textContent).toContain(
      'Tier · severity · ID · one-sheet example',
    );
    expect(first.querySelector('.meta')!.textContent).toMatch(
      /High\s*C-01\s*US English.*Confirm issue\s*For review\s*Drop.*Use as example/s,
    );
    expect(first.querySelector('.why')!.textContent).toBe('A customer reads opposite answers.');
    const open = first.querySelectorAll<HTMLAnchorElement>('a.open');
    expect(open.length).toBe(1); // the second quote has no URL
    expect(open[0].href).toBe('https://help.lumen.com/late-payments');
    expect(open[0].target).toBe('_blank');
    const details = [...first.querySelectorAll<HTMLAnchorElement>('a.details')];
    expect(details.map((a) => a.getAttribute('href'))).toEqual([
      '/audits/r1/pages/p1',
      '/audits/r1/pages/p2',
    ]);
  });

  it('recounts at once when a tier changes, and reopens the triage', () => {
    const { page, runs } = render(sampleIntegrityView({ triage: { status: 'confirmed' } }));
    page.setTier(page.findings()[0], 'review');
    expect(runs.updateIntegrity).toHaveBeenCalledWith('c1', { tier: 'review' });
    expect(page.counts().firm).toBe(2);
    expect(page.counts().review).toBe(2);
    expect(page.view()!.triage.status).toBe('in_progress');
  });

  it('puts a finding back when saving fails', () => {
    const { page, runs } = render();
    runs.updateIntegrity.mockReturnValueOnce(throwError(() => ({ error: { detail: 'nope' } })));
    page.setTier(page.findings()[0], 'drop');
    expect(page.findings()[0].tier).toBe('firm');
  });

  it('picks examples from firm findings only, and leaving firm clears one', () => {
    const { fixture, page, el } = render();
    page.toggleExample(page.findings()[0]);
    expect(page.picked().map((f) => f.code)).toEqual(['C-01']);
    expect(page.hint()).toBe('pick 2 more');
    page.setTier(page.findings()[0], 'review');
    expect(page.picked()).toEqual([]);
    fixture.detectChanges();
    const reviewRow = [...el.querySelectorAll('.finding')].find((r) =>
      r.textContent!.includes('D-01'),
    )!;
    const star = [...reviewRow.querySelectorAll('button')].find((b) =>
      b.textContent!.includes('Use as example'),
    )!;
    expect(star.disabled).toBe(true);
  });

  it('draws the example button as the mockup does: a star, lit once picked', () => {
    const { fixture, page, el } = render();
    const button = () => el.querySelector('button.example') as HTMLButtonElement;
    expect(button().querySelector('mat-icon')?.textContent?.trim()).toBe('star_outline');
    expect(button().classList).not.toContain('on');
    expect(el.querySelectorAll('.pick')).toHaveLength(0);
    page.toggleExample(page.findings()[0]);
    fixture.detectChanges();
    expect(button().querySelector('mat-icon')?.textContent?.trim()).toBe('star');
    expect(button().classList).toContain('on');
    expect(button().textContent).toContain('One-sheet example');
    expect(el.querySelectorAll('.pick')).toHaveLength(1);
  });

  it('saves a triage note only when it changed', () => {
    const { page, runs } = render();
    const f = page.findings()[0];
    page.saveNote(f, '');
    expect(runs.updateIntegrity).not.toHaveBeenCalled();
    page.saveNote(f, ' Checked live. ');
    expect(runs.updateIntegrity).toHaveBeenCalledWith('c1', { triage_note: ' Checked live. ' });
    expect(page.findings()[0].triage_note).toBe('Checked live.');
  });

  it('filters and pages', () => {
    const many = sampleIntegrityView();
    many.findings = Array.from({ length: PAGE_SIZE + 3 }, (_, i) => ({
      ...many.findings[0],
      id: `f${i}`,
      code: `C-${i}`,
    }));
    const { page } = render(many);
    expect(page.page()).toHaveLength(PAGE_SIZE);
    page.limit.set(PAGE_SIZE * 2);
    expect(page.page()).toHaveLength(PAGE_SIZE + 3);
    page.filter({ query: 'C-27' });
    expect(page.shown().map((f) => f.code)).toEqual(['C-27']);
    expect(page.limit()).toBe(PAGE_SIZE);
  });

  it('says so when the review did not run', () => {
    const v = sampleIntegrityView({ findings: [] });
    v.run.stages = [
      {
        key: 'content_integrity',
        label: 'Content integrity',
        status: 'failed',
        done: 3,
        total: 4,
        detail: "Content Integrity Reviewer didn't review this audit: 3 failed batch(es).",
      },
    ];
    const { el } = render(v);
    expect(el.textContent).toContain("didn't review this audit");
    expect(el.textContent).toContain('No candidates: the review did not run.');
    expect(el.textContent).not.toContain('The reviewer found no candidates.');
  });

  it('confirms the triage', () => {
    const { fixture, page, runs, el } = render();
    vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    page.confirm();
    fixture.detectChanges();
    expect(runs.confirmTriage).toHaveBeenCalledWith('r1');
    expect(el.textContent).toContain('Triage confirmed');
    expect(el.textContent).toContain('Confirmed by me@x.com');
    expect(el.textContent).toContain('The reports are built from these calls.');
  });

  it('confirms and goes on to the reports', () => {
    const { fixture, page, el } = render();
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const button = el.querySelector<HTMLButtonElement>('.page-actions button[color="primary"]')!;
    expect(button.textContent).toContain('Confirm triage and build reports');
    // Reports can be built before the triage is confirmed.
    expect(el.querySelector('.page-actions a[href="/audits/r1/deliverables"]')).not.toBeNull();
    page.confirm();
    fixture.detectChanges();
    expect(navigate).toHaveBeenCalledWith(['/audits', 'r1', 'deliverables']);
    const link = el.querySelector('.page-actions a[href="/audits/r1/deliverables"]');
    expect(link?.textContent).toContain('Reports');
  });

  it('offers the reports for an own-docs site too', () => {
    const { el } = render(sampleIntegrityView({ purpose: 'own' }));
    const button = el.querySelector<HTMLButtonElement>('.page-actions button[color="primary"]')!;
    expect(button.textContent).toContain('Confirm triage and build reports');
    expect(el.querySelector('.page-actions a[href="/audits/r1/deliverables"]')).not.toBeNull();
  });
});
