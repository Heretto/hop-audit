import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { HOP_LOGIN_CONFIG, HOP_LOGO_SRC, hopAuthInterceptor, provideHopUi } from '@heretto/hop-ui';
import { routes } from './app.routes';

/** The sign-in page's brand: the same mark and name as the top bar. */
export const LOGIN = {
  appName: 'HOP Audit',
  subtitle: 'Audit documentation sites and help centers.',
};
export const LOGO_SRC = 'hop-audit-mark.svg';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withInterceptors([hopAuthInterceptor])),
    // Outlined form fields, the only appearance hop-ui styles.
    provideHopUi(),
    { provide: HOP_LOGIN_CONFIG, useValue: LOGIN },
    { provide: HOP_LOGO_SRC, useValue: LOGO_SRC },
  ],
};
