import { ChangeDetectionStrategy, Component, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar } from '@angular/material/snack-bar';
import { apiErrors } from '../../sites/sites.service';
import { Finding } from '../run.model';
import { RunsService } from '../runs.service';

export const SEVERITY_CLASS: Record<Finding['severity'], string> = {
  High: 'error',
  Medium: 'warn',
  Low: '',
};

/** One agent finding, with dismiss (the reason teaches the agent) and restore. */
@Component({
  selector: 'app-finding-card',
  imports: [FormsModule, MatButtonModule, MatFormFieldModule, MatInputModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let f = finding();
    <article class="finding" [class.dismissed]="f.dismissed">
      <div class="head">
        <span class="sev" [class]="severity[f.severity]">{{ f.severity }}</span>
        @if (f.on_focus) {
          <span class="sev focus">Site focus</span>
        }
        <h3>{{ f.title }}</h3>
        <span class="sub">{{ f.agent_name }}{{ f.model ? ' · ' + f.model : '' }}</span>
      </div>
      @if (f.target) {
        <span class="sub mono"
          >{{ f.target }} · linked from {{ f.page_count }} page{{
            f.page_count === 1 ? '' : 's'
          }}</span
        >
      }
      @if (f.body) {
        <p>{{ f.body }}</p>
      }
      @if (f.quote) {
        <blockquote class="quote">"{{ f.quote }}"</blockquote>
      }
      @if (f.suggestion) {
        <div class="suggestion"><span class="sub">Suggested</span> {{ f.suggestion }}</div>
      }
      @if (f.dismissed) {
        <div class="row">
          <span class="sub"
            >Dismissed{{ f.dismissed_reason ? ': ' + f.dismissed_reason : '' }}</span
          >
          <button mat-button (click)="save(false)" [disabled]="busy()">Restore</button>
        </div>
      } @else if (asking()) {
        <div class="dismiss">
          <mat-form-field subscriptSizing="dynamic">
            <mat-label>Why isn't this useful? {{ f.agent_name }} remembers it.</mat-label>
            <textarea matInput rows="2" [(ngModel)]="reason"></textarea>
          </mat-form-field>
          <div class="row">
            <button mat-stroked-button (click)="asking.set(false)">Cancel</button>
            <button mat-flat-button color="primary" (click)="save(true)" [disabled]="busy()">
              Dismiss
            </button>
          </div>
        </div>
      } @else {
        <div class="row"><button mat-button (click)="asking.set(true)">Not useful…</button></div>
      }
    </article>
  `,
  styles: `
    .finding {
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding: 14px 0;
      border-bottom: 1px solid var(--border-light);
    }
    .finding.dismissed {
      opacity: 0.6;
    }
    .head {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    h3 {
      margin: 0;
      font-size: 1rem;
      flex: 1 1 auto;
    }
    p {
      margin: 0;
      color: var(--text-primary);
    }
    .focus {
      background: var(--color-accent-bg);
      color: var(--color-accent-text);
    }
    .quote {
      margin: 0;
      padding: 8px 12px;
      border-left: 3px solid var(--border-strong);
      background: var(--surface-sunken);
      font-style: italic;
    }
    .suggestion {
      padding: 8px 12px;
      border-radius: 8px;
      background: var(--color-success-bg);
      color: var(--color-success-text);
    }
    .row {
      display: flex;
      gap: 8px;
      align-items: center;
      justify-content: flex-end;
    }
    .dismiss {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
  `,
})
export class FindingCard {
  readonly finding = input.required<Finding>();
  readonly changed = output<Finding>();

  private runs = inject(RunsService);
  private snack = inject(MatSnackBar);

  readonly severity = SEVERITY_CLASS;
  readonly asking = signal(false);
  readonly busy = signal(false);
  reason = '';

  save(dismissed: boolean): void {
    this.busy.set(true);
    this.runs
      .updateFinding(this.finding().id, dismissed, dismissed ? this.reason.trim() : '')
      .subscribe({
        next: (f) => {
          this.busy.set(false);
          this.asking.set(false);
          this.reason = '';
          this.changed.emit(f);
        },
        error: (e) => {
          this.busy.set(false);
          this.snack.open(apiErrors(e).join(' '), 'Dismiss');
        },
      });
  }
}
