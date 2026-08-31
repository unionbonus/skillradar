'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Markdown from 'react-markdown';
import { api } from '@/lib/api';
import { Shell } from '@/components/Shell';

export default function PrdPage() {
  const params = useParams<{ id: string }>();
  const [md, setMd] = useState('');
  const [msg, setMsg] = useState('');
  const id = params.id;
  useEffect(() => {
    void api<{ markdown: string }>(`/api/v1/repos/${id}/prd`)
      .then((r) => setMd(r.data.markdown))
      .catch((e) => setMsg(e.message));
  }, [id]);
  return (
    <Shell>
      <h1 className="mb-3 text-2xl font-bold">PRD 工作台</h1>
      <div className="grid gap-4 md:grid-cols-2">
        <textarea className="min-h-[480px]" value={md} onChange={(e) => setMd(e.target.value)} />
        <article className="prose prose-invert min-h-[480px] rounded-xl border border-line bg-panel p-4">
          <Markdown>{md}</Markdown>
        </article>
      </div>
      <div className="mt-3 flex gap-2">
        <button
          onClick={() =>
            void api(`/api/v1/repos/${id}/prd`, { method: 'PUT', body: JSON.stringify({ markdown: md }) })
              .then(() => setMsg('已保存'))
              .catch((e) => setMsg(e.message))
          }
        >
          保存
        </button>
        <a
          href={`data:text/markdown;charset=utf-8,${encodeURIComponent(md)}`}
          download={`skillradar-${id}.md`}
        >
          <button className="ghost">导出 Markdown</button>
        </a>
      </div>
      {msg && <p className="mt-2 text-sm text-slate-400">{msg}</p>}
    </Shell>
  );
}
