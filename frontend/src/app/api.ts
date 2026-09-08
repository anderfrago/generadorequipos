import { Injectable, signal } from '@angular/core';

export interface User {id: string; name: string; email: string; role: 'ADMIN' | 'TEACHER'}

@Injectable({providedIn: 'root'})
export class Api {
  user = signal<User | null>(null);
  csrf = '';
  async session() {
    const data = await this.request<{user: User | null; csrf: string}>('/session');
    this.csrf = data.csrf;
    this.user.set(data.user);
  }
  async request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
    const response = await fetch('/api' + path, {
      method, credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': this.csrf},
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'No se pudo completar la operación.');
    return data as T;
  }
}
