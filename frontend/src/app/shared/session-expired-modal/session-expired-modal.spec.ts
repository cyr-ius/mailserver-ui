import { Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

import { SessionExpiryService } from '../../core/session-expiry.service';
import { sessionExpiryInterceptor } from '../../core/session-expiry.interceptor';
import { SessionExpiredModal } from './session-expired-modal';

/** Landing page for the redirect performed once the dialog is acknowledged. */
@Component({ template: '' })
class LoginStub {}

describe('SessionExpiredModal', () => {
  let fixture: ComponentFixture<SessionExpiredModal>;
  let sessionExpiry: SessionExpiryService;
  let http: HttpClient;
  let httpMock: HttpTestingController;

  const el = () => fixture.nativeElement as HTMLElement;
  const dialog = () => el().querySelector('.modal[role="dialog"]');
  const signInButton = () => el().querySelector('.modal-footer .btn') as HTMLButtonElement;

  /** Fail a request with 401, as an expired session cookie would. */
  const failWith401 = (url: string) => {
    http.get(url).subscribe({ error: () => undefined });
    httpMock.expectOne(url).flush(null, { status: 401, statusText: 'Unauthorized' });
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SessionExpiredModal],
      providers: [
        provideRouter([{ path: 'login', component: LoginStub }]),
        provideHttpClient(withInterceptors([sessionExpiryInterceptor])),
        provideHttpClientTesting(),
      ],
    }).compileComponents();

    sessionExpiry = TestBed.inject(SessionExpiryService);
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);

    fixture = TestBed.createComponent(SessionExpiredModal);
    fixture.detectChanges();
  });

  afterEach(() => {
    httpMock.verify();
    document.body.classList.remove('modal-open');
  });

  it('stays out of the DOM while the session holds', () => {
    expect(dialog()).toBeNull();
    expect(document.body.classList.contains('modal-open')).toBe(false);
  });

  it('opens when an API call reports an expired session', () => {
    failWith401('/api/mailboxes');
    fixture.detectChanges();

    expect(dialog()).not.toBeNull();
    expect(document.body.classList.contains('modal-open')).toBe(true);
  });

  it('leaves the login and probe endpoints alone, where a 401 is expected', () => {
    failWith401('/api/auth/login');
    failWith401('/api/auth/me');
    fixture.detectChanges();

    expect(sessionExpiry.expired()).toBe(false);
    expect(dialog()).toBeNull();
  });

  it('focuses its only action, so the keyboard never stays behind the backdrop', () => {
    failWith401('/api/mailboxes');
    fixture.detectChanges();

    expect(document.activeElement).toBe(signInButton());
  });

  it('signs the user out and closes once the action is taken', async () => {
    failWith401('/api/mailboxes');
    fixture.detectChanges();

    signInButton().click();
    httpMock.expectOne('/api/auth/logout').flush({});
    await fixture.whenStable();
    fixture.detectChanges();

    expect(sessionExpiry.expired()).toBe(false);
    expect(dialog()).toBeNull();
    expect(document.body.classList.contains('modal-open')).toBe(false);
  });
});
