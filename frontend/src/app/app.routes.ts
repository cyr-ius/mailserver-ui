import { Routes } from '@angular/router';

import { authGuard, guestGuard } from './core/auth.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'welcome' },
  {
    path: 'login',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/login/login').then((m) => m.Login),
  },
  {
    path: 'welcome',
    canActivate: [authGuard],
    loadComponent: () => import('./features/welcome/welcome').then((m) => m.Welcome),
  },
  { path: '**', redirectTo: 'welcome' },
];
