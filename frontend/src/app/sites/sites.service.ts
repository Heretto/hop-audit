import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { HOP_API_URL } from '@heretto/hop-ui';
import { Observable } from 'rxjs';
import { Discovery, Site, SiteInput, SiteSummary } from './site.model';

@Injectable({ providedIn: 'root' })
export class SitesService {
  private http = inject(HttpClient);
  private url = `${inject(HOP_API_URL)}/sites`;

  list(): Observable<SiteSummary[]> {
    return this.http.get<SiteSummary[]>(this.url);
  }

  /** A new site's settings: everything on, each analysis on its seeded agent. */
  defaults(): Observable<SiteInput> {
    return this.http.get<SiteInput>(`${this.url}/defaults`);
  }

  get(id: string): Observable<Site> {
    return this.http.get<Site>(`${this.url}/${id}`);
  }

  create(site: SiteInput): Observable<Site> {
    return this.http.post<Site>(this.url, site);
  }

  update(id: string, site: SiteInput): Observable<Site> {
    return this.http.put<Site>(`${this.url}/${id}`, site);
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`${this.url}/${id}`);
  }

  detect(startUrl: string, sitemapUrl = '', respectRobots = true): Observable<Discovery> {
    return this.http.post<Discovery>(`${this.url}/detect`, {
      start_url: startUrl,
      sitemap_url: sitemapUrl,
      respect_robots: respectRobots,
    });
  }
}

/** The API's 422 detail as one readable line per problem. */
export function apiErrors(error: unknown): string[] {
  const detail = (error as { error?: { detail?: unknown } })?.error?.detail;
  if (typeof detail === 'string') return [detail];
  if (Array.isArray(detail)) {
    return detail.map((d: { loc?: (string | number)[]; msg?: string }) => {
      const where = (d.loc ?? []).filter((p) => p !== 'body').join(' › ');
      const msg = (d.msg ?? 'Invalid value').replace(/^Value error, /, '');
      return where ? `${where}: ${msg}` : msg;
    });
  }
  return ['Something went wrong. Try again.'];
}
