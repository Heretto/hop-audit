import { Clipboard } from '@angular/cdk/clipboard';
import { DatePipe, DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar } from '@angular/material/snack-bar';
import { RouterLink } from '@angular/router';
import {
  AgentSummary,
  HopAgentService,
  HopConfirmDialogComponent,
  HopConfirmDialogData,
} from '@heretto/hop-ui';
import { filter, forkJoin, switchMap } from 'rxjs';
import { Site } from '../../sites/site.model';
import { apiErrors, SitesService } from '../../sites/sites.service';
import { duration, estimate, scopeLabel, statusChip, tokens } from '../run-format';
import { ACTIVE, AgentStats, LogEntry, RunDetail, Stage } from '../run.model';
import { RunsService } from '../runs.service';
import { RunLog } from './run-log';

export const POLL_MS = 2000;

const STAGE_ICONS: Record<Stage['status'], string> = {
  done: 'check_circle',
  running: 'progress_activity',
  pending: 'schedule',
  skipped: 'block',
  failed: 'error',
};

const AGENT_CHIPS: Record<Stage['status'], { cls: string; label: string }> = {
  pending: { cls: 'hop-status-chip-pending', label: 'Pending' },
  running: { cls: 'hop-status-chip-running', label: 'Running' },
  done: { cls: 'hop-status-chip-completed', label: 'Completed' },
  failed: { cls: 'hop-status-chip-failed', label: 'Stopped' },
  skipped: { cls: '', label: 'Not run' },
};

/** ``held`` plus the newer entries; overlapping polls never add one twice. */
export function appendLog(held: LogEntry[], newer: LogEntry[]): LogEntry[] {
  const last = held.at(-1)?.id ?? 0;
  const fresh = newer.filter((e) => e.id > last);
  return fresh.length ? [...held, ...fresh] : held;
}

/** One line per log entry, in the viewer's time zone: safe to paste into a bug report. */
export function logText(entries: LogEntry[]): string {
  return entries
    .map(
      (e) =>
        `${new Date(e.at).toLocaleTimeString('en-GB', { hour12: false })}  ${e.stage.padEnd(10)} ${e.message}`,
    )
    .join('\n');
}

