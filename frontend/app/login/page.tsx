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
      <h1 className="mb-4 text-2xl font-bold">登录 SkillRadar</h1>
      <form className="max-w-md space-y-3">
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email" />
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="password ≥8" />
        {err && <p className="text-red-400 text-sm">{err}</p>}
        <div className="flex gap-2">
          <button onClick={(e) => void go('/api/v1/auth/login', e)}>登录</button>
          <button className="ghost" onClick={(e) => void go('/api/v1/auth/register', e)}>注册</button>
        </div>
      </form>
    </Shell>
  );
}
