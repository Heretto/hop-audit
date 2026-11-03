import { DatePipe, DecimalPipe, TitleCasePipe } from '@angular/common';
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
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatDialog } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router, RouterLink } from '@angular/router';
import { HopConfirmDialogComponent, HopConfirmDialogData } from '@heretto/hop-ui';
import { forkJoin } from 'rxjs';
import { Site } from '../../sites/site.model';
import { apiErrors, SitesService } from '../../sites/sites.service';
import {
  deltaClass,
  download,
  duration,
  scopeLabel,
  scoreClass,
  signed,
  tokens,
} from '../run-format';
import {
  ACTIVE,
  CATEGORY_NAMES,
  Dashboard,
  IntegrityMetrics,
  PageRow,
  RunMetrics,
  Severity,
} from '../run.model';
import { RunsService } from '../runs.service';
import { buildTree, findingsLabel, isFiltering, TreeState } from './tree';

interface Kpi {
  icon: string;
  badge: string;
  value: string;
  label: string;
  delta: string | null;
  deltaClass: string;
  link?: boolean; // opens Findings and triage
}

export const CATEGORY_CARDS = 5;
const CATALOG = Object.keys(CATEGORY_NAMES); // ties keep the catalog's order

/** The dashboard's category cards, largest first. Past five, the smallest
 *  categories share the last card ("Outdated content, structure and …"). */
/** A category's bar: its firm findings, split by severity where the audit recorded it. */
export interface CategoryCard {
  code: string;
  label: string;
  n: number;
  high: number;
  medium: number;
  low: number;
}

export function categoryCards(
  counts: Record<string, number>,
  severities: Record<string, Partial<Record<Severity, number>>> = {},
): CategoryCard[] {
  const rows = Object.entries(counts)
    .filter(([, n]) => n > 0)
    .map(([code, n]) => ({
      code,
      label: CATEGORY_NAMES[code] ?? code,
      n,
      high: severities[code]?.High ?? 0,
      medium: severities[code]?.Medium ?? 0,
      low: severities[code]?.Low ?? 0,
    }))
    .sort((a, b) => b.n - a.n || CATALOG.indexOf(a.code) - CATALOG.indexOf(b.code));
  if (rows.length <= CATEGORY_CARDS) return rows;
  const rest = rows.slice(CATEGORY_CARDS - 1);
  const sum = (key: 'n' | 'high' | 'medium' | 'low') =>
    rest.reduce((total, r) => total + r[key], 0);
  return [
    ...rows.slice(0, CATEGORY_CARDS - 1),
    {
      code: rest.map((r) => r.code).join(' '),
      label: rest.map((r, i) => (i ? r.label.toLowerCase() : r.label)).join(', '),
      n: sum('n'),
      high: sum('high'),
      medium: sum('medium'),
      low: sum('low'),
    },
  ];
}

