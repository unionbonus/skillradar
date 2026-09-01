'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Markdown from 'react-markdown';
import { api } from '@/lib/api';
import { Shell } from '@/components/Shell';

type Hist = { id: number; sent_at: string; status: string; error_message?: string; content: string };

export default function SubDetailPage() {
  const params = useParams<{ id: string }>();
  const [sub, setSub] = useState<any>(null);
  const [hist, setHist] = useState<Hist[]>([]);
  const [open, setOpen] = useState<Hist | null>(null);
  const id = params.id;
  const load = async () => {
    const s = await api(`/api/v1/subscriptions/${id}`);
    setSub(s.data);
    const h = await api<{ items: Hist[] }>(`/api/v1/subscriptions/${id}/history`);
    setHist(h.data.items || []);
  };
  useEffect(() => {
    void load();
  }, [id]);
  return (
    <Shell>
      <h1 className="mb-2 text-2xl font-bold">{sub?.name || '订阅详情'}</h1>
      <p className="mb-3 text-sm text-slate-400">
        {sub?.frequency} · {sub?.channel} · {sub?.is_active ? '启用' : '暂停'}
      </p>
      <div className="mb-4 flex gap-2">
        <button onClick={() => void api(`/api/v1/subscriptions/${id}/send-test`, { method: 'POST' }).then(() => load())}>
          发送测试简报
        </button>
      </div>
      <h2 className="mb-2 font-semibold">发送历史</h2>
      <div className="space-y-2">
        {hist.map((h) => (
          <button key={h.id} className="ghost block w-full text-left" onClick={() => setOpen(h)}>
            {h.sent_at} · {h.status} {h.error_message ? `· ${h.error_message}` : ''}
          </button>
        ))}
      </div>
      {open && (
        <article className="mt-4 rounded-xl border border-line bg-panel p-4">
          <Markdown>{open.content}</Markdown>
          <button
            className="mt-3 ghost"
            onClick={() => void api(`/api/v1/subscriptions/${id}/resend/${open.id}`, { method: 'POST' })}
          >
            重发
          </button>
        </article>
      )}
    </Shell>
  );
}
