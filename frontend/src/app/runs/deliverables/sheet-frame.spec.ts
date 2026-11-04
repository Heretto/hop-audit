import { TestBed } from '@angular/core/testing';
import { naturalHeight, PAGE_H, SheetFrame } from './sheet-frame';

describe('SheetFrame', () => {
  it("measures the root's natural height and puts its fixed height back", () => {
    const doc = document.implementation.createHTMLDocument('sheet');
    doc.body.innerHTML = '<div style="height: 1056px">content</div>';
    const root = doc.body.firstElementChild as HTMLElement;
    let seen = '';
    Object.defineProperty(root, 'scrollHeight', {
      get: () => {
        seen = root.style.height;
        return 1100;
      },
    });
    expect(naturalHeight(doc)).toBe(1100);
    expect(seen).toBe('auto'); // measured without the page's fixed height
    expect(root.style.height).toBe('1056px');
    expect(naturalHeight(document.implementation.createHTMLDocument('empty'))).toBeNull();
  });

  it('frames the sheet in a sandbox and crops a thumbnail', () => {
    const fixture = TestBed.createComponent(SheetFrame);
    fixture.componentRef.setInput('html', '<div>Sheet</div>');
    fixture.componentRef.setInput('crop', 120);
    fixture.componentRef.setInput('label', 'Lead one-sheet');
    fixture.detectChanges();
    const frame = fixture.nativeElement.querySelector('iframe') as HTMLIFrameElement;
    expect(frame.getAttribute('sandbox')).toBe('allow-same-origin'); // no scripts
    expect(frame.getAttribute('srcdoc')).toBe('<div>Sheet</div>');
    expect(frame.title).toBe('Lead one-sheet');
    expect((fixture.nativeElement.querySelector('.frame') as HTMLElement).style.height).toBe(
      '120px',
    );
    expect(PAGE_H).toBe(1056);
  });
});
