import './globals.css';
import type { Metadata } from 'next';
import { IBM_Plex_Sans, Outfit } from 'next/font/google';

const display = Outfit({ subsets: ['latin'], variable: '--font-display', weight: ['500', '600', '700'] });
const body = IBM_Plex_Sans({ subsets: ['latin'], variable: '--font-body', weight: ['400', '500', '600'] });

export const metadata: Metadata = {
  title: 'SkillRadar v0.5',
  description: 'AI 基础插件商业情报与市场调研平台',
  viewport: 'width=device-width, initial-scale=1, viewport-fit=cover',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className={`${display.variable} ${body.variable}`}>
      <body className="font-sans">{children}</body>
    </html>
  );
}
