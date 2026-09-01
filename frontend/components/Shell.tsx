'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { clearToken } from '@/lib/api';

const NAV = [
  ['/radar', '雷达'],
  ['/reports', '报告库'],
  ['/subscriptions', '订阅'],
  ['/settings', '设置'],
];

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const active = (href: string) => path === href || (href !== '/' && path.startsWith(href));
  return (
    <div className="min-h-screen pb-20 md:pb-0">
      <header className="hidden items-center justify-between border-b border-line px-6 py-3 md:flex">
        <Link href="/" className="text-lg font-semibold text-accent">
          SkillRadar <span className="text-xs opacity-70">v0.5.2</span>
        </Link>
        <nav className="flex items-center gap-4 text-sm">
          {NAV.map(([href, label]) => (
            <Link key={href} href={href} className={active(href) ? 'text-white' : 'text-muted'}>
              {label}
            </Link>
          ))}
          <Link href="/help" className="text-muted">
            手册
          </Link>
          <button
            className="ghost text-sm"
            onClick={() => {
              clearToken();
              router.push('/login');
            }}
          >
            退出
          </button>
        </nav>
      </header>
      <header className="flex items-center justify-between border-b border-line px-4 py-3 md:hidden">
        <Link href="/" className="text-base font-semibold text-accent">
          SkillRadar <span className="text-xs opacity-70">v0.5.2</span>
        </Link>
        <Link href="/help" className="text-xs text-muted">
          手册
        </Link>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-5 md:px-6 md:py-6">{children}</main>
      <nav className="fixed bottom-0 left-0 right-0 z-20 grid grid-cols-4 border-t border-line bg-[#0f1419]/95 backdrop-blur md:hidden">
        {NAV.map(([href, label]) => (
          <Link
            key={href}
            href={href}
            className={`py-3 text-center text-xs ${active(href) ? 'text-accent' : 'text-muted'}`}
          >
            {label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
