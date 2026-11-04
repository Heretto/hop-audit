import { DatePipe } from '@angular/common';
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
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { HopConfirmDialogComponent, HopConfirmDialogData } from '@heretto/hop-ui';
import { forkJoin, Observable } from 'rxjs';
import { apiErrors } from '../../sites/sites.service';
import { blobErrors, download } from '../run-format';
import {
  DeliverablesChange,
  DeliverablesView,
  CheckItem,
  SheetCopy,
  SheetKind,
  WhyLine,
} from '../run.model';
import { RunsService } from '../runs.service';
import { PAGE_H, SheetFrame } from './sheet-frame';

export const MAX_LOGO_BYTES = 512 * 1024;
const LOGO_TYPES = ['image/png', 'image/jpeg', 'image/svg+xml'];

/** Tags for the "why it matters" lines, by Business Imperative. */
export function imperativeTag(w: WhyLine): { cls: string; label: string } {
  const cls = w.imperative === 'Risk' ? 'risk' : w.imperative === 'Cost' ? 'cost' : 'ret';
  return { cls, label: w.ai ? `${w.imperative} · AI` : w.imperative };
}

/** "Pat Smith, Account Executive" ⇄ name and title, as the one-sheet prints them. */
export function splitSender(value: string): { sender_name: string; sender_title: string } {
  const [name, ...rest] = value.split(',');
  return { sender_name: name.trim(), sender_title: rest.join(',').trim() };
}

export function joinSender(name: string, title: string): string {
  return [name, title].filter((p) => p.trim()).join(', ');
}

