import { ChangeDetectionStrategy, Component } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-audits-page',
  imports: [MatCardModule, MatIconModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="hop-page page">
      <header class="page-header">
        <div>
          <h1>Audits</h1>
          <span class="sub"
            >Every audit run across your sites: scope, trigger, pages, duration, score and
            status.</span
          >
        </div>
      </header>
      <mat-card>
        <div class="empty-state">
          <mat-icon>fact_check</mat-icon>
          <h2>No audits yet</h2>
          <span>Run an audit from a site to see it here.</span>
        </div>
      </mat-card>
    </div>
  `,
})
export class AuditsPage {}
