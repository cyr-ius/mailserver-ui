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
    path: 'profile',
    canActivate: [authGuard],
    loadComponent: () => import('./features/profile/profile').then((m) => m.Profile),
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
        loadComponent: () => import('./features/mailserver/relay/relay').then((m) => m.Relay),
      },
      {
        path: 'postfix',
        loadComponent: () => import('./features/mailserver/postfix/postfix').then((m) => m.Postfix),
      },
      {
        path: 'dovecot',
        loadComponent: () => import('./features/mailserver/dovecot/dovecot').then((m) => m.Dovecot),
      },
      {
        path: 'aliases',
        loadComponent: () => import('./features/mailserver/aliases/aliases').then((m) => m.Aliases),
      },
      {
        path: 'sieve',
        loadComponent: () => import('./features/mailserver/sieve/sieve').then((m) => m.Sieve),
      },
      {
        path: 'spam',
        loadComponent: () => import('./features/mailserver/spam/spam').then((m) => m.Spam),
      },
      {
        path: 'rspamd',
        loadComponent: () => import('./features/mailserver/rspamd/rspamd').then((m) => m.Rspamd),
      },
      {
        path: 'ldap',
        loadComponent: () => import('./features/mailserver/ldap/ldap').then((m) => m.Ldap),
      },
      {
        path: 'dkim',
        loadComponent: () => import('./features/mailserver/dkim/dkim').then((m) => m.Dkim),
      },
      {
        path: 'dns',
        loadComponent: () => import('./features/mailserver/dns/dns').then((m) => m.Dns),
      },
      {
        path: 'restrictions',
        loadComponent: () =>
          import('./features/mailserver/restrictions/restrictions').then((m) => m.Restrictions),
      },
      {
        path: 'queue',
        loadComponent: () => import('./features/mailserver/queue/queue').then((m) => m.Queue),
      },
      {
        path: 'tls',
        loadComponent: () => import('./features/mailserver/tls/tls').then((m) => m.Tls),
      },
      {
        path: 'environment',
        loadComponent: () =>
          import('./features/mailserver/environment/environment').then((m) => m.Environment),
      },
      {
        path: 'logs',
        loadComponent: () => import('./features/mailserver/logs/logs').then((m) => m.Logs),
      },
      { path: '**', redirectTo: 'relay' },
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
        loadComponent: () => import('./features/settings/oidc/oidc').then((m) => m.Oidc),
      },
      { path: '**', redirectTo: 'oidc' },
    ],
  },
  { path: '**', redirectTo: 'dashboard' },
];
