import { DatePipe, NgTemplateOutlet } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { apiErrors } from '../../sites/sites.service';
import { blobErrors, download } from '../run-format';
import { ReportView } from '../run.model';
import { RunsService } from '../runs.service';

type ReportFile = 'report.pdf' | 'report.docx' | 'audit.json' | 'integrity.csv';

@Component({
  selector: 'app-report-page',
  imports: [
    DatePipe,
    NgTemplateOutlet,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatMenuModule,
    MatTooltipModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './report-page.html',
  styleUrl: './report-page.scss',
})
export class ReportPage implements OnInit {
  /** Route parameter. */
  readonly runId = input.required<string>();

  private runs = inject(RunsService);
  private snack = inject(MatSnackBar);

  readonly view = signal<ReportView | null>(null);
  readonly error = signal<string | null>(null);
  readonly exporting = signal<ReportFile | null>(null);

  /** Every audit comes here from Reports. */
  readonly back = computed(() => {
    const v = this.view();
    if (!v) return null;
    return {
      link: ['/audits', v.run.id, 'deliverables'],
      label: `${v.run.site_name} · Audit #${v.run.number} · Reports`,
    };
  });

  ngOnInit(): void {
    this.runs.report(this.runId()).subscribe({
      next: (v) => this.view.set(v),
      error: (e) => this.error.set(apiErrors(e).join(' ')),
    });
  }

  copyLink(): void {
    navigator.clipboard.writeText(window.location.href).then(
      () => this.snack.open('Link copied', undefined, { duration: 2500 }),
      () => this.snack.open("Couldn't copy the link", 'Dismiss'),
    );
  }

  export(file: ReportFile): void {
    const run = this.view()!.run;
    const request =
      file === 'integrity.csv'
        ? this.runs.integrityCsv(run.id)
        : this.runs.reportFile(run.id, file);
    const [what, ext] = file === 'integrity.csv' ? ['integrity', 'csv'] : file.split('.');
    this.exporting.set(file);
    request.subscribe({
      next: (blob) => {
        this.exporting.set(null);
        download(
          blob,
          `${run.site_name}-audit-${run.number}-${what}.${ext}`.replace(/\s+/g, '-').toLowerCase(),
        );
      },
      error: async (e) => {
        this.exporting.set(null);
        this.snack.open((await blobErrors(e)).join(' '), 'Dismiss');
      },
    });
  }
}
