import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';

import { routes } from './app.routes';
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
  ],
};
