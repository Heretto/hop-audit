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
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar } from '@angular/material/snack-bar';
import { RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { apiErrors } from '../../sites/sites.service';
import { blobErrors, download } from '../run-format';
import { RunDetail, SheetKind } from '../run.model';
import { RunsService } from '../runs.service';
import { PAGE_H, SheetFrame } from './sheet-frame';

export const SHEETS: Record<SheetKind, { title: string; file: string }> = {
  lead: { title: 'Lead one-sheet', file: 'content-integrity-snapshot' },
  exec: { title: 'Executive brief', file: 'executive-brief' },
};

/** A one-sheet at full size, as the PDF will print it, with its measured height. */
@Component({
  selector: 'app-sheet-page',
  imports: [RouterLink, MatButtonModule, MatIconModule, SheetFrame],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="hop-page page">
      @if (run(); as r) {
        <a class="back" [routerLink]="['/audits', r.id, 'deliverables']">
          <mat-icon>arrow_back</mat-icon>{{ r.site_name }} · Audit #{{ r.number }} · Deliverables
        </a>
        <header class="page-header">
          <div>
            <h1>{{ sheet().title }}</h1>
            <span class="sub" [class.over]="overflow() > 0">
              @if (height(); as h) {
                @if (overflow() > 0) {
                  A page overflows Letter by {{ overflow() }} px: shorten the copy on Deliverables.
                } @else {
                  Every page fits on Letter (tallest {{ h }} px of {{ pageHeight }}).
                }
              } @else {
                Measuring…
              }
            </span>
          </div>
          <div class="page-actions">
            <button mat-flat-button color="primary" (click)="pdf()" [disabled]="busy()">
              <mat-icon>picture_as_pdf</mat-icon>PDF
            </button>
          </div>
        </header>
        @if (html(); as h) {
          <app-sheet-frame
            class="sheet"
            [html]="h"
            [label]="sheet().title"
            (measured)="height.set($event)"
          />
        }
      } @else if (error(); as message) {
        <div class="hop-status-message error" role="alert">{{ message }}</div>
      }
    </div>
  `,
  styles: `
    @use '../../shared/form-layout';
    .sheet {
      max-width: 816px;
      width: 100%;
    }
    .over {
      color: var(--color-error-text);
    }
  `,
})
export class SheetPage implements OnInit {
  /** Route parameters. */
  readonly runId = input.required<string>();
  readonly kind = input.required<SheetKind>();

  private runs = inject(RunsService);
  private snack = inject(MatSnackBar);

  readonly run = signal<RunDetail | null>(null);
  readonly html = signal<string | null>(null);
  readonly height = signal<number | null>(null);
  readonly error = signal<string | null>(null);
  readonly busy = signal(false);
  readonly pageHeight = PAGE_H;

  readonly sheet = computed(() => SHEETS[this.kind()] ?? SHEETS.lead);
  readonly overflow = computed(() => (this.height() ?? 0) - PAGE_H);

  ngOnInit(): void {
    forkJoin({
      view: this.runs.deliverables(this.runId()),
      html: this.runs.sheetHtml(this.runId(), this.kind()),
    }).subscribe({
      next: ({ view, html }) => {
        this.run.set(view.run);
        this.html.set(html);
      },
      error: (e) => this.error.set(apiErrors(e).join(' ')),
    });
  }

  pdf(): void {
    const r = this.run()!;
    this.busy.set(true);
    this.runs.sheetPdf(r.id, this.kind()).subscribe({
      next: (blob) => {
        this.busy.set(false);
        const name = `${r.site_name}-audit-${r.number}-${this.sheet().file}.pdf`;
        download(blob, name.replace(/\s+/g, '-').toLowerCase());
      },
      error: async (e) => {
        this.busy.set(false);
        this.snack.open((await blobErrors(e)).join(' '), 'Dismiss');
      },
    });
  }
}
