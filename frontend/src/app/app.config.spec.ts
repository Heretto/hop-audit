import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { appConfig } from './app.config';

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
});
