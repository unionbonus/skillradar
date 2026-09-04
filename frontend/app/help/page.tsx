'use client';

import Link from 'next/link';
import { desktop } from '@/lib/desktop';
import { Shell } from '@/components/Shell';

export default function HelpPage() {
  const desk = desktop();
  return (
    <Shell>
      <h1 className="mb-2 text-[20px] font-semibold">SkillRadar v0.5.3 使用手册</h1>
      <p className="mb-6 max-w-2xl text-sm text-muted">
        AI 基础插件商业情报平台：多渠道扫描、技术深度拆解、市场调研、商业报告库、飞书/企微/邮件订阅。桌面窗口菜单可跳转雷达 / 订阅 / 设置。
      </p>
      <ol className="mb-6 max-w-2xl list-decimal space-y-2 pl-5 text-sm text-slate-300">
        <li>
          <Link href="/login">登录或注册</Link> 后打开雷达，扫描 GitHub 或其他渠道。
        </li>
        <li>点亮的 PPI 接触点进入详情：架构图、深度分析、动机、市场调研，再生成商业拆解报告。</li>
        <li>报告库可全文/语义检索；订阅页配置飞书 / 企微 / 邮件。</li>
        <li>设置页渠道为飞书 / 企业微信 / 邮件标签。扫码绑定后头像右下角绿钩表示在线；大模型与渠道需先登录。</li>
      </ol>
      <div className="flex flex-wrap gap-2">
        <Link href="/radar">
          <button>打开雷达</button>
        </Link>
        <Link href="/reports">
          <button className="ghost">报告库</button>
        </Link>
        {desk ? (
          <button className="ghost" onClick={() => void desk.openManual()}>
            打开完整用户手册
          </button>
        ) : (
          <p className="text-sm text-muted">浏览器模式下请阅读仓库中的 用户手册.md。</p>
        )}
      </div>
    </Shell>
  );
}
