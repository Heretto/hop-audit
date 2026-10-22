import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { HOP_API_URL } from '@heretto/hop-ui';
import { Observable } from 'rxjs';
import { LogEntry, Preview, RunDetail, RunInput, RunListItem } from './run.model';

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

  control(runId: string, action: 'pause' | 'resume' | 'cancel'): Observable<RunDetail> {
    return this.http.post<RunDetail>(`${this.api}/runs/${runId}/${action}`, {});
  }
}
