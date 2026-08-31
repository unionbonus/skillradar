'use client';

import Link from 'next/link';
import { desktop } from '@/lib/desktop';
import { Shell } from '@/components/Shell';

export default function HelpPage() {
  const desk = desktop();
  return (
    <Shell>
      <h1 className="mb-2 text-2xl font-bold">SkillRadar 情报操作系统 v0.5</h1>
      <p className="mb-6 max-w-2xl text-slate-300">
        这是安装在本机的 Electron 窗口：菜单栏可跳转雷达 / 订阅 / 设置，外链会在系统浏览器打开。本地 FastAPI 跑在 127.0.0.1:8000，页面跑在 127.0.0.1:3000。
      </p>
      <ol className="mb-6 max-w-2xl list-decimal space-y-2 pl-5 text-sm text-slate-300">
        <li>
          <Link href="/login">登录或注册</Link> 后打开雷达。
        </li>
        <li>在雷达里扫描关键词或启用监控词，星点亮起后点预览再拆解。</li>
        <li>仓库页生成市场调研、商业拆解与 PRD；设置页配置大模型与飞书/企微/邮件渠道。</li>
        <li>GitHub Token、LLM Key 写在项目根目录 <code className="text-accent">.env</code>，不要贴进聊天。</li>
      </ol>
      <div className="flex flex-wrap gap-2">
        <Link href="/radar">
          <button>打开雷达</button>
        </Link>
        <Link href="/settings">
          <button className="ghost">运行状态</button>
        </Link>
        {desk ? (
          <button className="ghost" onClick={() => void desk.openManual()}>
            打开完整用户手册
          </button>
        ) : (
          <p className="text-sm text-slate-400">浏览器模式下请直接阅读仓库中的 用户手册.md。</p>
        )}
      </div>
      <p className="mt-6 text-xs text-slate-500">
        快捷键：Ctrl+1 雷达 · Ctrl+2 订阅 · Ctrl+3 设置。托盘图标可重新打开窗口。
      </p>
    </Shell>
  );
}
