import { DatePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { formatSeconds } from '../run-format';
import { LogEntry, Stage } from '../run.model';

/** Steps shown at most per section; Copy log has them all. */
export const MAX_STEPS = 1000;

export interface LogSection {
  key: string;
  label: string;
  status: Stage['status'] | null;
  /** Everything in order, steps included. */
  all: LogEntry[];
  /** Milestones, warnings and errors: what shows without the steps. */
  main: LogEntry[];
  steps: number;
  warnings: number;
  errors: number;
  from: string;
  to: string;
}

const LABELS: Record<string, string> = { run: 'Run' };
const STATUS_LABELS: Record<Stage['status'], { cls: string; label: string }> = {
  pending: { cls: 'hop-status-chip-pending', label: 'Pending' },
  running: { cls: 'hop-status-chip-running', label: 'Running' },
  done: { cls: 'hop-status-chip-completed', label: 'Done' },
  failed: { cls: 'hop-status-chip-failed', label: 'Failed' },
  skipped: { cls: '', label: 'Skipped' },
};

/** The log by stage, in the order the stages first logged. */
export function sections(entries: LogEntry[], stages: Stage[]): LogSection[] {
  const byKey = new Map<string, LogSection>();
  for (const e of entries) {
    let s = byKey.get(e.stage);
    if (!s) {
      const stage = stages.find((x) => x.key === e.stage);
      s = {
        key: e.stage,
        label: stage?.label ?? LABELS[e.stage] ?? e.stage.replace(/_/g, ' '),
        status: stage?.status ?? null,
        all: [],
        main: [],
        steps: 0,
        warnings: 0,
        errors: 0,
        from: e.at,
        to: e.at,
      };
      byKey.set(e.stage, s);
    }
    s.all.push(e);
    s.to = e.at;
    if (e.level === 'detail') s.steps++;
    else s.main.push(e);
    if (e.level === 'warn') s.warnings++;
    if (e.level === 'error') s.errors++;
  }
  return [...byKey.values()];
}

/** "12 entries · 229 steps · 2 warnings · 1 error" */
export function counts(s: LogSection): string {
  const plural = (n: number, one: string, many = `${one}s`) =>
    `${n.toLocaleString()} ${n === 1 ? one : many}`;
  const parts = [plural(s.main.length, 'entry', 'entries')];
  if (s.steps) parts.push(plural(s.steps, 'step'));
  if (s.warnings) parts.push(plural(s.warnings, 'warning'));
  if (s.errors) parts.push(plural(s.errors, 'error'));
  return parts.join(' · ');
}

/** The run log in collapsible sections, one per stage. */
@Component({
  selector: 'app-run-log',
  imports: [DatePipe, DecimalPipe, MatButtonModule, MatIconModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (all().length > 1) {
      <div class="tools">
        <button mat-button type="button" (click)="setAll(true)">Expand all</button>
        <button mat-button type="button" (click)="setAll(false)">Collapse all</button>
      </div>
    }
    @for (s of all(); track s.key) {
      <section class="section" [class.has-error]="s.errors" [class.has-warn]="s.warnings">
        <button
          type="button"
          class="head"
          (click)="toggle(s)"
          [attr.aria-expanded]="isOpen(s)"
          [attr.aria-controls]="'log-' + s.key"
        >
          <mat-icon>{{ isOpen(s) ? 'expand_more' : 'chevron_right' }}</mat-icon>
          <span class="label">{{ s.label }}</span>
          @if (s.status; as st) {
            <span class="hop-status-chip" [class]="statusChip(st).cls">{{
              statusChip(st).label
            }}</span>
          }
          <span class="sub counts">{{ counts(s) }}</span>
          <span class="sub when"
            >{{ s.from | date: 'HH:mm:ss' }}–{{ s.to | date: 'HH:mm:ss' }} · {{ span(s) }}</span
          >
        </button>
        @if (isOpen(s)) {
          <div class="body" [id]="'log-' + s.key">
            <ol class="log">
              @for (e of shown(s); track $index) {
                <li [class]="e.level">
                  <span class="t">{{ e.at | date: 'HH:mm:ss' }}</span
                  ><span class="m">{{ e.message }}</span>
                </li>
              }
            </ol>
            @if (s.steps) {
              <div class="steps">
                <button mat-button type="button" (click)="toggleSteps(s)">
                  <mat-icon>{{ stepsOpen(s) ? 'unfold_less' : 'unfold_more' }}</mat-icon>
                  {{ stepsOpen(s) ? 'Hide' : 'Show' }} {{ s.steps | number }} step{{
                    s.steps === 1 ? '' : 's'
                  }}
                </button>
                @if (stepsOpen(s) && s.steps > maxSteps) {
                  <span class="sub"
                    >Showing the last {{ maxSteps | number }}; Copy log has them all.</span
                  >
                }
              </div>
            }
          </div>
        }
      </section>
    } @empty {
      <p class="sub">Nothing logged yet.</p>
    }
  `,
  styles: `
    :host {
      display: block;
    }
    .tools {
      display: flex;
      justify-content: flex-end;
      gap: 4px;
    }
    .section {
      border: 1px solid var(--border-light);
      border-radius: 8px;
      margin-top: 8px;
      overflow: hidden;

      &.has-warn {
        border-color: var(--color-warning-border);
      }
      &.has-error {
        border-color: var(--color-error-border);
      }
    }
    .head {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      width: 100%;
      padding: 8px 12px;
      border: 0;
      background: var(--bg-secondary);
      color: inherit;
      font: inherit;
      text-align: left;
      cursor: pointer;

      &:hover {
        background: var(--hover-overlay);
      }
    }
    .label {
      font-weight: 600;
    }
    .when {
      margin-left: auto;
    }
    .log {
      margin: 0;
      padding: 0;
      list-style: none;
      font-family: var(--font-mono);
      font-size: 0.8125rem;

      li {
        display: grid;
        grid-template-columns: 72px minmax(0, 1fr);
        gap: 12px;
        padding: 6px 12px;
        border-top: 1px solid var(--border-light);
      }
      .t {
        color: var(--text-tertiary);
      }
      .m {
        overflow-wrap: anywhere;
      }
      .detail {
        padding-top: 3px;
        padding-bottom: 3px;
        color: var(--text-secondary);
        font-size: 0.75rem;
      }
      .warn {
        background: var(--color-warning-bg);
        color: var(--color-warning-text);
      }
      .error {
        background: var(--color-error-bg);
        color: var(--color-error-text);
      }
    }
    .steps {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 4px 8px;
      border-top: 1px solid var(--border-light);
    }
  `,
})
export class RunLog {
  readonly entries = input.required<LogEntry[]>();
  readonly stages = input<Stage[]>([]);

  readonly maxSteps = MAX_STEPS;
  readonly counts = counts;
  readonly all = computed(() => sections(this.entries(), this.stages()));
  /** Sections the viewer opened or closed; the rest follow ``openByDefault``. */
  private readonly chosen = signal<Record<string, boolean>>({});
  private readonly withSteps = signal<Record<string, boolean>>({});

  /** Open when something went wrong, when the stage is running, or for the latest section. */
  openByDefault(s: LogSection): boolean {
    const sections = this.all();
    return !!s.errors || !!s.warnings || s.status === 'running' || s === sections.at(-1);
  }

  isOpen(s: LogSection): boolean {
    return this.chosen()[s.key] ?? this.openByDefault(s);
  }

  toggle(s: LogSection): void {
    this.chosen.update((c) => ({ ...c, [s.key]: !this.isOpen(s) }));
  }

  setAll(open: boolean): void {
    this.chosen.set(Object.fromEntries(this.all().map((s) => [s.key, open])));
  }

  stepsOpen(s: LogSection): boolean {
    return !!this.withSteps()[s.key];
  }

  toggleSteps(s: LogSection): void {
    this.withSteps.update((c) => ({ ...c, [s.key]: !c[s.key] }));
  }

  /** The section's entries: milestones only, or with its steps (the last MAX_STEPS of them). */
  shown(s: LogSection): LogEntry[] {
    if (!this.stepsOpen(s)) return s.main;
    if (s.steps <= MAX_STEPS) return s.all;
    let skip = s.steps - MAX_STEPS;
    return s.all.filter((e) => e.level !== 'detail' || skip-- <= 0);
  }

  statusChip(status: Stage['status']) {
    return STATUS_LABELS[status];
  }

  span(s: LogSection): string {
    return formatSeconds((Date.parse(s.to) - Date.parse(s.from)) / 1000);
  }
}
