import { Clipboard } from '@angular/cdk/clipboard';
import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { provideRouter } from '@angular/router';
import { HopAgentService } from '@heretto/hop-ui';
import { of } from 'rxjs';
import { SitesService } from '../../sites/sites.service';
import { sampleSite } from '../../sites/testing';
import { LogEntry, RunDetail } from '../run.model';
import { RunsService } from '../runs.service';
import { sampleRun } from '../testing';
import { appendLog, AuditPage, logText, POLL_MS } from './audit-page';

const LOG: LogEntry[] = [
  {
    id: 1,
    at: '2026-10-22T09:14:02Z',
    stage: 'discover',
    level: 'info',
    message: 'Read sitemap.xml: 1,286 URLs.',
  },
  {
    id: 2,
    at: '2026-10-22T09:15:41Z',
    stage: 'crawl',
    level: 'warn',
    message: '/api/x returned 503 twice; retried.',
  },
];

describe('AuditPage', () => {
  afterEach(() => vi.useRealTimers());

  function render(run: RunDetail = sampleRun()) {
    // A tiny server: controls change the run that the next poll reads.
    let current = run;
    const statuses: Record<string, RunDetail['status']> = {
      pause: 'paused',
      resume: 'running',
      cancel: 'cancelled',
    };
    const runs = {
      get: vi.fn(() => of(current)),
      log: vi.fn((_id: string, _after?: number) => of(LOG)),
      control: vi.fn((_id: string, action: string) =>
        of((current = { ...current, status: statuses[action] })),
      ),
    };
    const copy = vi.fn();
    TestBed.configureTestingModule({
      imports: [AuditPage],
      providers: [
        provideRouter([]),
        { provide: RunsService, useValue: runs },
        {
          provide: SitesService,
          useValue: {
            get: () =>
              of({ ...sampleSite({ agent_assignments: { readability: 'a1' } }), id: 's1' }),
          },
        },
        {
          provide: HopAgentService,
          useValue: {
            listAgents: () =>
              of([
                {
                  id: 'a1',
                  name: 'Readability Reviewer',
                  ai_configuration: { model: 'claude-sonnet-4-5', name: 'Anthropic' },
                },
              ]),
          },
        },
        { provide: Clipboard, useValue: { copy } },
        { provide: MatDialog, useValue: { open: () => ({ afterClosed: () => of(true) }) } },
      ],
    });
    const fixture = TestBed.createComponent(AuditPage);
    fixture.componentRef.setInput('runId', 'r1');
    fixture.detectChanges();
    return {
      fixture,
      page: fixture.componentInstance,
      runs,
      copy,
      el: fixture.nativeElement as HTMLElement,
    };
  }

  it('shows progress, stages, agents and the log', () => {
    const { el, page } = render();
    const text = el.textContent!;
    expect(text).toContain('Audit #15');
    expect(text).toContain('61%');
    expect(text).toContain('372 of 608 pages crawled');
    expect(text).toContain('/authoring, /api (372 pages) · 2 help centers · 2 analyses');
    expect(text).toContain('608 / 608');
    expect(text).toContain('Pending');
    expect(text).toContain('Readability Reviewer');
    expect(text).toContain('claude-sonnet-4-5 · Anthropic');
    expect(text).toContain('2 entries');
    expect(el.querySelector('.log li.warn')?.textContent).toContain('returned 503');
    expect(el.querySelector('.progress')?.classList).toContain('hop-shimmer');
    expect(page.stageCount(sampleRun().stages[3])).toBe('Pending');
  });

  it('polls while the run is active and stops when it ends', () => {
    vi.useFakeTimers();
    const { runs } = render();
    expect(runs.get).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(POLL_MS);
    expect(runs.get).toHaveBeenCalledTimes(2);
    runs.get.mockReturnValue(of(sampleRun({ status: 'completed', progress: 100 })));
    vi.advanceTimersByTime(POLL_MS);
    vi.advanceTimersByTime(POLL_MS * 3);
    expect(runs.get).toHaveBeenCalledTimes(3);
  });

  it('polls the log for newer entries only and appends them', () => {
    vi.useFakeTimers();
    const { runs, page } = render();
    expect(runs.log).toHaveBeenLastCalledWith('r1', 0);
    const newer: LogEntry = {
      id: 3,
      at: '2026-10-22T09:16:00Z',
      stage: 'crawl',
      level: 'detail',
      message: '/a: 200.',
    };
    runs.log.mockReturnValue(of([LOG[1], newer])); // overlaps what's held
    vi.advanceTimersByTime(POLL_MS);
    expect(runs.log).toHaveBeenLastCalledWith('r1', 2);
    expect(page.log().map((e) => e.id)).toEqual([1, 2, 3]);
  });

  it('appends only entries newer than the last one held', () => {
    expect(appendLog(LOG, [LOG[1]])).toBe(LOG);
    expect(appendLog([], LOG)).toEqual(LOG);
  });

  it('pauses, resumes and cancels', () => {
    const { page, runs } = render();
    page.control('pause');
    expect(runs.control).toHaveBeenCalledWith('r1', 'pause');
    expect(page.run()!.status).toBe('paused');
    page.control('resume');
    expect(page.run()!.status).toBe('running');
    page.cancel();
    expect(runs.control).toHaveBeenCalledWith('r1', 'cancel');
    expect(page.run()!.status).toBe('cancelled');
  });

  it('shows one card per agent with its stats', () => {
    const run = sampleRun({
      stages: [
        { key: 'readability', label: 'Readability', status: 'done', done: 1, total: 1, detail: '' },
        {
          key: 'summary',
          label: 'Summary report',
          status: 'running',
          done: 0,
          total: 1,
          detail: '',
        },
      ],
      agent_stats: {
        a1: {
          name: 'Readability Reviewer',
          model: 'claude-sonnet-4-5',
          provider: 'anthropic',
          tokens: 612000,
          findings: 14,
          errors: 0,
          retries: 2,
          status: 'done',
        },
      },
    });
    const { page, el } = render(run);
    // Readability and Summary share agent a1 in this site's assignments.
    page.site.update((s) =>
      s ? { ...s, agent_assignments: { readability: 'a1', summary: 'a1' } } : s,
    );
    expect(page.runAgents()).toHaveLength(1);
    expect(page.runAgents()[0].stage.status).toBe('running');
    expect(page.agentLine(page.runAgents()[0].stats)).toBe(
      '612k tokens · 0 errors · 2 retries · 14 findings',
    );
    expect(page.agentLine(undefined)).toBe('—');
    expect(el.textContent).toContain('Readability Reviewer');
  });

  it('marks an agent that stopped', () => {
    const run = sampleRun({
      agent_stats: {
        a1: {
          name: 'Readability Reviewer',
          model: 'm',
          provider: 'p',
          tokens: 0,
          findings: 0,
          errors: 3,
          retries: 0,
          status: 'stopped',
        },
      },
    });
    const { page } = render(run);
    expect(page.runAgents()[0].stage.status).toBe('failed');
    expect(page.agentChip(page.runAgents()[0].stage).label).toBe('Stopped');
  });

  it('hides the controls and shows the error for a failed run', () => {
    const { el } = render(
      sampleRun({
        status: 'failed',
        error: 'Every help center refused the crawler; see the run log.',
      }),
    );
    expect(el.textContent).toContain('Every help center refused the crawler');
    expect(el.textContent).not.toContain('Cancel run');
  });

  it('copies the log as plain lines', () => {
    const { page, copy } = render();
    page.copyLog();
    const text = copy.mock.calls[0][0] as string;
    expect(text.split('\n')).toHaveLength(2);
    expect(text).toMatch(/^\d\d:\d\d:\d\d {2}discover {3}Read sitemap.xml/);
    expect(logText([])).toBe('');
  });
});
