import { NextRequest } from 'next/server';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const HOP = new Set([
  'connection',
  'content-encoding',
  'content-length',
  'host',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
]);

function backendBase() {
  return (process.env.BACKEND_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
}

function pickToken(req: NextRequest): string {
  const x = req.headers.get('x-skillradar-token')?.trim() || '';
  if (x) return x;
  const auth = req.headers.get('authorization') || '';
  if (auth.toLowerCase().startsWith('bearer ')) {
    const raw = auth.slice(7).trim();
    if (raw) return raw;
  }
  return req.cookies.get('sr_token')?.value?.trim() || '';
}

async function proxy(req: NextRequest, ctx: { params: { path: string[] } | Promise<{ path: string[] }> }) {
  const params = await ctx.params;
  const suffix = (params.path || []).join('/');
  const incoming = new URL(req.url);
  const target = `${backendBase()}/api/v1/${suffix}${incoming.search}`;
  const token = pickToken(req);
  const headers = new Headers();
  const contentType = req.headers.get('content-type');
  if (contentType) headers.set('Content-Type', contentType);
  const accept = req.headers.get('accept');
  if (accept) headers.set('Accept', accept);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
    headers.set('X-SkillRadar-Token', token);
  }
  const cookie = req.headers.get('cookie');
  if (cookie) headers.set('Cookie', cookie);

  const init: RequestInit = { method: req.method, headers, redirect: 'manual' };
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    init.body = await req.arrayBuffer();
  }
  const upstream = await fetch(target, init);
  const out = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP.has(key.toLowerCase())) out.set(key, value);
  });
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
