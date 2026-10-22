import { Routes } from '@angular/router';
import { HOP_AGENT_ROUTES, hopAdminGuard, hopAuthGuard } from '@heretto/hop-ui';

const hop = () => import('@heretto/hop-ui');

export const routes: Routes = [
  // Signed out: hop-core's pages, without the shell.
  { path: 'login', loadComponent: () => hop().then((m) => m.HopLoginComponent) },
  { path: 'forgot-password', loadComponent: () => hop().then((m) => m.HopForgotPasswordComponent) },
  { path: 'reset-password', loadComponent: () => hop().then((m) => m.HopResetPasswordComponent) },
  { path: 'auth/sso/complete', loadComponent: () => hop().then((m) => m.HopSSOCallbackComponent) },
  { path: 'invite/:token', loadComponent: () => hop().then((m) => m.HopAcceptInvitationComponent) },
  {
    path: '',
    canActivate: [hopAuthGuard],
    loadComponent: () => import('./shell/shell').then((m) => m.Shell),
    children: [
      { path: 'sites', loadComponent: () => import('./sites/sites-page').then((m) => m.SitesPage) },
      {
        path: 'audits',
        loadComponent: () => import('./audits/audits-page').then((m) => m.AuditsPage),
      },
      // hop-core's pages, mounted as-is.
      { path: 'agents', children: HOP_AGENT_ROUTES },
      { path: 'credentials', loadComponent: () => hop().then((m) => m.HopCredentialsComponent) },
      { path: 'account', loadComponent: () => hop().then((m) => m.HopAccountComponent) },
      {
        path: 'admin',
        canActivate: [hopAdminGuard],
        loadComponent: () => hop().then((m) => m.HopAdminComponent),
      },
      { path: '', pathMatch: 'full', redirectTo: 'sites' },
    ],
  },
  { path: '**', redirectTo: '' },
];
