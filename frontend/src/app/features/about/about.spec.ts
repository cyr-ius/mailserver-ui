import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { describe, it, expect } from 'vitest';

import { About } from './about';

describe('About', () => {
  it('loads the installed version from /api/health without throwing', async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    const fixture = TestBed.createComponent(About);

    expect(() => fixture.detectChanges()).not.toThrow();

    const httpMock = TestBed.inject(HttpTestingController);
    const req = httpMock.expectOne('/api/health');
    req.flush({ status: 'healthy', app: 'Mailserver UI', version: '1.2.2' });
    await fixture.whenStable();

    expect(fixture.componentInstance['appVersion']()).toBe('1.2.2');
    httpMock.verify();
  });
});
