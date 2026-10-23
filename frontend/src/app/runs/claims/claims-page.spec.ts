import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { ClaimsView } from '../run.model';
import { RunsService } from '../runs.service';
import { sampleClaimsView } from '../testing';
import { ClaimsPage, PAGE_SIZE } from './claims-page';

describe('ClaimsPage', () => {
  function render(view: ClaimsView = sampleClaimsView()) {
    const runs = {
      claims: vi.fn(() => of(view)),
      claimsCsv: vi.fn(() => of(new Blob(['subject']))),
    };
    TestBed.configureTestingModule({
      imports: [ClaimsPage],
      providers: [provideRouter([]), { provide: RunsService, useValue: runs }],
    });
    const fixture = TestBed.createComponent(ClaimsPage);
    fixture.componentRef.setInput('runId', 'r1');
    fixture.detectChanges();
    return {
      fixture,
      page: fixture.componentInstance,
      runs,
      el: fixture.nativeElement as HTMLElement,
    };
  }

  it('lists claims with their pages and the groups they were matched into', () => {
    const { el, runs } = render();
    const text = el.textContent!;
    expect(runs.claims).toHaveBeenCalledWith('r1');
    expect(text).toContain('5 claims from 4 articles');
    expect(text).toContain(
      '4 matched with statements in other articles by embeddings (OpenAI · Team key)',
    );
    expect(text).toContain('The late fee is $10.');
    expect(text).toContain('billing/faq');
    expect(text).toContain('Group 1 · 2 articles');
    expect(text).toMatch(/1 · late payment fee\s*Compared/);
    expect(text).toContain('2 claims in 2 articles · 1 candidate');
    expect(text).toMatch(/2 · refund window\s*Same wording/);
    const link = el.querySelector('.where a') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('/audits/r1/pages/p1');
  });

  it('shows a group when it is clicked, and all claims when clicked again', () => {
    const { page, fixture, el } = render();
    page.showGroup(page.groups()[1]);
    fixture.detectChanges();
    expect(page.shown().map((c) => c.slug)).toEqual(['billing/fees', 'billing/refunds']);
    expect(el.querySelector('.group.selected')!.textContent).toContain('refund window');
    page.showGroup(page.groups()[1]);
    expect(page.shown().length).toBe(5);
  });

  it('pages long lists', () => {
    const many = Array.from({ length: PAGE_SIZE + 7 }, (_, i) => ({
      ...sampleClaimsView().claims[0],
      statement: `Claim ${i}`,
    }));
    const { page } = render(sampleClaimsView({ claims: many }));
    expect(page.page().length).toBe(PAGE_SIZE);
    page.limit.set(page.limit() + 50);
    expect(page.page().length).toBe(PAGE_SIZE + 7);
    page.filter({ query: 'Claim 1' });
    expect(page.limit()).toBe(PAGE_SIZE);
  });

  it('explains an audit without claims', () => {
    const { el } = render(sampleClaimsView({ method: null, claims: [], groups: [] }));
    expect(el.textContent).toContain('not matched across articles in this audit');
    expect(el.textContent).toContain('No claims yet.');
    expect(el.textContent).toContain('No statements matched across articles.');
  });

  it('exports the claims', () => {
    URL.createObjectURL = vi.fn(() => 'blob:x'); // jsdom has neither
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {}); // jsdom can't navigate
    const { page, runs } = render();
    page.exportCsv();
    expect(runs.claimsCsv).toHaveBeenCalledWith('r1');
    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    click.mockRestore();
  });

  it('shows why the claims could not load', () => {
    TestBed.configureTestingModule({
      imports: [ClaimsPage],
      providers: [
        provideRouter([]),
        {
          provide: RunsService,
          useValue: { claims: () => throwError(() => ({ error: { detail: 'Audit not found' } })) },
        },
      ],
    });
    const fixture = TestBed.createComponent(ClaimsPage);
    fixture.componentRef.setInput('runId', 'x');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Audit not found');
  });
});
