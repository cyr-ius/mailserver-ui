import { Routes } from '@angular/router';

import { adminGuard, authGuard, guestGuard } from './core/auth.guard';

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
  {
    path: 'users',
    canActivate: [adminGuard],
    loadComponent: () => import('./features/users/users').then((m) => m.Users),
  },
  {
    path: 'settings',
    canActivate: [adminGuard],
    loadComponent: () => import('./features/settings/settings').then((m) => m.Settings),
  },
  { path: '**', redirectTo: 'welcome' },
];
