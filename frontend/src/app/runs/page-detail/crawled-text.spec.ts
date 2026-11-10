import { TestBed } from '@angular/core/testing';
import { Block, PageContent } from '../run.model';
import { CrawledText, fileName, group, mediaLabel, summary } from './crawled-text';

const BLOCKS: Block[] = [
  { t: 'h1', x: 'Publish a map' },
  { t: 'p', x: 'First you open the map.', d: 0 },
  { t: 'img', src: 'https://h.x/img/diagram%20one.png', alt: 'Diagram', d: 0 },
  { t: 'img', src: 'https://h.x/b.png', alt: null, d: 1 },
  { t: 'li', x: 'One', d: 1 },
  { t: 'li', x: 'First', d: 1, n: 1 },
  { t: 'row', cells: ['A', 'B'], head: true },
  { t: 'row', cells: ['1', '2'], head: false },
  { t: 'pre', x: 'code\n  indented' },
  { t: 'summary', x: 'More', d: 0 },
  { t: 'media', kind: 'iframe', src: 'https://video.example/embed/x', title: 'Demo', d: 0 },
];

function content(blocks?: Block[]): PageContent {
  return {
    title: 'Publish',
    description: null,
    canonical: null,
    robots: '',
    lang: 'en',
    og: {},
    headings: [],
    images: [],
    breadcrumb: [],
    text: 'Publish a map\nFirst you open the map.',
    blocks,
  };
}

function render(c: PageContent) {
  const fixture = TestBed.createComponent(CrawledText);
  fixture.componentRef.setInput('content', c);
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

describe('CrawledText', () => {
  it('groups table rows and leaves the rest in order', () => {
    const shown = group(BLOCKS);
    expect(shown.map((b) => b.t)).toEqual([
      'h1',
      'p',
      'img',
      'img',
      'li',
      'li',
      'table',
      'pre',
      'summary',
      'media',
    ]);
    const table = shown[6];
    expect(table.t === 'table' && table.rows.length).toBe(2);
  });

  it('summarizes headings, images without alt text and media', () => {
    expect(summary(BLOCKS)).toBe(
      '1 heading · 2 images (1 without alt text) · 1 embedded media item',
    );
    expect(summary([{ t: 'p', x: 'x', d: 0 }])).toBe('0 headings · 0 images');
  });

  it('names media and image files', () => {
    expect(mediaLabel('video')).toEqual({ icon: 'smart_display', label: 'Video' });
    expect(mediaLabel('applet').label).toBe('Media');
    expect(fileName('https://h.x/img/diagram%20one.png')).toBe('diagram one.png');
    expect(fileName('not a url')).toBe('not a url');
  });

  it('formats the blocks and marks where images and media sat', () => {
    const { el } = render(content(BLOCKS));
    expect(el.querySelector('.heading.h1')!.textContent).toContain('H1');
    expect(el.querySelector('.heading.h1')!.textContent).toContain('Publish a map');
    const markers = [...el.querySelectorAll('.marker')];
    expect(markers.map((m) => m.querySelector('span')!.textContent)).toEqual([
      'Image: “Diagram”',
      'Image without alt text',
      'Embedded frame: “Demo”',
    ]);
    expect(markers[1].classList).toContain('warn');
    expect((markers[1] as HTMLElement).style.marginLeft).toBe('20px');
    const link = markers[0].querySelector('a')!;
    expect(link.textContent).toBe('diagram one.png');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
    expect([...el.querySelectorAll('.li .mark')].map((m) => m.textContent)).toEqual(['•', '1.']);
    expect(el.querySelectorAll('table tr').length).toBe(2);
    expect(el.querySelector('tr.head')!.textContent).toBe('AB');
    expect(el.querySelector('pre.code')!.textContent).toBe('code\n  indented');
    expect(el.querySelector('.summary')!.textContent).toContain('More');
    expect(el.querySelector('pre.text')).toBeNull();
  });

  it('switches to the plain text the analyses read', () => {
    const { fixture, el } = render(content(BLOCKS));
    fixture.componentInstance.view.set('plain');
    fixture.detectChanges();
    expect(el.querySelector('.doc')).toBeNull();
    expect(el.querySelector('pre.text')!.textContent).toBe(
      'Publish a map\nFirst you open the map.',
    );
    expect(el.textContent).not.toContain('crawled before its layout was kept');
  });

  it('shows the plain text, and why, for pages crawled before blocks were kept', () => {
    const { el } = render(content());
    expect(el.querySelector('mat-button-toggle-group')).toBeNull();
    expect(el.textContent).toContain('crawled before its layout was kept');
    expect(el.querySelector('pre.text')!.textContent).toContain('First you open the map.');
  });
});
