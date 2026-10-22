import { ChangeDetectionStrategy, Component } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-sites-page',
  imports: [MatButtonModule, MatCardModule, MatIconModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="hop-page page">
      <header class="page-header">
        <div>
          <h1>Sites</h1>
          <span class="sub">
            Documentation websites and help centers this organization audits. Each audit crawls
            every language version, runs the analysis agents (readability, links, SEO, content
            integrity) and keeps a report.
          </span>
        </div>
        <button mat-flat-button color="primary" disabled><mat-icon>add</mat-icon>Add site</button>
      </header>
      <mat-card>
        <div class="empty-state">
          <mat-icon>language</mat-icon>
          <h2>No sites yet</h2>
          <span>Add a documentation site or help center to audit it.</span>
        </div>
      </mat-card>
    </div>
  `,
})
export class SitesPage {}
