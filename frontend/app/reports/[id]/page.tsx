'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import Markdown from 'react-markdown';
import { api } from '@/lib/api';
import { Shell } from '@/components/Shell';

export default function ReportDetailPage() {
  const params = useParams<{ id: string }>();
  const [md, setMd] = useState('');
  const [title, setTitle] = useState('');
  const [msg, setMsg] = useState('');
  const id = params.id;
  useEffect(() => {
    void api<{ title: string; content_md: string }>(`/api/v1/reports/${id}`)
      .then((r) => {
        setTitle(r.data.title);
        setMd(r.data.content_md);
      })
      .catch((e) => setMsg(e.message));
  }, [id]);
  return (
    <Shell>
      <p className="mb-2 text-xs text-muted">
        <Link href="/reports">← 报告库</Link>
      </p>
      <h1 className="mb-3 text-[20px] font-semibold">{title || '报告详情'}</h1>
      <div className="grid gap-4 md:grid-cols-2">
        <textarea className="min-h-[480px]" value={md} onChange={(e) => setMd(e.target.value)} />
        <article className="prose prose-invert card min-h-[480px] p-4">
          <Markdown>{md}</Markdown>
        </article>
      </div>
      <div className="mt-3 flex gap-2">
        <button
          onClick={() =>
            void api(`/api/v1/reports/${id}`, { method: 'PUT', body: JSON.stringify({ content_md: md }) })
              .then(() => setMsg('已保存'))
              .catch((e) => setMsg(e.message))
          }
        >
          保存
        </button>
        <a href={`data:text/markdown;charset=utf-8,${encodeURIComponent(md)}`} download={`skillradar-${id}.md`}>
          <button className="ghost">导出 Markdown</button>
        </a>
      </div>
      {msg && <p className="mt-2 text-sm text-muted">{msg}</p>}
    </Shell>
  );
}
