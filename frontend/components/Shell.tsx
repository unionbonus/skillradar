'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { clearToken } from '@/lib/api';

const NAV = [
  ['/', '情报', 'home'],
  ['/radar', '雷达', 'radar'],
  ['/subscriptions', '订阅', 'subs'],
  ['/settings', '设置', 'gear'],
];

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const active = (href: string) => (href === '/' ? path === '/' : path.startsWith(href));
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-line/80 bg-[#07111f]/80 px-4 py-3 backdrop-blur-xl md:px-6">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3">
          <Link href="/" className="display text-lg font-semibold tracking-tight text-white">
            SkillRadar <span className="ml-1 text-[11px] font-medium text-accent">v0.5</span>
          </Link>
          <nav className="hidden items-center gap-1 md:flex">
            {NAV.map(([href, label]) => (
              <Link
                key={href}
                href={href}
                className={`rounded-pill px-3 py-2 text-sm no-underline ${
                  active(href) ? 'bg-elevated text-white' : 'text-muted hover:text-white'
                }`}
              >
                {label}
              </Link>
            ))}
            <Link href="/help" className="rounded-pill px-3 py-2 text-sm text-muted no-underline hover:text-white">
              手册
            </Link>
            <button
              className="ghost ml-2 text-sm"
              onClick={() => {
                clearToken();
                router.push('/login');
              }}
            >
              退出
            </button>
          </nav>
        </div>
      </header>
      <main className="sr-main mx-auto max-w-6xl px-4 py-5 md:px-6 md:py-8">{children}</main>
      <nav className="fixed bottom-0 left-0 right-0 z-30 border-t border-line/80 bg-[#0c1b2e]/92 px-2 pb-[max(10px,env(safe-area-inset-bottom))] pt-2 backdrop-blur-xl md:hidden">
        <div className="grid grid-cols-4 gap-1">
          {NAV.map(([href, label]) => (
            <Link
              key={href}
              href={href}
              className={`flex min-h-[48px] flex-col items-center justify-center rounded-2xl text-[11px] no-underline ${
                active(href) ? 'bg-elevated text-accent' : 'text-muted'
              }`}
            >
              <span className="mb-0.5 h-1 w-1 rounded-full bg-current" />
              {label}
            </Link>
          ))}
        </div>
      </nav>
    </div>
  );
}
