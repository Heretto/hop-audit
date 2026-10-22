import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { HOP_API_URL } from '@heretto/hop-ui';
import { Observable } from 'rxjs';

export interface SetupState {
  agents_seeded_at: string;
  seeded_agents: Record<string, string>;
}

/** One-time organization setup: seeds the six analysis agents. Idempotent. */
@Injectable({ providedIn: 'root' })
export class SetupService {
  private http = inject(HttpClient);
  private api = inject(HOP_API_URL);

  ensure(): Observable<SetupState> {
    return this.http.post<SetupState>(`${this.api}/setup`, {});
  }
}
