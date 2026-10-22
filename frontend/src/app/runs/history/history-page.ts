import { DatePipe, DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router, RouterLink } from '@angular/router';
import { HopDataTableComponent, HopTableCellDirective, HopTableColumn } from '@heretto/hop-ui';
import { SiteSummary } from '../../sites/site.model';
import { apiErrors, SitesService } from '../../sites/sites.service';
import {
  deltaClass,
  download,
  duration,
  scopeLabel,
  scoreClass,
  signed,
  statusChip,
  tokens,
} from '../run-format';
import { ACTIVE, Comparison, RunListItem } from '../run.model';
import { RunsService } from '../runs.service';
import { chartPoints, comparisonCsv, defaultPair, scoreDeltas } from './history';

@Component({
  selector: 'app-history-page',
  imports: [
    DatePipe,
    DecimalPipe,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatIconModule,
    MatSelectModule,
    MatTooltipModule,
    HopDataTableComponent,
    HopTableCellDirective,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './history-page.html',
  styleUrl: './history-page.scss',
})
export class HistoryPage implements OnInit {
  /** Query parameter: one site's runs. */
  readonly site = input<string>();

  private runs = inject(RunsService);
  private sites = inject(SitesService);
  private router = inject(Router);

  private all = signal<RunListItem[] | null>(null);
  readonly siteList = signal<SiteSummary[]>([]);
  readonly error = signal<string | null>(null);
  readonly selected = signal<string[]>([]);
  readonly comparison = signal<Comparison | null>(null);

  readonly rows = computed(() => {
    const site = this.site();
    const all = this.all();
    return all && site ? all.filter((r) => r.site_id === site) : all;
  });
  readonly siteName = computed(() => this.siteList().find((s) => s.id === this.site())?.name);
  readonly points = computed(() => (this.site() ? chartPoints(this.rows() ?? []) : []));
  readonly deltas = computed(() => scoreDeltas(this.all() ?? []));

  readonly chip = statusChip;
  readonly scopeLabel = scopeLabel;
  readonly duration = duration;
  readonly scoreClass = scoreClass;
  readonly signed = signed;
  readonly deltaClass = deltaClass;
  readonly tokens = tokens;
  readonly isActive = (r: RunListItem) => ACTIVE.includes(r.status);

  readonly columns = computed<HopTableColumn<RunListItem>[]>(() => [
    { key: 'select', label: '', sortable: false, filterable: false },
    { key: 'run', label: 'Run', value: (r) => r.number },
    ...(this.site()
      ? []
      : [{ key: 'site', label: 'Site', value: (r: RunListItem) => r.site_name }]),
    { key: 'scope', label: 'Scope', value: (r) => scopeLabel(r.scope) },
    {
      key: 'trigger',
      label: 'Trigger',
      value: (r) => (r.trigger === 'schedule' ? 'Scheduled' : 'Manual'),
    },
    { key: 'pages', label: 'Pages', align: 'end', value: (r) => r.page_count },
    {
      key: 'duration',
      label: 'Duration',
      align: 'end',
      filterable: false,
      value: (r) => duration(r),
    },
    { key: 'score', label: 'Score', align: 'end', value: (r) => r.metrics.score ?? null },
    { key: 'status', label: 'Status', value: (r) => statusChip(r).label },
    { key: 'actions', label: '', sortable: false, filterable: false },
  ]);

  constructor() {
    // A new pair of runs (or a new site) loads its comparison.
    effect(() => {
      const [a, b] = this.selected();
      if (!a || !b) {
        this.comparison.set(null);
        return;
      }
      this.runs.compare(a, b).subscribe({
        next: (c) => this.comparison.set(c),
        error: (e) => this.error.set(apiErrors(e).join(' ')),
      });
    });
    effect(() => {
      const rows = this.rows();
      if (rows) this.selected.set(defaultPair(rows) ?? []);
    });
  }

  ngOnInit(): void {
    this.sites.list().subscribe({ next: (s) => this.siteList.set(s), error: () => {} });
    this.runs.all().subscribe({
      next: (rows) => this.all.set(rows),
      error: (e) => this.error.set(apiErrors(e).join(' ')),
    });
  }

  pickSite(id: string | null): void {
    this.router.navigate(['/audits'], { queryParams: id ? { site: id } : {} });
  }

  canSelect(r: RunListItem): boolean {
    const chosen = this.all()?.find((x) => x.id === this.selected()[0]);
    return (
      r.status === 'completed' &&
      !!r.metrics.analyzed_at &&
      (!chosen || chosen.site_id === r.site_id)
    );
  }

  /** Keep two runs, earlier first; picking a third drops the oldest pick. */
  toggle(r: RunListItem): void {
    this.selected.update((ids) => {
      if (ids.includes(r.id)) return ids.filter((id) => id !== r.id);
      const picked = [...ids, r.id].slice(-2);
      const number = (id: string) => this.all()!.find((x) => x.id === id)!.number;
      return picked.sort((a, b) => number(a) - number(b));
    });
  }

  exportComparison(): void {
    const c = this.comparison()!;
    const csv = comparisonCsv(c.rows, c.a.number, c.b.number);
    download(new Blob([csv], { type: 'text/csv' }), `compare-${c.a.number}-${c.b.number}.csv`);
  }

  barHeight(score: number): number {
    return Math.max(4, score);
  }
}
