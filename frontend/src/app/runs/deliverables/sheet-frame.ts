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
 * The sheet's natural height: its root without the fixed page height, as the
 * skill's build_onesheet.py measures it. More than PAGE_H means it overflows.
 */
export function naturalHeight(doc: Document): number | null {
  const root = doc.body?.firstElementChild as HTMLElement | null;
  if (!root) return null;
  const before = root.style.height;
  root.style.height = 'auto';
  const height = root.scrollHeight;
  root.style.height = before;
  return height;
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
    <div class="frame" #box [style.height.px]="crop() ?? pageHeight()">
      <iframe
        #frame
        [attr.title]="label()"
        [srcdoc]="safeHtml()"
        sandbox="allow-same-origin"
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
      height: ${PAGE_H}px;
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
    const height = naturalHeight(doc);
    if (height) this.measured.emit(height);
  }
}
