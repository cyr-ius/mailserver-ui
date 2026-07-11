import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import { AuditPage, AuditQuery } from './audit.models';

/**
 * Read access to the audit trail (admin only). The trail is append-only: there
 * is nothing to create or edit here, entries are written by the actions they
 * describe.
 */
@Injectable({ providedIn: 'root' })
export class AuditService {
  private readonly http = inject(HttpClient);

  /** Fetch a page of entries, newest first. */
  async list(query: AuditQuery = {}): Promise<AuditPage> {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(query)) {
      // An empty filter must not be sent: the backend would match on "" and
      // return nothing.
      if (value !== undefined && value !== '') {
        params = params.set(key, String(value));
      }
    }
    return firstValueFrom(this.http.get<AuditPage>('/api/audit', { params }));
  }
}
