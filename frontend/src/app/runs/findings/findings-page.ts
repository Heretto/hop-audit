import { DatePipe, DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { CATEGORIES } from '../../sites/site.model';
import { apiErrors } from '../../sites/sites.service';
import { download } from '../run-format';
import { CATEGORY_NAMES, IntegrityRow, IntegrityView, Tier } from '../run.model';
import { RunsService } from '../runs.service';
import { exampleHint, examples, Filters, matches, recount } from './triage';

export const PAGE_SIZE = 25;
const TRIAGE_CHIPS = {
  pending: { cls: 'hop-status-chip-pending', label: 'Not triaged yet' },
  in_progress: { cls: 'hop-status-chip-running', label: 'Triage in progress' },
  confirmed: { cls: 'hop-status-chip-completed', label: 'Triage confirmed' },
};

@Component({
  selector: 'app-findings-page',
  imports: [
    DatePipe,
    DecimalPipe,
    FormsModule,
    RouterLink,
    MatButtonModule,
    MatButtonToggleModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    MatTooltipModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './findings-page.html',
  styleUrl: './findings-page.scss',
})
export class FindingsPage implements OnInit {
  /** Route parameter. */
  readonly runId = input.required<string>();

  private runs = inject(RunsService);
  private snack = inject(MatSnackBar);

  readonly view = signal<IntegrityView | null>(null);
  readonly error = signal<string | null>(null);
  readonly filters = signal<Filters>({ query: '', category: '', tier: '', severity: '' });
  readonly limit = signal(PAGE_SIZE);
  readonly editing = signal<string | null>(null); // finding whose note is being edited
  readonly confirming = signal(false);

  readonly categories = CATEGORIES;
  readonly names = CATEGORY_NAMES;
  readonly chips = TRIAGE_CHIPS;

  readonly findings = computed(() => this.view()?.findings ?? []);
  /** The integrity stage, when it failed: no answer isn't a clean result. */
  readonly failure = computed(() => {
    const stage = this.view()?.run.stages.find((s) => s.key === 'content_integrity');
    return stage?.status === 'failed' ? stage.detail : null;
  });
  readonly shown = computed(() => this.findings().filter((f) => matches(f, this.filters())));
  readonly page = computed(() => this.shown().slice(0, this.limit()));
  readonly counts = computed(() => recount(this.findings()));
  readonly picked = computed(() => examples(this.findings()));
  readonly hint = computed(() => exampleHint(this.picked().length));
  readonly maxCategory = computed(() => Math.max(1, ...this.counts().categories.map((c) => c.n)));
  readonly articles = computed(() =>
    (this.view()?.help_centers ?? []).reduce((n, c) => n + c.articles, 0),
  );

  ngOnInit(): void {
    this.runs.integrity(this.runId()).subscribe({
      next: (v) => this.view.set(v),
      error: (e) => this.error.set(apiErrors(e).join(' ')),
    });
  }

  filter(change: Partial<Filters>): void {
    this.filters.update((f) => ({ ...f, ...change }));
    this.limit.set(PAGE_SIZE);
  }

  pct(n: number): number {
    return Math.round((100 * n) / Math.max(1, this.counts().firm));
  }

  setTier(f: IntegrityRow, tier: Tier): void {
    this.save(f, { tier }, { ...f, tier, example_rank: tier === 'firm' ? f.example_rank : null });
  }

  toggleExample(f: IntegrityRow): void {
    const on = f.example_rank === null;
    this.save(f, { example: on }, { ...f, example_rank: on ? 999 : null });
  }

  saveNote(f: IntegrityRow, note: string): void {
    this.editing.set(null);
    if (note.trim() !== f.triage_note)
      this.save(f, { triage_note: note }, { ...f, triage_note: note.trim() });
  }

  /** Show the change at once (the recount updates), then keep the server's answer. */
  private save(
    before: IntegrityRow,
    change: { tier?: Tier; triage_note?: string; example?: boolean },
    optimistic: IntegrityRow,
  ): void {
    this.replace(optimistic, true);
    this.runs.updateIntegrity(before.id, change).subscribe({
      next: (saved) => this.replace(saved, true),
      error: (e) => {
        this.replace(before, false);
        this.snack.open(apiErrors(e).join(' '), 'Dismiss');
      },
    });
  }

  private replace(row: IntegrityRow, reopen: boolean): void {
    this.view.update((v) =>
      v
        ? {
            ...v,
            findings: v.findings.map((f) => (f.id === row.id ? row : f)),
            triage: reopen ? { status: 'in_progress' } : v.triage,
          }
        : v,
    );
  }

  confirm(): void {
    this.confirming.set(true);
    this.runs.confirmTriage(this.runId()).subscribe({
      next: (v) => {
        this.view.set(v);
        this.confirming.set(false);
        this.snack.open(
          `Triage confirmed: ${recount(v.findings).firm} issues count. ${v.findings[0]?.agent_name ?? 'The reviewer'} learns from your calls.`,
          undefined,
          { duration: 5000 },
        );
      },
      error: (e) => {
        this.confirming.set(false);
        this.snack.open(apiErrors(e).join(' '), 'Dismiss');
      },
    });
  }

  exportCsv(): void {
    const run = this.view()!.run;
    this.runs.integrityCsv(run.id).subscribe({
      next: (blob) =>
        download(
          blob,
          `${run.site_name}-audit-${run.number}-integrity.csv`.replace(/\s+/g, '-').toLowerCase(),
        ),
      error: (e) => this.snack.open(apiErrors(e).join(' '), 'Dismiss'),
    });
  }
}
