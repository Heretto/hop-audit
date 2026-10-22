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
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { Site } from '../../sites/site.model';
import { apiErrors, SitesService } from '../../sites/sites.service';
import { deltaClass, download, duration, scopeLabel, scoreClass, signed } from '../run-format';
import { ACTIVE, Dashboard, PageRow, RunMetrics } from '../run.model';
import { RunsService } from '../runs.service';
import { buildTree, isFiltering, TreeState } from './tree';

interface Kpi {
  icon: string;
  badge: string;
  value: string;
  label: string;
  delta: string | null;
  deltaClass: string;
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

  readonly scoreClass = scoreClass;
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
    ];
  });

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

  analyze(): void {
    this.analyzing.set(true);
    this.runs.control(this.runId(), 'analyze').subscribe({
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
