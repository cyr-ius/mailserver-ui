import { ChangeDetectionStrategy, Component, computed, effect, inject, OnInit, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

@Component({
  selector: 'app-about',
  imports: [],
  templateUrl: './about.html',
  styleUrl: './about.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class About implements OnInit {
  private readonly http = inject(HttpClient);

  protected readonly appVersion = signal('Development');
  protected readonly checkingUpdate = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly latestRelease = signal<any | null>(null);

  protected readonly repo = signal('cyr-ius/mailserver-ui');
  protected readonly repoUrl = computed(() => `https://github.com/${this.repo()}`);
  protected readonly issueUrl = computed(
    () =>
      `https://github.com/${this.repo()}/issues/new?title=${encodeURIComponent('[Bug] ')}&body=${encodeURIComponent(
        `Version: ${this.appVersion() }\n\nDescribe the issue:\n`,
      )}`,
  );

  protected readonly updateAvailable = computed(() => {
    const tag = this.latestRelease()?.tag_name ?? '';
    return tag ? this.isNewerVersion(tag, this.appVersion()) : false;
  });

  ngOnInit(): void {
    effect(() => {
      // If repo is configured, attempt to auto-check once on mount.
      // Do not block rendering; call checkForUpdate lazily.
      void this.loadVersion();
    });
  }

  private async loadVersion(): Promise<void> {
    try {
      const res: any = await firstValueFrom(this.http.get('/api/health'));
      this.appVersion.set(res?.version ?? 'Development');
    } catch {
      this.appVersion.set('Development');
    }
  }

  protected async checkForUpdate(): Promise<void> {
    this.checkingUpdate.set(true);
    this.error.set(null);
    this.latestRelease.set(null);
    try {
      const resp = await fetch(`https://api.github.com/repos/${this.repo()}/releases/latest`, {
        headers: { Accept: 'application/vnd.github.v3+json' },
      });
      if (!resp.ok) throw new Error('GitHub API');
      const data = await resp.json();
      this.latestRelease.set(data);
    } catch (err) {
      this.error.set('Unable to check latest release on GitHub.');
    } finally {
      this.checkingUpdate.set(false);
    }
  }

  private normalizeVersion(version: string): number[] {
    return version
      .replace(/^v/i, '')
      .split('.')
      .map((part) => Number.parseInt(part.replace(/\D.*/, ''), 10))
      .filter((part) => Number.isFinite(part));
  }

  private isNewerVersion(remote: string, local: string): boolean {
    const r = this.normalizeVersion(remote);
    const l = this.normalizeVersion(local);
    const maxLength = Math.max(r.length, l.length);
    for (let i = 0; i < maxLength; i += 1) {
      const rv = r[i] ?? 0;
      const lv = l[i] ?? 0;
      if (rv > lv) return true;
      if (rv < lv) return false;
    }
    return false;
  }
}
