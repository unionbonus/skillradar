'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, saveToken } from '@/lib/api';
import { Shell } from '@/components/Shell';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('pm@example.com');
  const [password, setPassword] = useState('password1');
  const [err, setErr] = useState('');
  const go = async (path: string, e: FormEvent) => {
    e.preventDefault();
    setErr('');
    try {
      const res = await api<{ access_token: string }>(path, {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      saveToken(res.data.access_token);
      router.push('/radar');
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : '失败');
    }
  };
  return (
    <Shell>
      <p className="mb-2 text-xs uppercase tracking-[0.18em] text-accent">Sign in</p>
      <h1 className="display mb-5 text-3xl font-semibold">进入情报台</h1>
      <form className="sr-card max-w-md space-y-3 p-5">
        <label>邮箱<input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email" /></label>
        <label>密码<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="password ≥8" /></label>
        {err && <p className="text-sm text-danger">{err}</p>}
        <div className="flex gap-2">
          <button onClick={(e) => void go('/api/v1/auth/login', e)}>登录</button>
          <button className="ghost" onClick={(e) => void go('/api/v1/auth/register', e)}>注册</button>
        </div>
      </form>
    </Shell>
  );
}
