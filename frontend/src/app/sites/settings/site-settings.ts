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
import { ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router, RouterLink } from '@angular/router';
import { AgentSummary, AiConfiguration, HopAgentService } from '@heretto/hop-ui';
import { MONTHDAY_OPTIONS, nextRun, WEEKDAY_OPTIONS } from '../schedule';
import {
  ANALYSES,
  ASSIGNMENTS,
  CATEGORIES,
  Discovery,
  LANGUAGES,
  languageName,
  nativeLanguageName,
  Prospect,
  SiteInput,
} from '../site.model';
import { apiErrors, SitesService } from '../sites.service';
import { helpCenterGroup, httpUrl, SiteForm, siteForm, toSiteInput } from './site-form';

/** Providers HOP Audit can call for embeddings (Anthropic has no embeddings API). */
const EMBEDDERS = ['openai', 'gemini'];

const NO_PROSPECT: Prospect = {
  company: '',
  prepared_for: '',
  sender_name: '',
  sender_title: '',
  sender_email: '',
};

@Component({
  selector: 'app-site-settings',
  imports: [
    DatePipe,
    DecimalPipe,
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSlideToggleModule,
    MatTooltipModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './site-settings.html',
  styleUrl: './site-settings.scss',
})
export class SiteSettings implements OnInit {
  /** Route parameter; absent on /sites/new. */
  readonly id = input<string>();

  private sites = inject(SitesService);
  private agentService = inject(HopAgentService);
  private router = inject(Router);
  private snack = inject(MatSnackBar);

  readonly form = signal<SiteForm | null>(null);
  readonly title = signal('New site');
  readonly agents = signal<AgentSummary[]>([]);
  /** OpenAI and Gemini configurations, which can embed statements for content integrity. */
  readonly embedders = signal<AiConfiguration[]>([]);
  readonly discovery = signal<Discovery | null>(null);
  readonly detecting = signal(false);
  readonly saving = signal(false);
  readonly errors = signal<string[]>([]);
  readonly scheduleText = signal<string | null>(null);
  private prospect: Prospect = NO_PROSPECT;
  /** Bumped on help-center edits so computeds that read the FormArray refresh. */
  private centersVersion = signal(0);

  readonly analyses = ANALYSES;
  readonly assignments = ASSIGNMENTS;
  readonly categories = CATEGORIES;
  readonly weekdays = WEEKDAY_OPTIONS;
  readonly monthdays = MONTHDAY_OPTIONS;
  readonly languageName = languageName;

  /** hreflang alternates on the start URL that aren't help centers yet. */
  readonly missingAlternates = computed(() => {
    this.centersVersion();
    const known = new Set(this.centerUrls());
    return (this.discovery()?.alternates ?? []).filter((a) => !known.has(a.url.replace(/\/$/, '')));
  });

  readonly languageOptions = computed(() => {
    this.centersVersion();
    const used =
      this.form()?.controls.help_centers.controls.map((g) => g.controls.language.value) ?? [];
    const detected = this.discovery()?.alternates.map((a) => a.language) ?? [];
    return [...new Set([...LANGUAGES, ...detected, ...used])];
  });

  ngOnInit(): void {
    this.agentService
      .listAgents()
      .subscribe({ next: (a) => this.agents.set(a), error: () => this.agents.set([]) });
    this.agentService.listAiConfigurations().subscribe({
      next: (configs) => this.embedders.set(configs.filter((c) => EMBEDDERS.includes(c.provider))),
      error: () => this.embedders.set([]),
    });
    const id = this.id();
    const load = id ? this.sites.get(id) : this.sites.defaults();
    load.subscribe({
      next: (site) => this.init(site, !!id),
      error: (e) => this.errors.set(apiErrors(e)),
    });
  }

  private init(site: SiteInput, existing: boolean): void {
    const form = siteForm(site);
    if (!form.controls.help_centers.length) form.controls.help_centers.push(helpCenterGroup());
    this.prospect = site.prospect ?? NO_PROSPECT;
    if (existing) this.title.set(site.name);
    const schedule = form.controls.schedule;
    schedule.controls.frequency.valueChanges.subscribe((f) => {
      const day = schedule.controls.day;
      if ((f === 'weekly' && day.value > 6) || (f === 'monthly' && day.value < 1)) day.setValue(1);
    });
    schedule.valueChanges.subscribe(() => this.scheduleText.set(nextRun(schedule.getRawValue())));
    this.scheduleText.set(nextRun(schedule.getRawValue()));
    this.form.set(form);
    if (existing) this.detect();
  }

  private centerUrls(): string[] {
    return (this.form()?.controls.help_centers.controls ?? []).map((g) =>
      g.controls.url.value.trim().replace(/\/$/, ''),
    );
  }

  agentLabel(agent: AgentSummary): string {
    const model = agent.ai_configuration?.model;
    return `${agent.name} · ${model ?? 'no AI configuration'}`;
  }

  // ── Help centers ──────────────────────────────────────────────────────────

  addHelpCenter(name = '', url = '', language = 'en'): void {
    this.form()!.controls.help_centers.push(helpCenterGroup({ name, url, language }));
    this.centersVersion.update((v) => v + 1);
  }

  removeHelpCenter(index: number): void {
    this.form()!.controls.help_centers.removeAt(index);
    this.centersVersion.update((v) => v + 1);
  }

  makePrimary(index: number): void {
    const centers = this.form()!.controls.help_centers;
    const row = centers.at(index);
    centers.removeAt(index);
    centers.insert(0, row);
    this.centersVersion.update((v) => v + 1);
  }

  addDetected(): void {
    for (const alt of this.missingAlternates())
      this.addHelpCenter(nativeLanguageName(alt.language), alt.url, alt.language);
  }

  /** A new site's primary help center starts as the start URL. */
  startUrlChanged(): void {
    const form = this.form()!;
    const start = form.controls.start_url;
    if (start.invalid || !start.value.trim()) return;
    const primary = form.controls.help_centers.at(0);
    if (primary && !primary.controls.url.value) {
      primary.controls.url.setValue(start.value.trim());
      if (!primary.controls.name.value) primary.controls.name.setValue(new URL(start.value).host);
    }
    this.centersVersion.update((v) => v + 1);
    this.detect();
  }

  // ── Discovery ─────────────────────────────────────────────────────────────

  detect(): void {
    const form = this.form()!;
    const start = form.controls.start_url;
    const sitemap = form.controls.crawl.controls.sitemap_url;
    if (!start.value.trim() || start.invalid || httpUrl(sitemap)) return;
    this.detecting.set(true);
    this.sites
      .detect(
        start.value.trim(),
        sitemap.value.trim(),
        form.controls.crawl.controls.respect_robots.value,
      )
      .subscribe({
        next: (d) => {
          this.discovery.set(d);
          this.detecting.set(false);
          const primary = form.controls.help_centers.at(0);
          const own = d.alternates.find(
            (a) => a.url.replace(/\/$/, '') === start.value.trim().replace(/\/$/, ''),
          );
          if (own && primary && !primary.controls.language.dirty)
            primary.controls.language.setValue(own.language);
        },
        error: (e) => {
          this.discovery.set({
            status: 'unreachable',
            message: apiErrors(e).join(' '),
            sitemap_url: null,
            sitemap_count: 0,
            url_count: 0,
            last_modified: null,
            sections: [],
            alternates: [],
          });
          this.detecting.set(false);
        },
      });
  }

  // ── Save ──────────────────────────────────────────────────────────────────

  /** Save, then return to the list, or go on to run an audit of the site. */
  save(andRun = false): void {
    const form = this.form()!;
    form.markAllAsTouched();
    if (form.invalid) {
      this.errors.set(formProblems(form));
      return;
    }
    this.errors.set([]);
    this.saving.set(true);
    const body = toSiteInput(form, this.prospect);
    const id = this.id();
    (id ? this.sites.update(id, body) : this.sites.create(body)).subscribe({
      next: (site) => {
        this.snack.open(`Saved ${site.name}`, undefined, { duration: 4000 });
        this.router.navigate(andRun ? ['/sites', site.id, 'run'] : ['/sites']);
      },
      error: (e) => {
        this.saving.set(false);
        this.errors.set(apiErrors(e));
      },
    });
  }
}

/** What's wrong with the form, in the words the page uses. */
export function formProblems(form: SiteForm): string[] {
  const c = form.controls;
  const problems: string[] = [];
  if (c.name.invalid) problems.push('Site: a name is required.');
  if (c.start_url.invalid) problems.push('Site: the start URL must be an http(s) URL.');
  if (c.help_centers.controls.some((g) => g.invalid))
    problems.push('Help centers: each needs a name, an http(s) URL and a language.');
  if (c.help_centers.hasError('duplicateUrl'))
    problems.push('Help centers: each needs its own URL.');
  if (c.crawl.invalid) problems.push('Discovery and crawling: check the highlighted values.');
  if (form.hasError('noCategories'))
    problems.push('Content integrity needs at least one category.');
  if (c.schedule.invalid) problems.push('Schedule: the time must be HH:MM, 24-hour.');
  return problems;
}
