import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { ReportView } from '../run.model';
import { RunsService } from '../runs.service';
import { sampleReport } from '../testing';
import { ReportPage } from './report-page';

describe('ReportPage', () => {
  function render(view: ReportView = sampleReport()) {
    const runs = {
      report: vi.fn(() => of(view)),
      reportFile: vi.fn(() => of(new Blob(['%PDF']))),
      integrityCsv: vi.fn(() => of(new Blob(['code']))),
    };
    TestBed.configureTestingModule({
      imports: [ReportPage],
      providers: [provideRouter([]), { provide: RunsService, useValue: runs }],
    });
    const fixture = TestBed.createComponent(ReportPage);
    fixture.componentRef.setInput('runId', 'r1');
    fixture.detectChanges();
    return {
      fixture,
      page: fixture.componentInstance,
      runs,
      el: fixture.nativeElement as HTMLElement,
    };
  }

  it('renders the report with its tables, quotes, slugs and appendix', () => {
    const { el, runs } = render();
    expect(runs.report).toHaveBeenCalledWith('r1');
    const text = el.textContent!;
    expect(text).toContain('Lumen Financial — Content Integrity Review');
    expect(text).toContain('As of October 8, 2026');
    expect(text).toContain('· Patrick Bosek');
    expect([...el.querySelectorAll('h3')].map((h) => h.textContent)).toEqual([
      'Findings by category',
      'Contradictions between articles (19)',
      'Appendix: site health',
    ]);
    expect(el.querySelector('q')!.textContent).toBe('Late payments may lower your credit score.');
    expect(el.querySelector('.slug')!.textContent!.trim()).toBe('how-late-payments-affect-credit');
    expect(el.querySelector('.note')!.textContent!.trim()).toBe('(translated)');
    expect(el.querySelector('.sev.severity-high')!.textContent).toBe('High');
    expect(el.querySelector('tr.total')!.textContent).toContain('63');
    expect(el.querySelector('th.num')!.textContent).toBe('Total');
    expect(el.querySelector('.metric')!.textContent).toContain('9 internal · 2 external');
    expect(el.querySelector('img.wordmark')!.getAttribute('src')).toBe('heretto-wordmark.png');
  });

  it('goes back to Deliverables for a prospect review, the dashboard otherwise', () => {
    let { el } = render();
    expect(el.querySelector('a.back')!.getAttribute('href')).toBe('/audits/r1/deliverables');
    expect(el.querySelector('a.back')!.textContent).toContain('Audit #15 · Deliverables');
    TestBed.resetTestingModule();
    ({ el } = render(sampleReport({ purpose: 'own' })));
    expect(el.querySelector('a.back')!.getAttribute('href')).toBe('/audits/r1');
  });

  it('asks for a confirmed triage first', () => {
    const { el } = render(
      sampleReport({ ready: false, reason: 'Confirm the triage on Findings first.', sections: [] }),
    );
    expect(el.textContent).toContain('Confirm the triage on Findings first.');
    expect(el.querySelector('a[href="/audits/r1/findings"]')).not.toBeNull();
    expect(el.querySelector('article')).toBeNull();
    expect(
      el.querySelector<HTMLButtonElement>('.page-actions button[aria-haspopup]')!.disabled,
    ).toBe(true);
  });

  it('exports each format', async () => {
    URL.createObjectURL = vi.fn(() => 'blob:x');
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {}); // jsdom can't navigate
    const { page, runs } = render();
    page.export('report.pdf');
    page.export('report.docx');
    page.export('audit.json');
    page.export('integrity.csv');
    expect(runs.reportFile.mock.calls.map((c) => (c as unknown[])[1])).toEqual([
      'report.pdf',
      'report.docx',
      'audit.json',
    ]);
    expect(runs.integrityCsv).toHaveBeenCalledWith('r1');
    expect(click).toHaveBeenCalledTimes(4);
    click.mockRestore();
  });

  it('says why a PDF could not be made', async () => {
    const { page, runs } = render();
    const blob = new Blob([JSON.stringify({ detail: 'PDFs need Chromium on the server' })]);
    runs.reportFile.mockReturnValue(throwError(() => ({ error: blob })));
    const open = vi.spyOn(page['snack'], 'open');
    page.export('report.pdf');
    await vi.waitFor(() =>
      expect(open).toHaveBeenCalledWith('PDFs need Chromium on the server', 'Dismiss'),
    );
    expect(page.exporting()).toBeNull();
  });
});
