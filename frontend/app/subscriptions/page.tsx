'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { Shell } from '@/components/Shell';
import { SubscriptionForm, type SubscriptionInput } from '@/components/SubscriptionForm';

type Sub = {
  subscription_id: string;
  name: string;
  frequency: string;
  channel: string;
  is_active: boolean;
};

export default function SubsPage() {
  const [items, setItems] = useState<Sub[]>([]);
  const [msg, setMsg] = useState('');
  const load = () =>
    api<{ items: Sub[] }>('/api/v1/subscriptions').then((r) => setItems(r.data.items || []));
  useEffect(() => {
    void load().catch((e) => setMsg(e.message));
  }, []);
  const onSubmit = async (data: SubscriptionInput) => {
    await api('/api/v1/subscriptions', { method: 'POST', body: JSON.stringify(data) });
    setMsg('已创建');
    await load();
  };
  return (
    <Shell>
      <h1 className="mb-4 text-2xl font-bold">情报订阅</h1>
      <SubscriptionForm onSubmit={onSubmit} />
      {msg && <p className="my-2 text-sm">{msg}</p>}
      <div className="mt-6 space-y-2">
        {items.map((s) => (
          <Link key={s.subscription_id} href={`/subscriptions/${s.subscription_id}`} className="block rounded-xl border border-line bg-panel p-3">
            <strong>{s.name}</strong>
            <span className="ml-3 text-sm text-slate-400">
              {s.frequency} · {s.channel} · {s.is_active ? '启用' : '暂停'}
            </span>
          </Link>
        ))}
      </div>
    </Shell>
  );
}
