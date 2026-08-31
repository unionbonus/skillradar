'use client';

import Link from 'next/link';
import { desktop } from '@/lib/desktop';
import { Shell } from '@/components/Shell';

export default function HomePage() {
  const desk = desktop();
  return (
    <Shell>
      <p className="mb-2 text-xs uppercase tracking-[0.2em] text-accent">Intelligence OS · v0.5</p>
      <h1 className="display mb-3 max-w-xl text-4xl font-semibold leading-tight text-white md:text-5xl">
        AI 基础插件的商业情报操作系统
      </h1>
      <p className="mb-8 max-w-2xl text-base leading-7 text-muted">
        {desk ? '桌面窗口已就绪。' : ''}
        扫描 Skill / MCP / CLI 插件，拆解技术结构，生成可溯源的市场调研与商业拆解，再把简报推到飞书、企微或邮件。
      </p>
      <div className="mb-8 grid gap-3 sm:grid-cols-3">
        <Hint title="雷达扫描" text="关键词监控 GitHub，指纹分环点亮同类插件。" />
        <Hint title="市场调研" text="PEST、政策、竞品、痛点论证与 MVP，每条结论可溯源。" />
        <Hint title="连接中心" text="大模型与渠道配置隔离加密，订阅可指定配置集。" />
      </div>
      <div className="flex flex-wrap gap-3">
        <Link href="/radar"><button>打开雷达</button></Link>
        <Link href="/login"><button className="ghost">登录 / 注册</button></Link>
        <Link href="/settings"><button className="ghost">系统设置</button></Link>
      </div>
    </Shell>
  );
}

function Hint({ title, text }: { title: string; text: string }) {
  return (
    <div className="sr-card p-4">
      <h2 className="mb-1 text-sm font-semibold text-white">{title}</h2>
      <p className="text-sm text-muted">{text}</p>
    </div>
  );
}
