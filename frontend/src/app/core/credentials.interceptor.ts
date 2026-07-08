import { HttpInterceptorFn } from '@angular/common/http';

/**
 * Ensure the HttpOnly session cookie is sent with every API request, even
 * across origins (e.g. when the SPA and API are served from different hosts).
 */
export const credentialsInterceptor: HttpInterceptorFn = (req, next) =>
  next(req.clone({ withCredentials: true }));
