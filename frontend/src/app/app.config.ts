import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';

import { routes } from './app.routes';
import { AuthService } from './core/auth.service';
import { credentialsInterceptor } from './core/credentials.interceptor';
import { sessionExpiryInterceptor } from './core/session-expiry.interceptor';
import { ThemeService } from './core/theme.service';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(
      withFetch(),
      withInterceptors([credentialsInterceptor, sessionExpiryInterceptor]),
    ),
    // Instantiate at bootstrap so `auto` starts tracking the system preference
    // even on screens that never render the theme toggle.
    provideAppInitializer(() => {
      inject(ThemeService);
    }),
    // The auth capabilities gate what the UI may offer (API keys, login methods),
    // so they are fetched once at bootstrap rather than by the login page alone:
    // landing straight on /profile must know them too. A failure here is not
    // fatal — the guards still decide what the user can reach.
    provideAppInitializer(() => {
      const auth = inject(AuthService);
      return auth.loadConfig().catch(() => null);
    }),
  ],
};
