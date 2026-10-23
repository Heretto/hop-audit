import { DecimalPipe } from '@angular/common';
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
import { RouterLink } from '@angular/router';
import { apiErrors } from '../../sites/sites.service';
import { download } from '../run-format';
import { ClaimGroup, ClaimsView } from '../run.model';
import { RunsService } from '../runs.service';
import { ClaimFilters, GROUP_STATUS, matchesClaim, NO_FILTERS, rankGroups } from './claims';

export const PAGE_SIZE = 50;

@Component({
  selector: 'app-claims-page',
  imports: [
    DecimalPipe,
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
  templateUrl: './claims-page.html',
  styleUrl: './claims-page.scss',
})
export class ClaimsPage implements OnInit {
  /** Route parameter. */
  readonly runId = input.required<string>();

  private runs = inject(RunsService);
  private snack = inject(MatSnackBar);

  readonly view = signal<ClaimsView | null>(null);
  readonly error = signal<string | null>(null);
  readonly filters = signal<ClaimFilters>(NO_FILTERS);
  readonly limit = signal(PAGE_SIZE);
  readonly status = GROUP_STATUS;

  readonly claims = computed(() => this.view()?.claims ?? []);
  readonly shown = computed(() => this.claims().filter((c) => matchesClaim(c, this.filters())));
  readonly page = computed(() => this.shown().slice(0, this.limit()));
  readonly articles = computed(() => new Set(this.claims().map((c) => c.page_id)).size);
  readonly groups = computed(() => rankGroups(this.view()?.groups ?? []));
  readonly byNumber = computed(
    () => new Map((this.view()?.groups ?? []).map((g) => [g.number, g] as const)),
  );
  readonly centerNames = computed(
    () => new Map((this.view()?.help_centers ?? []).map((c) => [c.id, c.name] as const)),
  );
  readonly matched = computed(() => this.claims().filter((c) => c.group !== null).length);

  ngOnInit(): void {
    this.runs.claims(this.runId()).subscribe({
      next: (v) => this.view.set(v),
      error: (e) => this.error.set(apiErrors(e).join(' ')),
    });
  }

  filter(change: Partial<ClaimFilters>): void {
    this.filters.update((f) => ({ ...f, ...change }));
    this.limit.set(PAGE_SIZE);
  }

  showGroup(g: ClaimGroup): void {
    this.filter({ group: this.filters().group === g.number ? '' : g.number });
  }

  exportCsv(): void {
    const run = this.view()!.run;
    this.runs.claimsCsv(run.id).subscribe({
      next: (blob) =>
        download(
          blob,
          `${run.site_name}-audit-${run.number}-claims.csv`.replace(/\s+/g, '-').toLowerCase(),
        ),
      error: (e) => this.snack.open(apiErrors(e).join(' '), 'Dismiss'),
    });
  }
}
