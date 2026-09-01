'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';

type Hit = {
  id: number;
  full_name: string;
  description?: string;
  fingerprint_type?: string | null;
  source?: string;
  score?: number;
};

export function SearchBox({ placeholder = '搜索插件、关键词、报告…' }: { placeholder?: string }) {
  const [q, setQ] = useState('');
  const [items, setItems] = useState<Hit[]>([]);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const run = async (e?: FormEvent) => {
    e?.preventDefault();
    const query = q.trim();
    if (!query) return;
    setBusy(true);
    setErr('');
    try {
      const res = await api<{ items: Hit[] }>(`/api/v1/search?q=${encodeURIComponent(query)}&limit=8`);
      setItems(res.data.items || []);
      if (!(res.data.items || []).length) setErr('没有命中，先扫描或拆解一些插件');
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : '请先登录后再检索');
    } finally {
      setBusy(false);
    }
  };
  return (
    <div>
      <form className="flex gap-2" onSubmit={(e) => void run(e)}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} aria-label="语义检索" />
        <button type="submit" disabled={busy} className="shrink-0">
          检索
        </button>
      </form>
      {err && <p className="mt-2 text-sm text-muted">{err}</p>}
      {items.length > 0 && (
        <ul className="mt-3 space-y-2">
          {items.map((it) => (
            <li key={it.id} className="card p-3">
              <Link href={`/plugins/${it.id}`} className="font-medium text-white">
                {it.full_name}
              </Link>
              <p className="text-xs text-muted">
                {it.source || 'github'} · {it.fingerprint_type || '未分类'}
                {typeof it.score === 'number' ? ` · ${it.score.toFixed(2)}` : ''}
              </p>
              <p className="text-sm text-slate-300">{it.description}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
