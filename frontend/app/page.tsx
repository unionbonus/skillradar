'use client';

import Link from 'next/link';
import { desktop } from '@/lib/desktop';
import { Shell } from '@/components/Shell';
import { SearchBox } from '@/components/SearchBox';

export default function HomePage() {
  const desk = desktop();
  return (
    <Shell>
      <h1 className="mb-2 text-[28px] font-bold leading-tight">AI 基础插件商业情报雷达</h1>
      <p className="mb-5 max-w-2xl text-sm text-muted">
        {desk ? '桌面应用已接管本机窗口。' : ''}
        扫描 GitHub / npm / PyPI / MCP Registry 等渠道，拆解架构与设计亮点，生成咨询级商业报告，并按周期推送到飞书、企业微信或邮件。
      </p>
      <div className="card mb-6 p-4">
        <SearchBox />
      </div>
      <div className="mb-8 grid gap-3 sm:grid-cols-3">
        <Hint title="全网雷达" text="关键词监控多渠道插件，热度变化点亮雷达。" />
        <Hint title="深度拆解" text="架构风格、调用链、亮点与市场调研一次生成。" />
        <Hint title="报告库" text="商业拆解报告可检索、编辑，订阅后自动推送摘要。" />
      </div>
      <div className="flex flex-wrap gap-3">
        <Link href="/radar">
          <button>打开雷达</button>
        </Link>
        <Link href="/reports">
          <button className="ghost">报告库</button>
        </Link>
        <Link href="/login">
          <button className="ghost">登录 / 注册</button>
        </Link>
      </div>
    </Shell>
  );
}

function Hint({ title, text }: { title: string; text: string }) {
  return (
    <div className="card p-4">
      <h2 className="mb-1 text-sm font-semibold text-white">{title}</h2>
      <p className="text-sm text-muted">{text}</p>
    </div>
  );
}
