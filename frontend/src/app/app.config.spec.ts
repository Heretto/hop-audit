import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { HopLoginComponent } from '@heretto/hop-ui';
import { appConfig, LOGIN, LOGO_SRC } from './app.config';

@Component({
  imports: [MatFormFieldModule, MatInputModule],
  template: `<mat-form-field><mat-label>Name</mat-label><input matInput /></mat-form-field>`,
})
class Field {}

describe('appConfig', () => {
  it('makes form fields outlined by default, the only appearance hop-ui styles', () => {
    TestBed.configureTestingModule({ imports: [Field], providers: appConfig.providers });
    const fixture = TestBed.createComponent(Field);
    fixture.detectChanges();
    const field = fixture.nativeElement.querySelector('.mat-mdc-form-field');
    expect(field.classList).toContain('mat-form-field-appearance-outline');
    expect(field.querySelector('.mdc-text-field--filled')).toBeNull();
  });

  it("brands the sign-in page with HOP Audit's name, mark and tagline", () => {
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideRouter([])],
    });
    const fixture = TestBed.createComponent(HopLoginComponent);
    fixture.detectChanges();
    const login = fixture.componentInstance;
    expect(login.resolvedAppName).toBe(LOGIN.appName);
    expect(login.resolvedSubtitle).toBe(LOGIN.subtitle);
    expect(login.resolvedLogoSrc).toBe(LOGO_SRC);
    const text = fixture.nativeElement.textContent;
    expect(text).toContain('HOP Audit');
    expect(text).toContain(LOGIN.subtitle);
    const logos = [...fixture.nativeElement.querySelectorAll('img')] as HTMLImageElement[];
    expect(logos.some((img) => img.getAttribute('src') === LOGO_SRC)).toBe(true);
  });
});
