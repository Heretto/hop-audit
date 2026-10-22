import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import {
  HopAgentService,
  HopConfirmDialogComponent,
  HopConfirmDialogData,
  HopDataTableComponent,
  HopTableCellDirective,
  HopTableColumn,
} from '@heretto/hop-ui';
import { filter, switchMap } from 'rxjs';
import { duration, scopeLabel, statusChip } from '../runs/run-format';
import { ACTIVE } from '../runs/run.model';
import { SiteSummary } from './site.model';
import { apiErrors, SitesService } from './sites.service';

/** "help.heretto.com · en, de, ja · sitemap.xml" */
export function siteDetails(site: SiteSummary): string {
  const hosts = [...new Set(site.help_centers.map((hc) => new URL(hc.url).host))];
  const languages = [...new Set(site.help_centers.map((hc) => hc.language))];
  const parts = [hosts.join(', '), languages.join(', ')];
  if (site.crawl.sitemap_url)
    parts.push(new URL(site.crawl.sitemap_url).pathname.replace(/^\//, ''));
  if (site.purpose === 'prospect') parts.push('prospect review');
  return parts.filter(Boolean).join(' · ');
}

@Component({
  selector: 'app-sites-page',
  imports: [
    DatePipe,
    DecimalPipe,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatTooltipModule,
    RouterLink,
    HopDataTableComponent,
    HopTableCellDirective,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './sites-page.html',
  styleUrl: './sites-page.scss',
})
export class SitesPage implements OnInit {
  private sites = inject(SitesService);
  private agents = inject(HopAgentService);
  private dialog = inject(MatDialog);
  private snack = inject(MatSnackBar);

  readonly rows = signal<SiteSummary[] | null>(null);
  readonly error = signal<string | null>(null);
  readonly agentCount = signal<number | null>(null);
  readonly pageCount = computed(() =>
    (this.rows() ?? []).reduce((n, s) => n + (s.last_run?.page_count ?? 0), 0),
  );
  /** The most recent audit to finish in the last day, for the banner. */
  readonly justFinished = computed(() => {
    const day = Date.now() - 24 * 3600 * 1000;
    return (this.rows() ?? [])
      .filter(
        (s) => s.last_run?.status === 'completed' && Date.parse(s.last_run.finished_at ?? '') > day,
      )
      .map((s) => ({ site: s, run: s.last_run! }))
      .sort((a, b) => Date.parse(b.run.finished_at!) - Date.parse(a.run.finished_at!))[0];
  });

  readonly columns: HopTableColumn<SiteSummary>[] = [
    { key: 'name', label: 'Site', value: (s) => `${s.name} ${siteDetails(s)}` },
    {
      key: 'pages',
      label: 'Pages',
      filterable: false,
      value: (s) => s.last_run?.page_count ?? null,
    },
    {
      key: 'last',
      label: 'Last audit',
      filterable: false,
      value: (s) =>
        s.last_run ? new Date(s.last_run.started_at ?? s.last_run.created_at ?? 0) : null,
    },
    { key: 'score', label: 'Score', align: 'end', filterable: false, value: () => null },
    {
      key: 'integrity',
      label: 'Integrity issues',
      align: 'end',
      filterable: false,
      value: () => null,
    },
    { key: 'broken', label: 'Broken links', align: 'end', filterable: false, value: () => null },
    { key: 'status', label: 'Status', value: (s) => statusChip(s.last_run ?? null).label },
    { key: 'actions', label: '', sortable: false, filterable: false },
  ];
  readonly details = siteDetails;
  readonly chip = (s: SiteSummary) => statusChip(s.last_run ?? null);
  readonly scope = scopeLabel;
  readonly duration = duration;
  readonly isActive = (s: SiteSummary) => !!s.last_run && ACTIVE.includes(s.last_run.status);

  ngOnInit(): void {
    this.load();
    this.agents.listAgents().subscribe({
      next: (list) => this.agentCount.set(list.filter((a) => a.is_active).length),
      error: () => this.agentCount.set(null),
    });
  }

  load(): void {
    this.sites.list().subscribe({
      next: (rows) => {
        this.rows.set(rows);
        this.error.set(null);
      },
      error: (e) => this.error.set(apiErrors(e).join(' ')),
    });
  }

  confirmDelete(site: SiteSummary): void {
    const data: HopConfirmDialogData = {
      title: `Delete ${site.name}?`,
      message:
        'Its settings and help centers are removed. Agents and credentials are not affected.',
      confirmText: 'Delete',
    };
    this.dialog
      .open(HopConfirmDialogComponent, { data })
      .afterClosed()
      .pipe(
        filter(Boolean),
        switchMap(() => this.sites.delete(site.id)),
      )
      .subscribe({
        next: () => {
          this.rows.update((rows) => (rows ?? []).filter((s) => s.id !== site.id));
          this.snack.open(`Deleted ${site.name}`, undefined, { duration: 4000 });
        },
        error: (e) => this.snack.open(apiErrors(e).join(' '), 'Dismiss'),
      });
  }
}
