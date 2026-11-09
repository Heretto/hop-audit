import { ChangeDetectionStrategy, Component, inject, OnInit } from '@angular/core';
import { HopMainLayoutComponent, NavItem } from '@heretto/hop-ui';
import { LOGO_SRC } from '../app.config';
import { SetupService } from '../shared/setup.service';

/** Sidebar per Nav.dc.html; hop-core appends Account and Administration. */
export const NAV_ITEMS: NavItem[] = [
  { label: 'Sites', route: '/sites', icon: 'language' },
  { label: 'Agents', route: '/agents', icon: 'smart_toy' },
  { label: 'Credentials', route: '/credentials', icon: 'key' },
];

@Component({
  selector: 'app-shell',
  imports: [HopMainLayoutComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<hop-main-layout appTitle="HOP Audit" [logoSrc]="logo" [navItems]="navItems" />`,
})
export class Shell implements OnInit {
  readonly navItems = NAV_ITEMS;
  readonly logo = LOGO_SRC;
  private setup = inject(SetupService);

  ngOnInit(): void {
    // Seeds the organization's agents on first sign-in. A failure only means
    // the Agents page starts empty, so it is logged rather than shown.
    this.setup.ensure().subscribe({ error: (e) => console.error('Organization setup failed', e) });
  }
}
