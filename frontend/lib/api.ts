export const API = '';

const TOKEN_KEY = 'sr_token';

export function readToken(): string {
  if (typeof window === 'undefined') return '';
  const fromStore = window.localStorage.getItem(TOKEN_KEY) || '';
  if (fromStore) return fromStore;
  const match = document.cookie.match(/(?:^|; )sr_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : '';
}

export async function api<T>(path: string, init?: RequestInit): Promise<{ code: number; data: T; message: string }> {
  const token = readToken();
  const headers = new Headers(init?.headers);
  if (!headers.has('Content-Type') && init?.body) {
    headers.set('Content-Type', 'application/json');
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
    headers.set('X-SkillRadar-Token', token);
  }
  const res = await fetch(`${API}${path}`, { ...init, headers, credentials: 'include' });
  const body = await res.json().catch(() => ({ code: res.status, data: null, message: res.statusText }));
  const detail = typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? JSON.stringify(body.detail) : '';
  if (!res.ok) {
    throw new Error(body.message || detail || `HTTP ${res.status}`);
  }
  if (body.code && body.code !== 0) {
    throw new Error(body.message || detail || 'request failed');
  }
  return body;
}

export function saveToken(token: string) {
  if (typeof window === 'undefined') return;
  localStorage.setItem(TOKEN_KEY, token);
  document.cookie = `sr_token=${encodeURIComponent(token)}; Path=/; SameSite=Lax; Max-Age=604800`;
}

export function clearToken() {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(TOKEN_KEY);
  document.cookie = 'sr_token=; Path=/; Max-Age=0';
}