@Component({
  selector: 'app-audit-page',
  imports: [
    DatePipe,
    DecimalPipe,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    RunLog,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './audit-page.html',
  styleUrl: './audit-page.scss',
})
export class AuditPage implements OnInit {
  /** Route parameter. */
  readonly runId = input.required<string>();

  private runs = inject(RunsService);
  private sites = inject(SitesService);
  private agentService = inject(HopAgentService);
  private dialog = inject(MatDialog);
  private snack = inject(MatSnackBar);
  private clipboard = inject(Clipboard);
  private destroyRef = inject(DestroyRef);

  readonly run = signal<RunDetail | null>(null);
  readonly site = signal<Site | null>(null);
  readonly log = signal<LogEntry[]>([]);
  readonly agents = signal<AgentSummary[]>([]);
  readonly error = signal<string | null>(null);
  readonly logOpen = signal(true);
  readonly busy = signal(false);
  readonly now = signal(Date.now());

  readonly icons = STAGE_ICONS;
  readonly active = computed(() => ACTIVE.includes(this.run()?.status ?? 'completed'));
  readonly chip = computed(() => statusChip(this.run()));
  readonly elapsed = computed(() =>
    duration(this.run() ?? { started_at: null, finished_at: null }, this.now()),
  );
  readonly scope = computed(() => (this.run() ? scopeLabel(this.run()!.scope) : ''));
  readonly crawl = computed(() => this.run()?.stages.find((s) => s.key === 'crawl'));
  readonly remaining = computed(() => {
    const run = this.run();
    const crawl = this.crawl();
    if (!run?.started_at || !crawl?.done || !crawl.total || crawl.done >= crawl.total) return null;
    const spent = (this.now() - Date.parse(run.started_at)) / 1000;
    return estimate((spent / crawl.done) * (crawl.total - crawl.done));
  });
  readonly tokenTotal = computed(() =>
    tokens(Object.values(this.run()?.tokens ?? {}).reduce((a, b) => a + b, 0)),
  );

  /** Agents on this run's analyses, one card each, with their stage's status and their stats. */
  readonly runAgents = computed(() => {
    const run = this.run();
    const assigned = (this.site()?.agent_assignments ?? {}) as Record<string, string | null>;
    if (!run) return [];
    const order: Stage['status'][] = ['running', 'failed', 'pending', 'done', 'skipped'];
    const cards = new Map<string, { stage: Stage; id: string }>();
    for (const stage of run.stages) {
      const id = stage.key === 'links' ? null : assigned[stage.key]; // links need no agent
      if (!id) continue;
      const seen = cards.get(id);
      if (!seen || order.indexOf(stage.status) < order.indexOf(seen.stage.status))
        cards.set(id, { stage, id });
    }
    return [...cards.values()].map(({ stage, id }) => {
      const agent = this.agents().find((a) => a.id === id);
      const stats = run.agent_stats?.[id];
      return {
        id,
        stage: stats?.status === 'stopped' ? { ...stage, status: 'failed' as const } : stage,
        name: stats?.name ?? agent?.name ?? 'Unknown agent',
        model: stats
          ? `${stats.model} · ${stats.provider}`
          : agent?.ai_configuration
            ? `${agent.ai_configuration.model} · ${agent.ai_configuration.name}`
            : 'No AI configuration',
        stats,
      };
    });
  });

  /** "612k tokens · 0 errors · 14 findings" */
  agentLine(stats: AgentStats | undefined): string {
    if (!stats) return '—';
    const parts = [
      `${tokens(stats.tokens)} tokens`,
      `${stats.errors} error${stats.errors === 1 ? '' : 's'}`,
    ];
    if (stats.retries) parts.push(`${stats.retries} retr${stats.retries === 1 ? 'y' : 'ies'}`);
    parts.push(`${stats.findings} findings`);
    return parts.join(' · ');
  }

  ngOnInit(): void {
    this.agentService.listAgents().subscribe({ next: (a) => this.agents.set(a), error: () => {} });
    this.refresh(true);
    const timer = setInterval(() => {
      this.now.set(Date.now());
      if (this.active()) this.refresh(false);
    }, POLL_MS);
    this.destroyRef.onDestroy(() => clearInterval(timer));
  }

  refresh(first: boolean): void {
    // The log comes in increments: only entries newer than the last one held.
    const after = first ? 0 : (this.log().at(-1)?.id ?? 0);
    forkJoin([this.runs.get(this.runId()), this.runs.log(this.runId(), after)]).subscribe({
      next: ([run, log]) => {
        this.run.set(run);
        if (first) this.log.set(log);
        else if (log.length) this.log.update((held) => appendLog(held, log));
        this.error.set(null);
        if (first)
          this.sites.get(run.site_id).subscribe({ next: (s) => this.site.set(s), error: () => {} });
      },
      error: (e) => this.error.set(apiErrors(e).join(' ')),
    });
  }

  agentChip(stage: Stage) {
    return AGENT_CHIPS[stage.status];
  }

  stageCount(stage: Stage): string {
    if (stage.status === 'pending') return 'Pending';
    if (stage.status === 'skipped') return 'Skipped';
    return `${stage.done.toLocaleString()} / ${stage.total.toLocaleString()}`;
  }

  stagePercent(stage: Stage): number {
    if (stage.status === 'done') return 100;
    return stage.total ? Math.round((100 * stage.done) / stage.total) : 0;
  }

  control(action: 'pause' | 'resume'): void {
    this.busy.set(true);
    this.runs.control(this.runId(), action).subscribe({
      next: (run) => {
        this.run.set(run);
        this.busy.set(false);
        this.refresh(false);
      },
      error: (e) => {
        this.busy.set(false);
        this.snack.open(apiErrors(e).join(' '), 'Dismiss');
      },
    });
  }

  cancel(): void {
    const data: HopConfirmDialogData = {
      title: `Cancel audit #${this.run()!.number}?`,
      message: 'The run stops right away, paused or not. Pages already read are kept.',
      confirmText: 'Cancel run',
      cancelText: 'Keep running',
    };
    this.dialog
      .open(HopConfirmDialogComponent, { data })
      .afterClosed()
      .pipe(
        filter(Boolean),
        switchMap(() => this.runs.control(this.runId(), 'cancel')),
      )
      .subscribe({
        next: (run) => {
          this.run.set(run);
          this.refresh(false);
        },
        error: (e) => this.snack.open(apiErrors(e).join(' '), 'Dismiss'),
      });
  }

  copyLog(): void {
    this.clipboard.copy(logText(this.log()));
    this.snack.open('Run log copied', undefined, { duration: 3000 });
  }
}
