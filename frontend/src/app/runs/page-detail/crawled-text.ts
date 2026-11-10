import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatIconModule } from '@angular/material/icon';
import { Block, PageContent } from '../run.model';

/** A row of blocks as drawn: consecutive table rows become one table. */
type Row = Extract<Block, { t: 'row' }>;
export type Shown = Exclude<Block, Row> | { t: 'table'; rows: Row[] };

const MEDIA: Record<string, { icon: string; label: string }> = {
  iframe: { icon: 'web_asset', label: 'Embedded frame' },
  video: { icon: 'smart_display', label: 'Video' },
  audio: { icon: 'audiotrack', label: 'Audio' },
  embed: { icon: 'extension', label: 'Embedded object' },
  object: { icon: 'extension', label: 'Embedded object' },
};

export function group(blocks: Block[]): Shown[] {
  const out: Shown[] = [];
  for (const b of blocks) {
    const last = out.at(-1);
    if (b.t !== 'row') out.push(b);
    else if (last?.t === 'table') last.rows.push(b);
    else out.push({ t: 'table', rows: [b] });
  }
  return out;
}

export function mediaLabel(kind: string): { icon: string; label: string } {
  return MEDIA[kind] ?? { icon: 'perm_media', label: 'Media' };
}

/** The last path segment, enough to tell images apart. */
export function fileName(src: string): string {
  try {
    const path = new URL(src).pathname.replace(/\/$/, '');
    return decodeURIComponent(path.slice(path.lastIndexOf('/') + 1)) || src;
  } catch {
    return src;
  }
}

/** One line on what the formatted view shows. */
export function summary(blocks: Block[]): string {
  const count = (t: Block['t'] | 'heading') =>
    blocks.filter((b) => (t === 'heading' ? /^h[1-6]$/.test(b.t) : b.t === t)).length;
  const images = blocks.filter((b) => b.t === 'img');
  const noAlt = images.filter((b) => b.t === 'img' && !b.alt).length;
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;
  const parts = [plural(count('heading'), 'heading'), plural(images.length, 'image')];
  if (noAlt) parts[1] += ` (${noAlt} without alt text)`;
  const media = count('media');
  if (media) parts.push(plural(media, 'embedded media item'));
  return parts.join(' · ');
}

