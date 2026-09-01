'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { Shell } from '@/components/Shell';
import { SearchBox } from '@/components/SearchBox';

type Report = {
  id: string;
  title: string;
  summary: string;
  status: string;
  tags?: string[];
  updated_at?: string | null;
};

export default function ReportsPage() {
  const [items, setItems] = useState<Report[]>([]);
  const [q, setQ] = useState('');
  const [err, setErr] = useState('');
  const load = async (query?: string) => {
    const qs = query ? `?q=${encodeURIComponent(query)}` : '';
    const res = await api<{ items: Report[] }>(`/api/v1/reports${qs}`);
    setItems(res.data.items || []);
  };
  useEffect(() => {
    void load().catch((e) => setErr(e instanceof Error ? e.message : '请先登录'));
  }, []);
  return (
    <Shell>
      <h1 className="mb-3 text-[20px] font-semibold">报告库</h1>
      <form
        className="mb-4 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void load(q).catch((ex) => setErr(ex instanceof Error ? ex.message : '检索失败'));
        }}
      >
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="按标题 / 摘要过滤" />
        <button type="submit" className="shrink-0">
          过滤
        </button>
      </form>
      <div className="mb-6 card p-4">
        <p className="mb-2 text-xs text-muted">语义检索（含插件与报告向量）</p>
        <SearchBox placeholder="例如：MCP 文件系统" />
      </div>
      {err && <p className="mb-3 text-sm text-danger">{err}</p>}
      <div className="grid gap-3">
        {items.length === 0 && <p className="card border-dashed p-6 text-sm text-muted">还没有报告。打开插件详情生成商业拆解。</p>}
        {items.map((r) => (
          <Link key={r.id} href={`/reports/${r.id}`} className="card block p-4">
            <h2 className="font-semibold text-white">{r.title}</h2>
            <p className="mt-1 text-sm text-muted">{r.summary}</p>
            <p className="mt-2 text-xs text-accent">
              {r.status} · {(r.tags || []).join(' / ')}
            </p>
          </Link>
        ))}
      </div>
    </Shell>
  );
}
