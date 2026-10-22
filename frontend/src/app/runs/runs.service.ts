import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { HOP_API_URL } from '@heretto/hop-ui';
import { Observable } from 'rxjs';
import {
  Comparison,
  Dashboard,
  Finding,
  LogEntry,
  PageDetail,
  PageRow,
  Preview,
  RunDetail,
  RunInput,
  RunListItem,
} from './run.model';

@Injectable({ providedIn: 'root' })
export class RunsService {
  private http = inject(HttpClient);
  private api = inject(HOP_API_URL);

  /** Reads the sitemaps afresh, so it can take a few seconds. */
  preview(siteId: string): Observable<Preview> {
    return this.http.get<Preview>(`${this.api}/sites/${siteId}/runs/preview`);
  }

  start(siteId: string, run: RunInput): Observable<RunDetail> {
    return this.http.post<RunDetail>(`${this.api}/sites/${siteId}/runs`, run);
  }

  forSite(siteId: string): Observable<RunListItem[]> {
    return this.http.get<RunListItem[]>(`${this.api}/sites/${siteId}/runs`);
  }

  all(): Observable<RunListItem[]> {
    return this.http.get<RunListItem[]>(`${this.api}/runs`);
  }

  get(runId: string): Observable<RunDetail> {
    return this.http.get<RunDetail>(`${this.api}/runs/${runId}`);
  }

  log(runId: string): Observable<LogEntry[]> {
    return this.http.get<LogEntry[]>(`${this.api}/runs/${runId}/log`);
  }

  control(runId: string, action: 'pause' | 'resume' | 'cancel' | 'analyze'): Observable<RunDetail> {
    return this.http.post<RunDetail>(`${this.api}/runs/${runId}/${action}`, {});
  }

  dashboard(runId: string): Observable<Dashboard> {
    return this.http.get<Dashboard>(`${this.api}/runs/${runId}/dashboard`);
  }

  pages(runId: string): Observable<PageRow[]> {
    return this.http.get<PageRow[]>(`${this.api}/runs/${runId}/pages`);
  }

  /** The pages as CSV; fetched rather than linked, since the API needs the auth header. */
  pagesCsv(runId: string): Observable<Blob> {
    return this.http.get(`${this.api}/runs/${runId}/pages.csv`, { responseType: 'blob' });
  }

  page(pageId: string): Observable<PageDetail> {
    return this.http.get<PageDetail>(`${this.api}/pages/${pageId}`);
  }

  /** Dismiss (with a reason the agent learns from) or restore a finding. */
  updateFinding(id: string, dismissed: boolean, reason = ''): Observable<Finding> {
    return this.http.patch<Finding>(`${this.api}/findings/${id}`, { dismissed, reason });
  }

  compare(a: string, b: string): Observable<Comparison> {
    return this.http.get<Comparison>(`${this.api}/runs/compare`, { params: { a, b } });
  }
}
