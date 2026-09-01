'use client';

import { useEffect, useState } from 'react';
import { Shell } from '@/components/Shell';
import { desktop } from '@/lib/desktop';
import { api } from '@/lib/api';

type Health = {
  status?: string;
  version?: string;
  graph?: { backend?: string; connected?: boolean; nodes?: number | null };
  vector?: { backend?: string; connected?: boolean; points?: number };
  objects?: { backend?: string; connected?: boolean };
  message?: string;
};

type Llm = {
  id: string;
  name: string;
  provider: string;
  model_name: string;
  is_default: boolean;
  has_api_key: boolean;
};
type Channel = { id: string; name: string; channel_type: string; is_default: boolean };

export default function SettingsPage() {
  const [tab, setTab] = useState<'status' | 'llm' | 'channels'>('status');
  const [health, setHealth] = useState<Health | null>(null);
  const [llms, setLlms] = useState<Llm[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const desk = desktop();

  const load = async () => {
    const h = await fetch('/api/v1/health').then((r) => r.json());
    setHealth(h);
    try {
      const l = await api<{ items: Llm[] }>('/api/v1/configs/llm');
      setLlms(l.data.items || []);
      const c = await api<{ items: Channel[] }>('/api/v1/configs/channels');
      setChannels(c.data.items || []);
    } catch {
      /* not logged in */
    }
  };

  useEffect(() => {
    void load().catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <Shell>
      <h1 className="mb-3 text-[20px] font-semibold">设置</h1>
      <div className="mb-4 flex gap-2">
        <button className={tab === 'status' ? '' : 'ghost'} onClick={() => setTab('status')}>
          运行状态
        </button>
        <button className={tab === 'llm' ? '' : 'ghost'} onClick={() => setTab('llm')}>
          大模型
        </button>
        <button className={tab === 'channels' ? '' : 'ghost'} onClick={() => setTab('channels')}>
          渠道
        </button>
      </div>
      {err && <p className="mb-3 text-sm text-danger">{err}</p>}
      {msg && <p className="mb-3 text-sm text-accent">{msg}</p>}
      {tab === 'status' && (
        <div>
          <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Card label="运行形态" value={desk ? 'Electron 桌面' : '浏览器'} hint={health?.version} />
            <Card label="图存储" value={health?.graph?.backend || '…'} hint={health?.graph?.connected ? '在线' : '降级'} />
            <Card label="向量" value={health?.vector?.backend || '…'} hint={`${health?.vector?.points ?? 0} 点`} />
            <Card label="对象存储" value={health?.objects?.backend || '…'} hint={health?.objects?.connected ? '在线' : ''} />
          </div>
          <pre className="card p-3 text-xs">{JSON.stringify(health, null, 2)}</pre>
          <p className="mt-3 text-xs text-muted">
            API Key / Webhook 加密存储。密钥写在 <code className="text-accent">.env</code>，不要贴进聊天。
          </p>
        </div>
      )}
      {tab === 'llm' && (
        <LlmPanel
          items={llms}
          onSaved={() => void load()}
          onMsg={setMsg}
        />
      )}
      {tab === 'channels' && (
        <ChannelPanel items={channels} onSaved={() => void load()} onMsg={setMsg} />
      )}
    </Shell>
  );
}

function Card({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="card px-4 py-3">
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div className="text-lg font-semibold text-white">{value}</div>
      {hint && <div className="text-xs text-accent">{hint}</div>}
    </div>
  );
}

function LlmPanel({ items, onSaved, onMsg }: { items: Llm[]; onSaved: () => void; onMsg: (s: string) => void }) {
  const [name, setName] = useState('默认 GPT');
  const [model, setModel] = useState('gpt-4o');
  const [base, setBase] = useState('https://api.openai.com/v1');
  const [key, setKey] = useState('');
  return (
    <div className="space-y-3">
      <form
        className="card space-y-2 p-4"
        onSubmit={(e) => {
          e.preventDefault();
          void api('/api/v1/configs/llm', {
            method: 'POST',
            body: JSON.stringify({ name, provider: 'openai', model_name: model, base_url: base, api_key: key, is_default: true }),
          })
            .then(() => {
              onMsg('已保存大模型配置');
              setKey('');
              onSaved();
            })
            .catch((ex) => onMsg(ex instanceof Error ? ex.message : '保存失败'));
        }}
      >
        <label>名称<input value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label>模型<input value={model} onChange={(e) => setModel(e.target.value)} /></label>
        <label>Base URL<input value={base} onChange={(e) => setBase(e.target.value)} /></label>
        <label>API Key<input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="不会回显明文" /></label>
        <button type="submit">保存为默认</button>
      </form>
      {items.map((it) => (
        <div key={it.id} className="card flex items-center justify-between p-3 text-sm">
          <div>
            <strong>{it.name}</strong>
            <p className="text-xs text-muted">
              {it.provider} · {it.model_name}
              {it.is_default ? ' · 默认' : ''}
              {it.has_api_key ? ' · Key 已加密' : ''}
            </p>
          </div>
          <button
            className="ghost text-xs"
            onClick={() =>
              void api(`/api/v1/configs/llm/${it.id}/test`, { method: 'POST' })
                .then((r: any) => onMsg(r.data?.ok ? '连接成功' : r.data?.message || r.message))
                .catch((ex) => onMsg(ex instanceof Error ? ex.message : '测试失败'))
            }
          >
            测试连接
          </button>
        </div>
      ))}
    </div>
  );
}

function ChannelPanel({
  items,
  onSaved,
  onMsg,
}: {
  items: Channel[];
  onSaved: () => void;
  onMsg: (s: string) => void;
}) {
  const [ctype, setCtype] = useState<'feishu' | 'wecom' | 'email'>('feishu');
  const [name, setName] = useState('飞书机器人');
  const [webhook, setWebhook] = useState('');
  const [email, setEmail] = useState('');
  return (
    <div className="space-y-3">
      <form
        className="card space-y-2 p-4"
        onSubmit={(e) => {
          e.preventDefault();
          void api('/api/v1/configs/channels', {
            method: 'POST',
            body: JSON.stringify({
              name,
              channel_type: ctype,
              webhook_url: webhook || undefined,
              email: email || undefined,
              is_default: true,
            }),
          })
            .then(() => {
              onMsg('渠道已保存');
              onSaved();
            })
            .catch((ex) => onMsg(ex instanceof Error ? ex.message : '保存失败'));
        }}
      >
        <select value={ctype} onChange={(e) => setCtype(e.target.value as typeof ctype)}>
          <option value="feishu">飞书</option>
          <option value="wecom">企业微信</option>
          <option value="email">邮件</option>
        </select>
        <label>名称<input value={name} onChange={(e) => setName(e.target.value)} /></label>
        {ctype !== 'email' ? (
          <label>Webhook<input value={webhook} onChange={(e) => setWebhook(e.target.value)} /></label>
        ) : (
          <label>收件人<input value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        )}
        <button type="submit">保存渠道</button>
      </form>
      {items.map((it) => (
        <div key={it.id} className="card flex items-center justify-between p-3 text-sm">
          <div>
            <strong>{it.name}</strong>
            <p className="text-xs text-muted">
              {it.channel_type}
              {it.is_default ? ' · 默认' : ''}
            </p>
          </div>
          <button
            className="ghost text-xs"
            onClick={() =>
              void api(`/api/v1/configs/channels/${it.id}/test`, { method: 'POST' })
                .then((r: any) => onMsg(r.data?.ok ? '发送成功' : r.data?.error || r.message))
                .catch((ex) => onMsg(ex instanceof Error ? ex.message : '测试失败'))
            }
          >
            测试发送
          </button>
        </div>
      ))}
    </div>
  );
}