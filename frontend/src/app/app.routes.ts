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
        path: 'sites/new',
        loadComponent: () => import('./sites/settings/site-settings').then((m) => m.SiteSettings),
      },
      {
        path: 'sites/:id/edit',
        loadComponent: () => import('./sites/settings/site-settings').then((m) => m.SiteSettings),
      },
      {
        path: 'sites/:id/run',
        loadComponent: () => import('./runs/run-audit/run-audit').then((m) => m.RunAudit),
      },
      {
        path: 'audits',
        loadComponent: () => import('./runs/audits-page').then((m) => m.AuditsPage),
      },
      {
        path: 'audits/:runId',
        loadComponent: () => import('./runs/audit/audit-page').then((m) => m.AuditPage),
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
