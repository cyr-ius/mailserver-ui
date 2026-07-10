import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ThemeService } from '../../core/theme.service';
import { ThemeToggle } from './theme-toggle';

describe('ThemeToggle', () => {
  let fixture: ComponentFixture<ThemeToggle>;
  let theme: ThemeService;

  const el = () => fixture.nativeElement as HTMLElement;
  const trigger = () => el().querySelector('.theme-toggle-trigger') as HTMLButtonElement;
  const triggerIcon = () => trigger().querySelector('i') as HTMLElement;
  const items = () => Array.from(el().querySelectorAll('.dropdown-item')) as HTMLButtonElement[];

  beforeEach(async () => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-bs-theme');

    await TestBed.configureTestingModule({ imports: [ThemeToggle] }).compileComponents();

    theme = TestBed.inject(ThemeService);
    fixture = TestBed.createComponent(ThemeToggle);
    fixture.detectChanges();
  });

  it('keeps the static `bi` class alongside the bound icon class', () => {
    const classes = triggerIcon().classList;
    expect(classes.contains('bi')).toBe(true);
    expect(classes.contains('bi-sun-fill')).toBe(true);
  });

  it('offers light, dark and system, marking the active one', () => {
    expect(items().map((item) => item.textContent?.trim())).toEqual(['Light', 'Dark', 'System']);
    expect(items()[2].classList.contains('active')).toBe(true);
  });

  it('applies the picked mode to the document and the trigger', () => {
    items()[1].click();
    fixture.detectChanges();

    expect(theme.themeMode()).toBe('dark');
    expect(document.documentElement.getAttribute('data-bs-theme')).toBe('dark');
    expect(triggerIcon().classList.contains('bi-moon-stars-fill')).toBe(true);
    expect(items()[1].classList.contains('active')).toBe(true);
  });

  it('persists the choice across service instances', () => {
    items()[0].click();
    fixture.detectChanges();

    expect(localStorage.getItem('mailserver-ui-theme')).toBe('light');
  });
});
