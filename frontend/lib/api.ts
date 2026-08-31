export const API = '';

export async function api<T>(path: string, init?: RequestInit): Promise<{ code: number; data: T; message: string }> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('sr_token') : null;
  const headers = new Headers(init?.headers);
  headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const res = await fetch(`${API}${path}`, { ...init, headers });
  const body = await res.json().catch(() => ({ code: res.status, data: null, message: res.statusText }));
  const detail = typeof body.detail === 'string' ? body.detail : '';
  if (!res.ok) {
    throw new Error(body.message || detail || `HTTP ${res.status}`);
  }
  if (body.code && body.code !== 0) {
    throw new Error(body.message || detail || 'request failed');
  }
  return body;
}

export function saveToken(token: string) {
  localStorage.setItem('sr_token', token);
}

export function clearToken() {
  localStorage.removeItem('sr_token');
}
