import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { RunsService } from '../runs.service';
import { sampleFinding } from '../testing';
import { FindingCard } from './finding-card';
import { Finding } from '../run.model';

describe('FindingCard', () => {
  function render(finding: Finding = sampleFinding()) {
    const runs = {
      updateFinding: vi.fn((id: string, dismissed: boolean, reason: string) =>
        of({ ...finding, dismissed, dismissed_reason: reason }),
      ),
    };
    TestBed.configureTestingModule({
      imports: [FindingCard],
      providers: [{ provide: RunsService, useValue: runs }],
    });
    const fixture = TestBed.createComponent(FindingCard);
    fixture.componentRef.setInput('finding', finding);
    const changed: Finding[] = [];
    fixture.componentInstance.changed.subscribe((f) => changed.push(f));
    fixture.detectChanges();
    return {
      fixture,
      card: fixture.componentInstance,
      runs,
      changed,
      el: fixture.nativeElement as HTMLElement,
    };
  }

  it('shows severity, focus, agent, quote and suggestion', () => {
    const { el } = render(sampleFinding({ on_focus: true }));
    expect(el.querySelector('.sev.error')?.textContent).toBe('High');
    expect(el.textContent).toContain('Site focus');
    expect(el.textContent).toContain('Readability Reviewer · claude-sonnet-4-5');
    expect(el.querySelector('.quote')?.textContent).toContain('If the target element');
    expect(el.textContent).toContain('Suggested');
  });

  it('shows the target of a link finding', () => {
    const { el } = render(
      sampleFinding({ target: 'https://x.com/gone', page_count: 3, quote: '' }),
    );
    expect(el.textContent).toContain('https://x.com/gone · linked from 3 pages');
    expect(el.querySelector('.quote')).toBeNull();
  });

  it('dismisses with a reason and restores', () => {
    const { fixture, card, runs, changed } = render();
    card.asking.set(true);
    card.reason = '  Intended repetition. ';
    card.save(true);
    expect(runs.updateFinding).toHaveBeenCalledWith('f1', true, 'Intended repetition.');
    expect(changed[0].dismissed).toBe(true);
    expect(card.asking()).toBe(false);
    fixture.componentRef.setInput('finding', changed[0]);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Dismissed: Intended repetition.');
    card.save(false);
    expect(runs.updateFinding).toHaveBeenLastCalledWith('f1', false, '');
  });
});
