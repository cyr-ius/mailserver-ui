import { Routes } from '@angular/router';

import { adminGuard, authGuard, guestGuard, mailboxManagerGuard } from './core/auth.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
  {
    path: 'login',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/login/login').then((m) => m.Login),
  },
  {
    path: 'dashboard',
    canActivate: [authGuard],
    loadComponent: () => import('./features/dashboard/dashboard').then((m) => m.Dashboard),
  },
  {
    path: 'about',
    canActivate: [authGuard],
    loadComponent: () => import('./features/about/about').then((m) => m.About),
  },
  {
    path: 'mailboxes',
    canActivate: [mailboxManagerGuard],
    loadComponent: () => import('./features/mailboxes/mailboxes').then((m) => m.Mailboxes),
  },
  {
    path: 'mailserver',
    canActivate: [adminGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'relay' },
      {
        path: 'relay',
        loadComponent: () => import('./features/mailserver/mailserver').then((m) => m.Mailserver),
      },
      {
        path: 'postfix',
        loadComponent: () => import('./features/mailserver/mailserver').then((m) => m.Mailserver),
      },
      {
        path: 'dkim',
        loadComponent: () => import('./features/mailserver/mailserver').then((m) => m.Mailserver),
      },
      {
        path: 'restrictions',
        loadComponent: () => import('./features/mailserver/mailserver').then((m) => m.Mailserver),
      },
      {
        path: 'dovecot',
        loadComponent: () => import('./features/mailserver/mailserver').then((m) => m.Mailserver),
      },
      {
        path: 'aliases',
        loadComponent: () => import('./features/mailserver/mailserver').then((m) => m.Mailserver),
      },
      {
        path: 'sieve',
        loadComponent: () => import('./features/mailserver/mailserver').then((m) => m.Mailserver),
      },
      {
        path: 'dns',
        loadComponent: () => import('./features/mailserver/mailserver').then((m) => m.Mailserver),
      },
      {
        path: 'queue',
        loadComponent: () => import('./features/mailserver/mailserver').then((m) => m.Mailserver),
      },
      {
        path: 'tls',
        loadComponent: () => import('./features/mailserver/mailserver').then((m) => m.Mailserver),
      },
      {
        path: 'environment',
        loadComponent: () => import('./features/mailserver/mailserver').then((m) => m.Mailserver),
      },
      {
        path: 'logs',
        loadComponent: () => import('./features/mailserver/mailserver').then((m) => m.Mailserver),
      },
    ],
  },
  {
    path: 'fail2ban',
    canActivate: [adminGuard],
    loadComponent: () => import('./features/fail2ban/fail2ban').then((m) => m.Fail2ban),
  },
  {
    path: 'users',
    canActivate: [adminGuard],
    loadComponent: () => import('./features/users/users').then((m) => m.Users),
  },
  {
    path: 'settings',
    canActivate: [adminGuard],
    children: [
      {
        path: '',
        pathMatch: 'full',
        redirectTo: 'oidc',
      },
      {
        path: 'oidc',
        loadComponent: () => import('./features/settings/settings').then((m) => m.Settings),
      },
      {
        path: 'appearance',
        loadComponent: () => import('./features/settings/settings').then((m) => m.Settings),
      },
      {
        path: 'syslog',
        loadComponent: () => import('./features/settings/settings').then((m) => m.Settings),
      },
      {
        path: 'email',
        loadComponent: () => import('./features/settings/settings').then((m) => m.Settings),
      },
    ],
  },
  { path: '**', redirectTo: 'dashboard' },
];
