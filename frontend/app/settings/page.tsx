'use client';

import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import { Shell } from '@/components/Shell';
import { api } from '@/lib/api';
import { desktop } from '@/lib/desktop';

type Health = {
  status?: string;
  version?: string;
  graph?: { backend?: string; connected?: boolean; nodes?: number | null };
};
type LLM = {
  id: string;
  name: string;
  provider: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
  is_default: boolean;
  api_key_masked?: string;
  has_api_key?: boolean;
  base_url?: string | null;
};
type Channel = {
  id: string;
  name: string;
  channel_type: string;
  webhook_url_masked?: string;
  smtp_host?: string;
  smtp_port?: number;
  from_email?: string;
  to_email?: string;
  is_default: boolean;
};

const TABS = [
  { id: 'system', label: '系统' },
  { id: 'llm', label: '大模型' },
  { id: 'channels', label: '渠道' },
] as const;

export default function SettingsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]['id']>('llm');
  const [channelTab, setChannelTab] = useState<'feishu' | 'wecom' | 'email'>('feishu');
  const [health, setHealth] = useState<Health | null>(null);
  const [llms, setLlms] = useState<LLM[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [msg, setMsg] = useState('');
  const desk = desktop();

  const load = async () => {
    const h = await fetch('/api/v1/health').then((r) => r.json());
    setHealth(h);
    try {
      const l = await api<{ items: LLM[] }>('/api/v1/configs/llm');
      setLlms(l.data.items || []);
      const c = await api<{ items: Channel[] }>('/api/v1/configs/channels');
      setChannels(c.data.items || []);
    } catch {
      /* unauthenticated */
    }
  };

  useEffect(() => {
    void load().catch((e) => setMsg(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <Shell>
      <p className="mb-1 text-xs uppercase tracking-[0.18em] text-accent">Connection OS</p>
      <h1 className="display mb-4 text-3xl font-semibold text-white">系统设置</h1>
      <div className="mb-5 flex gap-2 overflow-x-auto">
        {TABS.map((t) => (
          <button key={t.id} className={tab === t.id ? '' : 'ghost'} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      {msg && <p className="mb-3 text-sm text-danger">{msg}</p>}
      {tab === 'system' && (
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <Stat label="运行" value={desk ? 'Electron' : '浏览器'} hint={health?.version} />
            <Stat label="服务" value={health?.status || '…'} />
            <Stat label="图存储" value={health?.graph?.backend || '…'} hint={health?.graph?.connected ? '在线' : '降级'} />
          </div>
          <p className="text-sm text-muted">
            API Key 与 Webhook 使用 AES-256-GCM 加密。管理员级 GitHub Token / Qdrant 仍放在
            <code className="text-accent"> .env</code>。
          </p>
          <Link href="/help">
            <button className="ghost">打开手册</button>
          </Link>
        </div>
      )}
      {tab === 'llm' && <LLMPanel items={llms} onChange={() => void load()} setMsg={setMsg} />}
      {tab === 'channels' && (
        <div>
          <div className="mb-4 flex gap-2">
            {(['feishu', 'wecom', 'email'] as const).map((id) => (
              <button key={id} className={channelTab === id ? '' : 'ghost'} onClick={() => setChannelTab(id)}>
                {id === 'feishu' ? '飞书' : id === 'wecom' ? '企业微信' : '邮件'}
              </button>
            ))}
          </div>
          <ChannelPanel type={channelTab} items={channels.filter((c) => c.channel_type === channelTab)} onChange={() => void load()} setMsg={setMsg} />
        </div>
      )}
    </Shell>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="sr-card px-4 py-3">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className="text-lg font-semibold text-white">{value}</div>
      {hint && <div className="text-xs text-accent">{hint}</div>}
    </div>
  );
}

function LLMPanel({ items, onChange, setMsg }: { items: LLM[]; onChange: () => void; setMsg: (s: string) => void }) {
  const [form, setForm] = useState({
    name: 'GPT-4o 默认',
    provider: 'openai',
    api_key: '',
    base_url: '',
    model_name: 'gpt-4o',
    temperature: 0.7,
    max_tokens: 4096,
    is_default: true,
  });
  const save = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api('/api/v1/configs/llm', { method: 'POST', body: JSON.stringify(form) });
      setMsg('已保存大模型配置');
      onChange();
    } catch (ex) {
      setMsg(ex instanceof Error ? ex.message : '保存失败');
    }
  };
  const test = async (id: string) => {
    const r = await api<{ ok: boolean; error?: string; reply?: string }>(`/api/v1/configs/llm/${id}/test`, { method: 'POST' });
    setMsg(r.data.ok ? `连接成功：${r.data.reply || 'ok'}` : `连接失败：${r.data.error}`);
  };
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <form onSubmit={(e) => void save(e)} className="sr-card space-y-3 p-4">
        <label>名称<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label>
          提供商
          <select value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })}>
            <option value="openai">OpenAI 兼容</option>
            <option value="anthropic">Anthropic</option>
            <option value="azure">Azure</option>
            <option value="custom">自定义 / 本地</option>
          </select>
        </label>
        <label>API Key<input type="password" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} placeholder="不会回显明文" /></label>
        <label>Base URL<input value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} placeholder="可选，本地模型填 v1 地址" /></label>
        <label>模型<input value={form.model_name} onChange={(e) => setForm({ ...form, model_name: e.target.value })} /></label>
        <div className="grid grid-cols-2 gap-3">
          <label>温度<input type="number" step="0.1" value={form.temperature} onChange={(e) => setForm({ ...form, temperature: Number(e.target.value) })} /></label>
          <label>Max tokens<input type="number" value={form.max_tokens} onChange={(e) => setForm({ ...form, max_tokens: Number(e.target.value) })} /></label>
        </div>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input className="w-auto min-h-0" type="checkbox" checked={form.is_default} onChange={(e) => setForm({ ...form, is_default: e.target.checked })} />
          设为默认
        </label>
        <button type="submit">保存配置</button>
      </form>
      <div className="space-y-2">
        {items.length === 0 && <p className="text-sm text-muted">还没有大模型配置。</p>}
        {items.map((row) => (
          <div key={row.id} className="sr-card p-3">
            <div className="flex items-center justify-between gap-2">
              <strong>{row.name}</strong>
              {row.is_default && <span className="text-[11px] text-accent">默认</span>}
            </div>
            <p className="text-xs text-muted">
              {row.provider} · {row.model_name} · {row.api_key_masked || '未填密钥'}
            </p>
            <div className="mt-2 flex gap-2">
              <button className="flex-1 text-xs" onClick={() => void test(row.id)}>测试连接</button>
              <button
                className="ghost flex-1 text-xs"
                onClick={() => void api(`/api/v1/configs/llm/${row.id}`, { method: 'DELETE' }).then(onChange)}
              >
                删除
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ChannelPanel({
  type,
  items,
  onChange,
  setMsg,
}: {
  type: 'feishu' | 'wecom' | 'email';
  items: Channel[];
  onChange: () => void;
  setMsg: (s: string) => void;
}) {
  const [form, setForm] = useState({
    name: type === 'feishu' ? '公司飞书群' : type === 'wecom' ? '企微机器人' : '情报邮箱',
    webhook_url: '',
    secret: '',
    smtp_host: '',
    smtp_port: 587,
    smtp_user: '',
    smtp_password: '',
    from_email: '',
    to_email: '',
    is_default: true,
  });
  const save = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api('/api/v1/configs/channels', {
        method: 'POST',
        body: JSON.stringify({ ...form, channel_type: type }),
      });
      setMsg('已保存渠道配置');
      onChange();
    } catch (ex) {
      setMsg(ex instanceof Error ? ex.message : '保存失败');
    }
  };
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <form onSubmit={(e) => void save(e)} className="sr-card space-y-3 p-4">
        <label>名称<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        {type !== 'email' ? (
          <>
            <label>Webhook URL<input value={form.webhook_url} onChange={(e) => setForm({ ...form, webhook_url: e.target.value })} placeholder={type === 'feishu' ? 'https://open.feishu.cn/...' : 'https://qyapi.weixin.qq.com/...key='} /></label>
            {type === 'feishu' && (
              <label>签名密钥（可选）<input type="password" value={form.secret} onChange={(e) => setForm({ ...form, secret: e.target.value })} /></label>
            )}
          </>
        ) : (
          <>
            <label>SMTP 服务器<input value={form.smtp_host} onChange={(e) => setForm({ ...form, smtp_host: e.target.value })} /></label>
            <label>端口<input type="number" value={form.smtp_port} onChange={(e) => setForm({ ...form, smtp_port: Number(e.target.value) })} /></label>
            <label>用户名<input value={form.smtp_user} onChange={(e) => setForm({ ...form, smtp_user: e.target.value })} /></label>
            <label>密码<input type="password" value={form.smtp_password} onChange={(e) => setForm({ ...form, smtp_password: e.target.value })} /></label>
            <label>发件人<input value={form.from_email} onChange={(e) => setForm({ ...form, from_email: e.target.value })} /></label>
            <label>收件人<input value={form.to_email} onChange={(e) => setForm({ ...form, to_email: e.target.value })} /></label>
          </>
        )}
        <button type="submit">保存渠道</button>
      </form>
      <div className="space-y-2">
        {items.length === 0 && <p className="text-sm text-muted">还没有该渠道配置。</p>}
        {items.map((row) => (
          <div key={row.id} className="sr-card p-3">
            <strong>{row.name}</strong>
            <p className="text-xs text-muted">{row.webhook_url_masked || row.smtp_host || row.channel_type}</p>
            <div className="mt-2 flex gap-2">
              <button
                className="flex-1 text-xs"
                onClick={() =>
                  void api<{ ok: boolean; error?: string }>(`/api/v1/configs/channels/${row.id}/test`, { method: 'POST' }).then((r) =>
                    setMsg(r.data.ok ? '测试已发送' : `发送失败：${r.data.error}`),
                  )
                }
              >
                测试发送
              </button>
              <button className="ghost flex-1 text-xs" onClick={() => void api(`/api/v1/configs/channels/${row.id}`, { method: 'DELETE' }).then(onChange)}>
                删除
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
