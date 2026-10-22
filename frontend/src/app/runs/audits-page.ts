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
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { HopDataTableComponent, HopTableCellDirective, HopTableColumn } from '@heretto/hop-ui';
import { apiErrors } from '../sites/sites.service';
import { duration, scopeLabel, statusChip } from './run-format';
import { RunListItem } from './run.model';
import { RunsService } from './runs.service';

/** Every run across the organization's sites; ?site= narrows it to one. */
@Component({
  selector: 'app-audits-page',
  imports: [
    DatePipe,
    DecimalPipe,
    RouterLink,
    MatCardModule,
    MatIconModule,
    HopDataTableComponent,
    HopTableCellDirective,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="hop-page page">
      <header class="page-header">
        <div>
          <h1>Audits</h1>
          <span class="sub"
            >Every audit run{{ siteName() ? ' of ' + siteName() : ' across your sites' }}: scope,
            trigger, pages, duration and status.</span
          >
        </div>
        @if (site()) {
          <a routerLink="/audits">Show all sites</a>
        }
      </header>
      @if (error(); as message) {
        <div class="hop-status-message error" role="alert">{{ message }}</div>
      }
      @if (rows(); as runs) {
        @if (runs.length) {
          <mat-card>
            <hop-data-table
              [columns]="columns"
              [data]="runs"
              [filterable]="true"
              filterPlaceholder="Filter audits"
            >
              <ng-template hopCell="audit" let-r>
                <div class="cell">
                  <a [routerLink]="['/audits', r.id]">#{{ r.number }} · {{ r.site_name }}</a>
                  <span class="sub">{{ r.created_by ?? 'schedule' }}</span>
                </div>
              </ng-template>
              <ng-template hopCell="started" let-r>{{
                r.started_at ?? r.created_at | date: 'MMM d, y HH:mm'
              }}</ng-template>
              <ng-template hopCell="pages" let-r>{{ r.page_count | number }}</ng-template>
              <ng-template hopCell="status" let-r>
                <span class="hop-status-chip" [class]="chip(r).cls">{{ chip(r).label }}</span>
              </ng-template>
            </hop-data-table>
          </mat-card>
        } @else {
          <mat-card>
            <div class="empty-state">
              <mat-icon>fact_check</mat-icon>
              <h2>No audits yet</h2>
              <span>Run an audit from a site to see it here.</span>
            </div>
          </mat-card>
        }
      }
    </div>
  `,
  styles: '.cell { display: flex; flex-direction: column; gap: 2px; }',
})
export class AuditsPage implements OnInit {
  /** Query parameter: one site's runs. */
  readonly site = input<string>();

  private runs = inject(RunsService);
  private all = signal<RunListItem[] | null>(null);
  readonly error = signal<string | null>(null);

  readonly rows = computed(() => {
    const site = this.site();
    const all = this.all();
    return all && site ? all.filter((r) => r.site_id === site) : all;
  });
  readonly siteName = computed(() => (this.site() ? this.rows()?.[0]?.site_name : undefined));
  readonly chip = statusChip;

  readonly columns: HopTableColumn<RunListItem>[] = [
    {
      key: 'audit',
      label: 'Audit',
      value: (r) => `#${r.number} ${r.site_name} ${r.created_by ?? ''}`,
    },
    { key: 'scope', label: 'Scope', value: (r) => scopeLabel(r.scope) },
    {
      key: 'trigger',
      label: 'Trigger',
      value: (r) => (r.trigger === 'schedule' ? 'Schedule' : 'Manual'),
    },
    { key: 'pages', label: 'Pages', align: 'end', value: (r) => r.page_count },
    { key: 'started', label: 'Started', value: (r) => new Date(r.started_at ?? r.created_at ?? 0) },
    { key: 'duration', label: 'Duration', filterable: false, value: (r) => duration(r) },
    { key: 'status', label: 'Status', value: (r) => statusChip(r).label },
  ];

  ngOnInit(): void {
    this.runs.all().subscribe({
      next: (rows) => this.all.set(rows),
      error: (e) => this.error.set(apiErrors(e).join(' ')),
    });
  }
}
