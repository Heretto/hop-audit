import { DatePipe, DecimalPipe, JsonPipe } from '@angular/common';
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
import { MatTabsModule } from '@angular/material/tabs';
import { RouterLink } from '@angular/router';
import { apiErrors } from '../../sites/sites.service';
import { scoreClass, signed } from '../run-format';
import { Finding, LinkRow, PageDetail } from '../run.model';
import { FindingCard } from './finding-card';
import { RunsService } from '../runs.service';

export const LINK_PREVIEW = 8; // problem links shown before "All N links"

const OUTCOME_LABELS: Record<LinkRow['outcome'], { label: string; sev: string }> = {
  broken: { label: 'Broken', sev: 'error' },
  anchor: { label: 'Anchor', sev: 'warn' },
  redirect: { label: 'Redirect', sev: 'warn' },
  blocked: { label: "Couldn't check", sev: '' },
  ok: { label: 'OK', sev: 'ok' },
};
const OUTCOME_ORDER: LinkRow['outcome'][] = ['broken', 'anchor', 'redirect', 'blocked', 'ok'];

/** "Difficult", from the same bands as the dashboard. */
export function readabilityBand(flesch: number | null): { label: string; sev: string } {
  if (flesch === null) return { label: 'Not measured', sev: '' };
  if (flesch >= 60) return { label: 'Plain', sev: 'ok' };
  if (flesch >= 50) return { label: 'Fairly difficult', sev: 'warn' };
  return { label: 'Difficult', sev: 'error' };
}

@Component({
  selector: 'app-page-detail',
  imports: [
    DatePipe,
    DecimalPipe,
    JsonPipe,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatTabsModule,
    FindingCard,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './page-detail.html',
  styleUrl: './page-detail.scss',
})
export class PageDetailPage implements OnInit {
  /** Route parameters. */
  readonly runId = input.required<string>();
  readonly pageId = input.required<string>();

  private runs = inject(RunsService);

  readonly page = signal<PageDetail | null>(null);
  readonly error = signal<string | null>(null);
  readonly allLinks = signal(false);

  readonly scoreClass = scoreClass;
  readonly outcomes = OUTCOME_LABELS;
  readonly band = computed(() => readabilityBand(this.page()?.flesch ?? null));
  readonly change = computed(() => {
    const p = this.page();
    return p?.previous_score !== null && p?.score !== null && p
      ? signed(p.score - p.previous_score!)
      : null;
  });

  /** Problem links first; all links when asked. */
  readonly links = computed(() => {
    const rows = [...(this.page()?.links ?? [])].sort(
      (a, b) => OUTCOME_ORDER.indexOf(a.outcome) - OUTCOME_ORDER.indexOf(b.outcome),
    );
    return this.allLinks() ? rows : rows.filter((l) => l.outcome !== 'ok').slice(0, LINK_PREVIEW);
  });
  readonly broken = computed(
    () => this.page()?.links.filter((l) => l.outcome === 'broken').length ?? 0,
  );
  readonly seoIssues = computed(
    () => (this.page()?.seo ?? []).filter((c) => c.status !== 'ok').length,
  );
  /** Open findings, worst first; dismissed ones after. */
  readonly findings = computed(() => {
    const order = { High: 0, Medium: 1, Low: 2 };
    const all = [...(this.page()?.agent_findings ?? [])].sort(
      (a, b) => order[a.severity] - order[b.severity] || Number(b.on_focus) - Number(a.on_focus),
    );
    return { open: all.filter((f) => !f.dismissed), dismissed: all.filter((f) => f.dismissed) };
  });
  readonly meter = computed(() => Math.max(0, Math.min(100, this.page()?.flesch ?? 0)));

  ngOnInit(): void {
    this.runs.page(this.pageId()).subscribe({
      next: (p) => this.page.set(p),
      error: (e) => this.error.set(apiErrors(e).join(' ')),
    });
  }

  replace(updated: Finding): void {
    this.page.update((p) =>
      p
        ? { ...p, agent_findings: p.agent_findings.map((f) => (f.id === updated.id ? updated : f)) }
        : p,
    );
  }

  /** Path for internal targets, full URL for external ones. */
  target(link: LinkRow): string {
    if (!link.internal) return link.url;
    const u = new URL(link.url);
    return u.pathname + u.hash;
  }
}
