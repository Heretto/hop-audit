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
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { Router, RouterLink } from '@angular/router';
import { AgentSummary, HopAgentService } from '@heretto/hop-ui';
import { forkJoin } from 'rxjs';
import {
  ANALYSES,
  ANALYSIS_KEYS,
  AnalysisKey,
  CATEGORIES,
  languageName,
  Site,
} from '../../sites/site.model';
import { apiErrors, SitesService } from '../../sites/sites.service';
import { estimate, scopeLabel, tokens } from '../run-format';
import { Preview, RunListItem, RunScope, ScopeMode } from '../run.model';
import { RunsService } from '../runs.service';

/** Page URLs or paths typed one per line. */
export function listedPages(text: string): string[] {
  return [
    ...new Set(
      text
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean),
    ),
  ];
}

@Component({
  selector: 'app-run-audit',
  imports: [
    DatePipe,
    DecimalPipe,
    FormsModule,
    RouterLink,
    MatButtonModule,
    MatButtonToggleModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSlideToggleModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './run-audit.html',
  styleUrl: './run-audit.scss',
})
export class RunAudit implements OnInit {
  /** Route parameter. */
  readonly id = input.required<string>();

  private sites = inject(SitesService);
  private runs = inject(RunsService);
  private agentService = inject(HopAgentService);
  private router = inject(Router);

  readonly site = signal<Site | null>(null);
  readonly preview = signal<Preview | null>(null);
  readonly recent = signal<RunListItem[]>([]);
  readonly agents = signal<AgentSummary[]>([]);
  readonly errors = signal<string[]>([]);
  readonly starting = signal(false);

  readonly mode = signal<ScopeMode>('site');
  readonly sections = signal<Set<string>>(new Set());
  readonly pagesText = signal('');
  readonly analyses = signal<Set<AnalysisKey>>(new Set());
  readonly helpCenters = signal<Set<string>>(new Set());
  reuse = true;
  recheckExternal = false;
  forceReevaluate = false;
  focus = '';

  readonly languageName = languageName;
  readonly categoryCount = CATEGORIES.length;

  /** The site's analyses, in the settings screen's order. */
  readonly siteAnalyses = computed(() =>
    ANALYSES.filter((a) => this.site()?.analyses.includes(a.key)),
  );

  readonly pageCount = computed(() => {
    const p = this.preview();
    if (!p) return 0;
    switch (this.mode()) {
      case 'sections':
        return p.sections
          .filter((s) => this.sections().has(s.path))
          .reduce((n, s) => n + s.count, 0);
      case 'changed':
        return p.changed;
      case 'pages':
        return listedPages(this.pagesText()).length;
      default:
        return p.site_pages;
    }
  });

  readonly scope = computed<RunScope>(() => ({
    mode: this.mode(),
    sections: this.mode() === 'sections' ? [...this.sections()] : [],
    pages: this.mode() === 'pages' ? listedPages(this.pagesText()) : [],
  }));

  readonly scopeText = computed(() => {
    const p = this.preview();
    if (this.mode() === 'sections' && p) {
      const n = this.sections().size;
      return n ? `${n} of ${p.sections.length} sections` : 'No sections chosen';
    }
    return scopeLabel(this.scope());
  });

  readonly duration = computed(() =>
    estimate(this.pageCount() * (this.preview()?.seconds_per_page ?? 0)),
  );
  readonly tokenText = computed(() => {
    const share = [...this.analyses()].filter((a) => a !== 'links').length / 4;
    return tokens(this.pageCount() * (this.preview()?.tokens_per_page ?? 0) * share);
  });

  /** Distinct agents behind the chosen analyses. */
  readonly agentCount = computed(() => {
    const assigned = this.site()?.agent_assignments ?? {};
    const byAgent = [...this.analyses()].filter((a) => a !== 'links').map((a) => assigned[a]);
    return new Set(byAgent.filter(Boolean)).size;
  });

  readonly canStart = computed(
    () =>
      !!this.preview() &&
      !this.starting() &&
      this.analyses().size > 0 &&
      this.pageCount() > 0 &&
      (!this.analyses().has('content_integrity') || this.helpCenters().size > 0),
  );

  readonly primary = computed(() => this.preview()?.help_centers.find((h) => h.is_primary));

  ngOnInit(): void {
    const id = this.id();
    this.agentService.listAgents().subscribe({ next: (a) => this.agents.set(a), error: () => {} });
    this.runs
      .forSite(id)
      .subscribe({ next: (r) => this.recent.set(r.slice(0, 4)), error: () => {} });
    forkJoin([this.sites.get(id), this.runs.preview(id)]).subscribe({
      next: ([site, preview]) => {
        this.site.set(site);
        this.preview.set(preview);
        this.analyses.set(
          new Set(site.analyses.filter((a): a is AnalysisKey => ANALYSIS_KEYS.includes(a))),
        );
        this.helpCenters.set(
          new Set(preview.help_centers.filter((h) => !h.blocked).map((h) => h.id)),
        );
        this.reuse = preview.last_run_number !== null;
      },
      error: (e) => this.errors.set(apiErrors(e)),
    });
  }

  agentName(analysis: AnalysisKey): string {
    if (analysis === 'links') return 'checked by HOP Audit';
    const id = this.site()?.agent_assignments[analysis];
    return this.agents().find((a) => a.id === id)?.name ?? 'no agent assigned';
  }

  toggle<T>(set: ReturnType<typeof signal<Set<T>>>, value: T): void {
    set.update((s) => {
      const next = new Set(s);
      next.has(value) ? next.delete(value) : next.add(value);
      return next;
    });
  }

  selectAll(on: boolean): void {
    this.sections.set(new Set(on ? this.preview()!.sections.map((s) => s.path) : []));
  }

  start(): void {
    this.starting.set(true);
    this.errors.set([]);
    this.runs
      .start(this.id(), {
        scope: this.scope(),
        analyses: ANALYSIS_KEYS.filter((a) => this.analyses().has(a)),
        help_center_ids: [...this.helpCenters()],
        reuse_crawl: this.reuse,
        recheck_external: this.recheckExternal,
        force_reevaluate: this.forceReevaluate,
        focus: this.focus.trim(),
      })
      .subscribe({
        next: (run) => this.router.navigate(['/audits', run.id]),
        error: (e) => {
          this.starting.set(false);
          this.errors.set(apiErrors(e));
        },
      });
  }
}