@Component({
  selector: 'app-deliverables-page',
  imports: [
    DatePipe,
    FormsModule,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    SheetFrame,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './deliverables-page.html',
  styleUrl: './deliverables-page.scss',
})
export class DeliverablesPage implements OnInit {
  /** Route parameter. */
  readonly runId = input.required<string>();

  private runs = inject(RunsService);
  private snack = inject(MatSnackBar);
  private dialog = inject(MatDialog);

  readonly view = signal<DeliverablesView | null>(null);
  readonly error = signal<string | null>(null);
  readonly sheets = signal<Partial<Record<SheetKind, string>>>({});
  readonly building = signal(false);
  readonly busy = signal<string | null>(null); // a download in progress

  /** Editable copies of the copy and the prospect's details, saved on blur. */
  draft: SheetCopy | null = null;
  company = '';
  sender = '';
  email = '';

  readonly pageHeight = PAGE_H;
  readonly tag = imperativeTag;
  readonly built = computed(() => !!this.view()?.copy);
  /** The findings the "why it matters" lines trace to. */
  readonly traces = computed(() =>
    (this.view()?.copy?.why ?? []).filter((w) => w.codes.length).map((w) => w.codes.join(', ')),
  );

  ngOnInit(): void {
    this.runs.deliverables(this.runId()).subscribe({
      next: (v) => this.show(v, true),
      error: (e) => this.error.set(apiErrors(e).join(' ')),
    });
  }

  private show(v: DeliverablesView, sheets: boolean): void {
    this.view.set(v);
    this.draft = v.copy ? structuredClone(v.copy) : null;
    this.company = v.prospect.company;
    this.sender = joinSender(v.prospect.sender_name, v.prospect.sender_title);
    this.email = v.prospect.sender_email;
    if (sheets && v.copy) this.loadSheets();
  }

  private loadSheets(): void {
    const id = this.runId();
    forkJoin({
      lead: this.runs.sheetHtml(id, 'lead'),
      exec: this.runs.sheetHtml(id, 'exec'),
    }).subscribe({
      next: (sheets) => this.sheets.set(sheets),
      error: (e) => this.snack.open(apiErrors(e).join(' '), 'Dismiss'),
    });
  }

  private save(change: Observable<DeliverablesView>, sheets = true): void {
    change.subscribe({
      next: (v) => this.show(v, sheets),
      error: (e) => this.snack.open(apiErrors(e).join(' '), 'Dismiss'),
    });
  }

  budget(value: string, key: string): { text: string; over: boolean } {
    const limit = this.view()?.budgets[key] ?? 0;
    return { text: `${value.length} / ${limit}`, over: value.length > limit };
  }

  whyLength(w: WhyLine): number {
    return `${w.lead} ${w.text}`.trim().length;
  }

  build(): void {
    const start = () => {
      this.building.set(true);
      this.runs.buildDeliverables(this.runId()).subscribe({
        next: (v) => {
          this.building.set(false);
          this.show(v, true);
        },
        error: (e) => {
          this.building.set(false);
          this.snack.open(apiErrors(e).join(' '), 'Dismiss');
        },
      });
    };
    if (!this.built()) return start();
    const data: HopConfirmDialogData = {
      title: 'Rebuild the one-sheets?',
      message:
        'The Collateral Writer writes the copy again from the confirmed findings. Your edits to the headlines, ' +
        'why-it-matters lines and impact cards are replaced, and the quotes need spot-checking again.',
      confirmText: 'Rebuild',
    };
    this.dialog
      .open(HopConfirmDialogComponent, { data })
      .afterClosed()
      .subscribe((ok) => ok && start());
  }

  saveCopy(): void {
    const saved = this.view()?.copy;
    if (!this.draft || JSON.stringify(this.draft) === JSON.stringify(saved)) return;
    this.save(this.runs.updateDeliverables(this.runId(), { copy: this.draft }));
  }

  saveProspect(): void {
    const p = this.view()!.prospect;
    const change = {
      company: this.company.trim(),
      ...splitSender(this.sender),
      sender_email: this.email.trim(),
    };
    if (
      change.company === p.company &&
      change.sender_name === p.sender_name &&
      change.sender_title === p.sender_title &&
      change.sender_email === p.sender_email
    ) {
      return;
    }
    this.save(this.runs.updateDeliverables(this.runId(), { prospect: change }), this.built());
  }

  uploadLogo(event: Event): void {
    const field = event.target as HTMLInputElement;
    const file = field.files?.[0];
    field.value = '';
    if (!file) return;
    if (!LOGO_TYPES.includes(file.type)) {
      this.snack.open('Use a PNG, JPEG or SVG file.', 'Dismiss');
      return;
    }
    if (file.size > MAX_LOGO_BYTES) {
      this.snack.open('The logo file is over 512 KB.', 'Dismiss');
      return;
    }
    const reader = new FileReader();
    reader.onload = () =>
      this.save(this.runs.setLogo(this.runId(), String(reader.result)), this.built());
    reader.readAsDataURL(file);
  }

  removeLogo(): void {
    this.save(this.runs.setLogo(this.runId(), null), this.built());
  }

  toggle(item: CheckItem): void {
    if (!item.toggle) return;
    const change: DeliverablesChange = { [item.key]: !item.ok };
    this.save(this.runs.updateDeliverables(this.runId(), change), false);
  }

  /** A thumbnail measured its sheet; keep the server's record current. */
  measured(kind: SheetKind, height: number): void {
    if (this.view()?.heights[kind] === height) return;
    this.save(this.runs.updateDeliverables(this.runId(), { heights: { [kind]: height } }), false);
  }

  private file(request: Observable<Blob>, what: string, ext: string): void {
    const run = this.view()!.run;
    this.busy.set(what);
    request.subscribe({
      next: (blob) => {
        this.busy.set(null);
        download(
          blob,
          `${run.site_name}-audit-${run.number}-${what}.${ext}`.replace(/\s+/g, '-').toLowerCase(),
        );
      },
      error: async (e) => {
        this.busy.set(null);
        this.snack.open((await blobErrors(e)).join(' '), 'Dismiss');
      },
    });
  }

  sheetPdf(kind: SheetKind): void {
    const what = kind === 'lead' ? 'content-integrity-snapshot' : 'executive-brief';
    this.file(this.runs.sheetPdf(this.runId(), kind), what, 'pdf');
  }

  downloadPdfs(): void {
    this.sheetPdf('lead');
    this.sheetPdf('exec');
  }

  report(file: 'report.pdf' | 'report.docx'): void {
    this.file(this.runs.reportFile(this.runId(), file), 'report', file.split('.')[1]);
  }

  copyNote(): void {
    navigator.clipboard.writeText(this.view()!.internal_note).then(
      () => this.snack.open('Internal note copied', undefined, { duration: 2500 }),
      () => this.snack.open("Couldn't copy the note", 'Dismiss'),
    );
  }
}
