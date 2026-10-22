import { HOP_AGENT_ROUTES, hopAdminGuard, hopAuthGuard } from '@heretto/hop-ui';
import { routes } from './app.routes';

describe('routes', () => {
  const shell = routes.find((r) => r.path === '')!;
  const child = (path: string) => shell.children!.find((r) => r.path === path);

  it('keeps sign-in pages outside the shell', () => {
    for (const path of [
      'login',
      'forgot-password',
      'reset-password',
      'auth/sso/complete',
      'invite/:token',
    ]) {
      expect(routes.some((r) => r.path === path)).toBe(true);
    }
  });

  it('guards the shell with authentication', () => {
    expect(shell.canActivate).toEqual([hopAuthGuard]);
  });

  it('mounts hop-core pages as-is', () => {
    expect(child('agents')?.children).toBe(HOP_AGENT_ROUTES);
    expect(child('credentials')?.loadComponent).toBeDefined();
    expect(child('account')?.loadComponent).toBeDefined();
    expect(child('admin')?.canActivate).toEqual([hopAdminGuard]);
  });

  it('opens on Sites', () => {
    expect(child('sites')?.loadComponent).toBeDefined();
    expect(child('audits')?.loadComponent).toBeDefined();
    expect(shell.children!.find((r) => r.path === '' && r.redirectTo)?.redirectTo).toBe('sites');
  });
});