/** The main content as crawled: formatted from its blocks, or the plain text the analyses read. */
@Component({
  selector: 'app-crawled-text',
  imports: [MatButtonToggleModule, MatIconModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (blocks().length) {
      <div class="bar">
        <span class="sub">{{ summary() }}</span>
        <mat-button-toggle-group
          [value]="view()"
          (change)="view.set($event.value)"
          aria-label="How to show the crawled text"
        >
          <mat-button-toggle value="formatted">Formatted</mat-button-toggle>
          <mat-button-toggle value="plain">Plain text</mat-button-toggle>
        </mat-button-toggle-group>
      </div>
    }
    @if (blocks().length && view() === 'formatted') {
      <div class="doc">
        @for (b of shown(); track $index) {
          @switch (b.t) {
            @case ('table') {
              <table>
                @for (r of b.rows; track $index) {
                  <tr [class.head]="r.head">
                    @for (c of r.cells; track $index) {
                      <td>{{ c }}</td>
                    }
                  </tr>
                }
              </table>
            }
            @case ('img') {
              <div class="marker" [style.margin-left.px]="b.d * 20" [class.warn]="!b.alt">
                <mat-icon>image</mat-icon>
                @if (b.alt) {
                  <span>Image: “{{ b.alt }}”</span>
                } @else {
                  <span>Image without alt text</span>
                }
                @if (b.src) {
                  <a class="src mono" [href]="b.src" target="_blank" rel="noopener noreferrer">{{
                    fileName(b.src)
                  }}</a>
                }
              </div>
            }
            @case ('media') {
              @let m = mediaLabel(b.kind);
              <div class="marker" [style.margin-left.px]="b.d * 20">
                <mat-icon>{{ m.icon }}</mat-icon>
                <span>{{ m.label }}{{ b.title ? ': “' + b.title + '”' : '' }}</span>
                @if (b.src) {
                  <a class="src mono" [href]="b.src" target="_blank" rel="noopener noreferrer">{{
                    b.src
                  }}</a>
                }
              </div>
            }
            @case ('pre') {
              <pre class="code">{{ b.x }}</pre>
            }
            @case ('li') {
              <div class="li" [style.margin-left.px]="b.d * 20">
                <span class="mark">{{ b.n ? b.n + '.' : '•' }}</span
                ><span>{{ b.x }}</span>
              </div>
            }
            @case ('summary') {
              <div class="summary" [style.margin-left.px]="b.d * 20">
                <mat-icon>expand_more</mat-icon><span>{{ b.x }}</span>
              </div>
            }
            @case ('quote') {
              <blockquote [style.margin-left.px]="b.d * 20">{{ b.x }}</blockquote>
            }
            @case ('term') {
              <p class="term" [style.margin-left.px]="b.d * 20">{{ b.x }}</p>
            }
            @case ('p') {
              <p [style.margin-left.px]="b.d * 20">{{ b.x }}</p>
            }
            @default {
              <div class="heading" [class]="b.t">
                <span class="level">{{ b.t.toUpperCase() }}</span
                >{{ b.x }}
              </div>
            }
          }
        }
      </div>
    } @else {
      @if (!blocks().length) {
        <p class="sub">
          This page was crawled before its layout was kept. Run the audit again to see headings,
          lists, tables and where images and media were.
        </p>
      }
      <pre class="text">{{ content().text }}</pre>
    }
  `,
  styles: `
    :host {
      display: block;
    }
    .bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }
    .doc,
    .text {
      max-height: 640px;
      overflow: auto;
      padding: 16px;
      border-radius: 8px;
      background: var(--surface-sunken);
      font-family: var(--font-sans);
    }
    .text {
      white-space: pre-wrap;
    }
    .doc {
      display: flex;
      flex-direction: column;
      gap: 8px;
      line-height: 1.5;

      p {
        margin: 0;
      }
    }
    .heading {
      display: flex;
      align-items: baseline;
      gap: 8px;
      margin-top: 8px;
      font-weight: 600;
      color: var(--text-primary);
    }
    .h1 {
      font-size: 1.5rem;
    }
    .h2 {
      font-size: 1.25rem;
    }
    .h3 {
      font-size: 1.125rem;
    }
    .level {
      flex: none;
      padding: 0 6px;
      border-radius: 4px;
      background: var(--bg-tertiary);
      color: var(--text-tertiary);
      font-family: var(--font-mono);
      font-size: 0.6875rem;
      font-weight: 500;
    }
    .li {
      display: flex;
      gap: 8px;
    }
    .mark {
      flex: none;
      min-width: 1.25em;
      color: var(--text-tertiary);
      text-align: right;
    }
    .term {
      font-weight: 600;
    }
    blockquote {
      margin: 0;
      padding-left: 12px;
      border-left: 3px solid var(--border-strong);
      color: var(--text-secondary);
    }
    .summary {
      display: flex;
      align-items: center;
      gap: 4px;
      font-weight: 600;
    }
    .marker {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      padding: 6px 10px;
      border: 1px dashed var(--border-strong);
      border-radius: 6px;
      background: var(--bg-primary);
      color: var(--text-secondary);
      font-size: 0.875rem;

      &.warn {
        border-color: var(--color-warning-border);
        background: var(--color-warning-bg);
        color: var(--color-warning-text);
      }
    }
    .marker mat-icon,
    .summary mat-icon {
      font-size: 18px;
      width: 18px;
      height: 18px;
    }
    .src {
      min-width: 0;
      overflow-wrap: anywhere;
      color: var(--text-tertiary);
      font-size: 0.75rem;
    }
    .code {
      margin: 0;
      padding: 10px 12px;
      border-radius: 6px;
      background: var(--bg-tertiary);
      font-family: var(--font-mono);
      font-size: 0.8125rem;
      white-space: pre-wrap;
    }
    table {
      border-collapse: collapse;
      font-size: 0.875rem;

      td {
        padding: 4px 10px;
        border: 1px solid var(--border-default);
        vertical-align: top;
      }
      .head td {
        background: var(--bg-tertiary);
        font-weight: 600;
      }
    }
  `,
})
export class CrawledText {
  readonly content = input.required<PageContent>();
  readonly view = signal<'formatted' | 'plain'>('formatted');

  readonly blocks = computed(() => this.content().blocks ?? []);
  readonly shown = computed(() => group(this.blocks()));
  readonly summary = computed(() => summary(this.blocks()));
  readonly mediaLabel = mediaLabel;
  readonly fileName = fileName;
}
