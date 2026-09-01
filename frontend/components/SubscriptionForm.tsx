'use client';

import { FormEvent, useState } from 'react';

export type SubscriptionInput = {
  name: string;
  conditions: {
    keywords: string[];
    authors: string[];
    organizations: string[];
    topics: string[];
    specific_repos: string[];
  };
  frequency: 'daily' | 'weekly' | 'monthly';
  channel: 'feishu' | 'wecom' | 'email';
  channel_config: { webhook_url?: string; email?: string };
};

const empty: SubscriptionInput = {
  name: '',
  conditions: { keywords: [], authors: [], organizations: [], topics: [], specific_repos: [] },
  frequency: 'weekly',
  channel: 'feishu',
  channel_config: {},
};

function csv(v: string): string[] {
  return v.split(',').map((s) => s.trim()).filter(Boolean);
}

export function SubscriptionForm({
  initial,
  onSubmit,
}: {
  initial?: Partial<SubscriptionInput>;
  onSubmit: (data: SubscriptionInput) => Promise<void>;
}) {
  const [form, setForm] = useState<SubscriptionInput>({ ...empty, ...initial, conditions: { ...empty.conditions, ...initial?.conditions } });
  const [err, setErr] = useState('');
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr('');
    if (!form.name.trim()) {
      setErr('名称必填');
      return;
    }
    try {
      await onSubmit(form);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : '保存失败');
    }
  };
  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-3 rounded-xl border border-line bg-panel p-4">
      <label>订阅名称<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
      <label>关键词（逗号分隔）
        <input onChange={(e) => setForm({ ...form, conditions: { ...form.conditions, keywords: csv(e.target.value) } })} placeholder="mcp server, agent memory" />
      </label>
      <label>作者<input onChange={(e) => setForm({ ...form, conditions: { ...form.conditions, authors: csv(e.target.value) } })} /></label>
      <label>组织<input onChange={(e) => setForm({ ...form, conditions: { ...form.conditions, organizations: csv(e.target.value) } })} /></label>
      <label>主题<input onChange={(e) => setForm({ ...form, conditions: { ...form.conditions, topics: csv(e.target.value) } })} /></label>
      <label>指定仓库 full_name<input onChange={(e) => setForm({ ...form, conditions: { ...form.conditions, specific_repos: csv(e.target.value) } })} /></label>
      <div className="grid grid-cols-2 gap-3">
        <select value={form.frequency} onChange={(e) => setForm({ ...form, frequency: e.target.value as SubscriptionInput['frequency'] })}>
          <option value="daily">每日</option>
          <option value="weekly">每周</option>
          <option value="monthly">每月</option>
        </select>
        <select value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value as SubscriptionInput['channel'] })}>
          <option value="feishu">飞书</option>
          <option value="wecom">企业微信</option>
          <option value="email">邮件</option>
        </select>
      </div>
      {form.channel === 'email' ? (
        <label>
          收件邮箱
          <input
            onChange={(e) => setForm({ ...form, channel_config: { ...form.channel_config, email: e.target.value } })}
            placeholder="ops@example.com"
          />
        </label>
      ) : (
        <label>
          Webhook URL
          <input
            onChange={(e) => setForm({ ...form, channel_config: { webhook_url: e.target.value } })}
            placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
          />
        </label>
      )}
      {err && <p className="text-red-400 text-sm">{err}</p>}
      <button type="submit">保存订阅</button>
    </form>
  );
}
