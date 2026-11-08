import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  inject,
  input,
  OnDestroy,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { DomSanitizer } from '@angular/platform-browser';

/** Letter at 96 dpi, the one-sheet's page. */
export const PAGE_W = 816;
export const PAGE_H = 1056;

/**
 * The sheet's natural height: each page's root without its fixed height, as
 * the skill's build_onesheet.py measures it; the tallest page. More than
 * PAGE_H means a page overflows.
 */
export function naturalHeight(doc: Document): number | null {
  const pages = [...(doc.body?.children ?? [])].filter(
    (el): el is HTMLElement => el.tagName === 'DIV',
  );
  if (!pages.length) return null;
  return Math.max(
    ...pages.map((page) => {
      const before = page.style.height;
      page.style.height = 'auto';
      const height = page.scrollHeight;
      page.style.height = before;
      return height;
    }),
  );
}

/** How many Letter pages the sheet has. */
export function pageCount(doc: Document): number {
  return [...(doc.body?.children ?? [])].filter((el) => el.tagName === 'DIV').length || 1;
}

/**
 * A one-sheet's HTML in a sandboxed frame (no scripts), scaled to the width
 * it's given; `crop` shows only the top that many pixels (thumbnails).
 * Emits the measured height once the page and its fonts have loaded.
 */
@Component({
  selector: 'app-sheet-frame',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="frame" #box [style.height.px]="crop() ?? pageHeight() * pages()">
      <iframe
        #frame
        [attr.title]="label()"
        [srcdoc]="safeHtml()"
        sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
        [style.height.px]="unscaledPage * pages()"
        [style.transform]="'scale(' + scale() + ')'"
        (load)="measure()"
      ></iframe>
    </div>
  `,
  styles: `
    :host {
      display: block;
    }
    .frame {
      position: relative;
      overflow: hidden;
      border-radius: 8px;
      border: 1px solid var(--border-default);
      background: var(--bg-secondary);
    }
    iframe {
      position: absolute;
      top: 0;
      left: 0;
      width: ${PAGE_W}px;
      border: 0;
      transform-origin: 0 0;
    }
  `,
})
export class SheetFrame implements AfterViewInit, OnDestroy {
  readonly html = input.required<string>();
  readonly label = input('One-sheet preview');
  /** Show only the top this many pixels of the scaled page. */
  readonly crop = input<number | null>(null);
  readonly measured = output<number>();

  private sanitizer = inject(DomSanitizer);
  private box = viewChild.required<ElementRef<HTMLElement>>('box');
  private frame = viewChild.required<ElementRef<HTMLIFrameElement>>('frame');
  private observer?: ResizeObserver;

  readonly width = signal(PAGE_W);
  readonly scale = computed(() => Math.min(1, this.width() / PAGE_W));
  readonly pageHeight = computed(() => PAGE_H * this.scale());
  readonly unscaledPage = PAGE_H;
  /** Letter pages in the sheet; the frame grows to show them all. */
  readonly pages = signal(1);
  /** Our own server's rendering of our own template; the frame runs no scripts. */
  readonly safeHtml = computed(() => this.sanitizer.bypassSecurityTrustHtml(this.html()));

  ngAfterViewInit(): void {
    const box = this.box().nativeElement;
    this.width.set(box.clientWidth || PAGE_W);
    if (typeof ResizeObserver !== 'undefined') {
      this.observer = new ResizeObserver(() => this.width.set(box.clientWidth || PAGE_W));
      this.observer.observe(box);
    }
  }

  ngOnDestroy(): void {
    this.observer?.disconnect();
  }

  async measure(): Promise<void> {
    const doc = this.frame().nativeElement.contentDocument;
    if (!doc) return;
    await doc.fonts?.ready; // Poppins changes the line breaks
    this.pages.set(pageCount(doc));
    const height = naturalHeight(doc);
    if (height) this.measured.emit(height);
  }
}
