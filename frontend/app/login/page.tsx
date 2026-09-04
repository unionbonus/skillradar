'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, saveToken } from '@/lib/api';
import { Shell } from '@/components/Shell';

function explain(msg: string) {
  if (msg.includes('already registered')) return '该邮箱已注册，请直接登录';
  if (msg.includes('invalid credentials')) return '邮箱或密码不正确';
  if (msg.includes('internal error')) return '服务暂时不可用，请稍后重试';
  if (msg.toLowerCase().includes('email')) return '请填写有效邮箱';
  return msg;
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const go = async (path: string, e: FormEvent) => {
    e.preventDefault();
    setErr('');
    if (!email.trim() || password.length < 8) {
      setErr('请填写邮箱，密码至少 8 位');
      return;
    }
    setBusy(true);
    try {
      const res = await api<{ access_token: string }>(path, {
        method: 'POST',
        body: JSON.stringify({ email: email.trim(), password }),
      });
      saveToken(res.data.access_token);
      router.push('/radar');
    } catch (ex) {
      setErr(explain(ex instanceof Error ? ex.message : '失败'));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Shell>
      <h1 className="mb-4 text-2xl font-bold">登录 SkillRadar</h1>
      <p className="mb-3 text-sm text-muted">使用邮箱注册账号，再登录后即可配置大模型与渠道。</p>
      <form className="max-w-md space-y-3">
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="邮箱" autoComplete="email" />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="密码至少 8 位"
          autoComplete="current-password"
        />
        {err && <p className="text-red-400 text-sm">{err}</p>}
        <div className="flex gap-2">
          <button type="button" disabled={busy} onClick={(e) => void go('/api/v1/auth/login', e)}>
            登录
          </button>
          <button type="button" className="ghost" disabled={busy} onClick={(e) => void go('/api/v1/auth/register', e)}>
            注册
          </button>
        </div>
      </form>
    </Shell>
  );
}
