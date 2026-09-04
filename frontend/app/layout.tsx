import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'SkillRadar v0.5.3',
  description: 'AI 基础插件商业情报与市场调研平台',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
