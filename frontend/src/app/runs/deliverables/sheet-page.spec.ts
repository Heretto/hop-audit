import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { RunsService } from '../runs.service';
import { sampleDeliverables } from '../testing';
import { SheetPage } from './sheet-page';

describe('SheetPage', () => {
  function render(kind = 'exec') {
    const runs = {
      deliverables: vi.fn(() => of(sampleDeliverables())),
      sheetHtml: vi.fn(() => of('<div>exec sheet</div>')),
      sheetPdf: vi.fn(() => of(new Blob(['%PDF']))),
    };
    TestBed.configureTestingModule({
      imports: [SheetPage],
      providers: [provideRouter([]), { provide: RunsService, useValue: runs }],
    });
    const fixture = TestBed.createComponent(SheetPage);
    fixture.componentRef.setInput('runId', 'r1');
    fixture.componentRef.setInput('kind', kind);
    fixture.detectChanges();
    return {
      fixture,
      page: fixture.componentInstance,
      runs,
      el: fixture.nativeElement as HTMLElement,
    };
  }

  it('shows the sheet full size with whether it fits', () => {
    const { fixture, page, runs, el } = render();
    expect(runs.sheetHtml).toHaveBeenCalledWith('r1', 'exec');
    expect(el.querySelector('h1')!.textContent).toBe('Executive brief');
    expect(el.querySelector('a.back')!.getAttribute('href')).toBe('/audits/r1/deliverables');
    expect(el.textContent).toContain('Measuring…');
    page.height.set(1038);
    fixture.detectChanges();
    expect(el.textContent).toContain('Every page fits on Letter (tallest 1038 px of 1056).');
    page.height.set(1100);
    fixture.detectChanges();
    expect(el.textContent).toContain('A page overflows Letter by 44 px');
  });

  it('downloads the PDF', () => {
    URL.createObjectURL = vi.fn(() => 'blob:x');
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {}); // jsdom can't navigate
    const { page, runs } = render('lead');
    page.pdf();
    expect(runs.sheetPdf).toHaveBeenCalledWith('r1', 'lead');
    expect(click).toHaveBeenCalled();
    click.mockRestore();
  });
});