@Component({
  selector: 'app-dashboard-page',
  imports: [
    DatePipe,
    DecimalPipe,
    TitleCasePipe,
    FormsModule,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard-page.html',
  styleUrl: './dashboard-page.scss',
})
export class DashboardPage implements OnInit {
  /** Route parameter. */
  readonly runId = input.required<string>();

  private runs = inject(RunsService);
  private sites = inject(SitesService);
  private router = inject(Router);
  private snack = inject(MatSnackBar);
  private dialog = inject(MatDialog);

  readonly data = signal<Dashboard | null>(null);
  readonly pages = signal<PageRow[]>([]);
  readonly site = signal<Site | null>(null);
  readonly error = signal<string | null>(null);
  readonly analyzing = signal(false);

  readonly state = signal<TreeState>({
    query: '',
    show: 'all',
    sort: 'path',
    open: new Set(),
    closed: new Set(),
    expanded: new Set(),
  });
  readonly tree = computed(() =>
    buildTree(this.data()?.sections ?? [], this.pages(), this.state()),
  );
  readonly filtering = computed(() => isFiltering(this.state()));
  readonly matchCount = computed(() =>
    this.tree().reduce((n, r) => n + (r.kind === 'section' ? r.matching : 0), 0),
  );

  /** Labels of analyses whose agent review failed on this run. */
  readonly failedStages = computed(() =>
    (this.data()?.run.stages ?? []).filter((s) => s.status === 'failed').map((s) => s.label),
  );
  readonly scoreClass = scoreClass;
  readonly findingsLabel = findingsLabel;
  readonly tokens = tokens;
  readonly duration = duration;
  readonly scopeLabel = scopeLabel;

  /** Language tags beside page titles, when the site has more than one help center. */
  readonly languages = computed(() => {
    const centers = this.site()?.help_centers ?? [];
    return centers.length > 1
      ? new Map(centers.map((hc) => [hc.id!, hc.language]))
      : new Map<string, string>();
  });

  readonly kpis = computed<Kpi[]>(() => {
    const d = this.data();
    if (!d) return [];
    const m = d.run.metrics as Partial<RunMetrics>;
    const before = (d.compared?.metrics ?? {}) as Partial<RunMetrics>;
    const n = d.compared?.number;
    const change = (key: keyof RunMetrics, better: 'up' | 'down', digits = 0) => {
      const a = before[key] as number | null | undefined;
      const b = m[key] as number | null | undefined;
      const delta = a !== null && a !== undefined && b !== null && b !== undefined ? b - a : null;
      const text = signed(delta, digits);
      return {
        delta: text && n ? `${text} vs #${n}` : null,
        deltaClass: deltaClass(delta, better),
      };
    };
    const fmt = (v: number | null | undefined, digits = 0) =>
      v === null || v === undefined
        ? '—'
        : v.toLocaleString('en-US', {
            maximumFractionDigits: digits,
            minimumFractionDigits: digits,
          });
    return [
      {
        icon: 'verified',
        badge: '',
        value: fmt(m.score),
        label: 'Site score',
        ...change('score', 'up'),
      },
      {
        icon: 'article',
        badge: 'accent',
        value: fmt(m.pages),
        label: 'Pages analyzed',
        delta: m.new_pages ? `+${m.new_pages} new` : null,
        deltaClass: 'flat',
      },
      {
        icon: 'menu_book',
        badge: 'success',
        value: fmt(m.flesch, 1),
        label: 'Avg Flesch Reading Ease',
        ...change('flesch', 'up', 1),
      },
      {
        icon: 'link_off',
        badge: 'error',
        value: fmt(m.broken),
        label: 'Broken links',
        ...change('broken', 'down'),
      },
      {
        icon: 'travel_explore',
        badge: 'warning',
        value: fmt(m.seo_issues),
        label: 'SEO issues',
        ...change('seo_issues', 'down'),
      },
      this.integrityKpi(),
    ];
  });

  /** Integrity counts: only once triage is confirmed. */
  readonly integrity = computed(
    () => (this.data()?.run.metrics.integrity ?? null) as IntegrityMetrics | null,
  );
  readonly categoryRows = computed(() =>
    categoryCards(
      this.integrity()?.by_category ?? {},
      this.integrity()?.severity_by_category ?? {},
    ),
  );
  readonly maxCategory = computed(() => Math.max(1, ...this.categoryRows().map((r) => r.n)));

  /** Category cards and severity line: confirmed counts, or the reviewer's proposal before triage. */
  readonly showCards = computed(() => (this.integrity()?.firm ?? 0) > 0);

  private integrityKpi(): Kpi & { link?: boolean } {
    const i = this.integrity();
    const before = (this.data()?.compared?.metrics.integrity ?? null) as IntegrityMetrics | null;
    if (!i?.candidates) {
      return {
        icon: 'rule',
        badge: '',
        value: '—',
        label: 'Confirmed integrity issues',
        delta: null,
        deltaClass: 'flat',
      };
    }
    if (!i.confirmed) {
      const delta = `${i.candidates} candidates to triage`;
      return {
        icon: 'rule',
        badge: '',
        value: '—',
        label: 'Confirmed integrity issues',
        delta,
        deltaClass: 'flat',
        link: true,
      };
    }
    const vs = before?.confirmed
      ? ` · ${signed(i.firm - before.firm)} vs #${this.data()!.compared!.number}`
      : '';
    return {
      icon: 'rule',
      badge: '',
      value: `${i.firm}`,
      label: 'Confirmed integrity issues',
      delta: `${i.high} High${vs}`,
      deltaClass: before?.confirmed ? deltaClass(i.firm - before.firm, 'down') : 'flat',
      link: true,
    };
  }

  ngOnInit(): void {
    const id = this.runId();
    forkJoin([this.runs.dashboard(id), this.runs.pages(id)]).subscribe({
      next: ([dashboard, pages]) => {
        if (ACTIVE.includes(dashboard.run.status)) {
          this.router.navigate(['/audits', id, 'progress'], { replaceUrl: true });
          return;
        }
        this.data.set(dashboard);
        this.pages.set(pages);
        this.sites
          .get(dashboard.run.site_id)
          .subscribe({ next: (s) => this.site.set(s), error: () => {} });
      },
      error: (e) => this.error.set(apiErrors(e).join(' ')),
    });
  }

  update(change: Partial<TreeState>): void {
    this.state.update((s) => ({ ...s, ...change }));
  }

  toggle(path: string, open: boolean): void {
    this.state.update((s) => {
      const opened = new Set(s.open);
      const closed = new Set(s.closed);
      if (open) {
        opened.delete(path);
        closed.add(path);
      } else {
        opened.add(path);
        closed.delete(path);
      }
      return { ...s, open: opened, closed };
    });
  }

  expandAll(open: boolean): void {
    const paths = (this.data()?.sections ?? []).map((s) => s.path);
    this.update(
      open
        ? { open: new Set(paths), closed: new Set() }
        : { open: new Set(), closed: new Set(paths) },
    );
  }

  showAll(path: string): void {
    this.state.update((s) => ({ ...s, expanded: new Set([...s.expanded, path]) }));
  }

  /** Re-evaluate every page, unchanged ones too, after a confirmation (it costs model tokens). */
  reevaluate(): void {
    const data: HopConfirmDialogData = {
      title: 'Re-evaluate every page?',
      message:
        "Readability and SEO are evaluated again, and the agents asked again, even for pages whose checksum hasn't " +
        'changed since the last audit. This uses model tokens. Nothing is crawled again.',
      confirmText: 'Re-evaluate',
    };
    this.dialog
      .open(HopConfirmDialogComponent, { data })
      .afterClosed()
      .subscribe((ok) => ok && this.analyze(true));
  }

  analyze(force = false): void {
    this.analyzing.set(true);
    this.runs.analyze(this.runId(), force).subscribe({
      next: () => this.router.navigate(['/audits', this.runId(), 'progress']),
      error: (e) => {
        this.analyzing.set(false);
        this.snack.open(apiErrors(e).join(' '), 'Dismiss');
      },
    });
  }

  exportCsv(): void {
    const run = this.data()!.run;
    this.runs.pagesCsv(run.id).subscribe({
      next: (blob) =>
        download(
          blob,
          `${run.site_name}-audit-${run.number}-pages.csv`.replace(/\s+/g, '-').toLowerCase(),
        ),
      error: (e) => this.snack.open(apiErrors(e).join(' '), 'Dismiss'),
    });
  }
}
