'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { api } from '@/lib/api';
import { Shell } from '@/components/Shell';
import { GraphView } from '@/components/GraphView';
import { MarkdownReport } from '@/components/MarkdownReport';

type Repo = {
  id: number;
  full_name: string;
  html_url: string;
  description?: string;
  stargazers_count: number;
  star_delta?: number;
  fingerprint_type?: string | null;
  source_keywords?: string[];
};

type Report = { id: string; content_md: string; status?: string };

const TABS = [
  { id: 'overview', label: '概览' },
  { id: 'market', label: '市场调研' },
  { id: 'commercial', label: '商业拆解' },
] as const;

export default function RepoPage() {
  const params = useParams<{ id: string }>();
  const [repo, setRepo] = useState<Repo | null>(null);
  const [graph, setGraph] = useState<{ nodes: any[]; edges: any[]; source?: string }>({ nodes: [], edges: [] });
  const [mot, setMot] = useState<any>(null);
  const [market, setMarket] = useState<Report | null>(null);
  const [commercial, setCommercial] = useState<Report | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]['id']>('overview');
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const id = params.id;

  const load = async () => {
    const r = await api<Repo>(`/api/v1/repos/${id}`);
    setRepo(r.data);
    try {
      const g = await api<{ nodes: any[]; edges: any[]; source?: string }>(`/api/v1/repos/${id}/graph?type=data_flow`);
      setGraph(g.data);
    } catch {
      setGraph({ nodes: [], edges: [] });
    }
    try {
      const m = await api(`/api/v1/repos/${id}/motivation`);
      setMot(m.data);
    } catch {
      setMot(null);
    }
    try {
      const mr = await api<Report>(`/api/v1/repos/${id}/market-research`);
      setMarket(mr.data);
    } catch {
      setMarket(null);
    }
    try {
      const cr = await api<Report>(`/api/v1/repos/${id}/commercial-report`);
      setCommercial(cr.data);
    } catch {
      setCommercial(null);
    }
  };

  useEffect(() => {
    void load().catch((e) => setErr(e instanceof Error ? e.message : '加载失败'));
  }, [id]);

  const run = async (path: string, ok: string) => {
    setBusy(true);
    setMsg('生成中…');
    try {
      await api(path, { method: 'POST', body: JSON.stringify({}) });
      setMsg(ok);
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : '失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell>
      <p className="mb-2 text-xs text-muted">
        <Link href="/radar" className="no-underline text-muted">← 雷达</Link>
      </p>
      <h1 className="display mb-1 text-2xl font-semibold text-white md:text-3xl">{repo?.full_name || '插件详情'}</h1>
      {err && <p className="text-danger">{err}</p>}
      <p className="mb-3 text-sm text-muted">{repo?.description}</p>
      {repo && (
        <p className="mb-4 text-xs text-accent">
          ⭐ {repo.stargazers_count}
          {repo.fingerprint_type ? ` · ${repo.fingerprint_type}` : ''}
          {graph.source ? ` · 图 ${graph.source}` : ''}
        </p>
      )}
      <div className="mb-4 flex gap-2 overflow-x-auto">
        {TABS.map((t) => (
          <button key={t.id} className={tab === t.id ? '' : 'ghost'} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      {msg && <p className="mb-3 text-sm text-accent">{msg}</p>}

      {tab === 'overview' && (
        <div>
          <div className="mb-3 flex flex-wrap gap-2">
            <button onClick={() => void api(`/api/v1/repos/${id}/motivation`, { method: 'POST' }).then((r) => setMot((r.data as any).motivation || r.data))}>
              生成动机分析
            </button>
            <Link href={`/prd/${id}`}>
              <button className="ghost">PRD 工作台</button>
            </Link>
            {repo?.html_url && (
              <a href={repo.html_url} target="_blank" rel="noreferrer">
                <button className="ghost">GitHub</button>
              </a>
            )}
          </div>
          {graph.nodes?.length ? (
            <GraphView nodes={graph.nodes || []} edges={graph.edges || []} />
          ) : (
            <p className="sr-card border-dashed p-6 text-sm text-muted">尚未拆解。回到雷达对该仓执行拆解。</p>
          )}
          {mot && (
            <pre className="mt-4 overflow-auto sr-card p-3 text-xs">{JSON.stringify(mot, null, 2)}</pre>
          )}
        </div>
      )}

      {tab === 'market' && (
        <div>
          <div className="mb-3 flex flex-wrap gap-2">
            <button disabled={busy} onClick={() => void run(`/api/v1/repos/${id}/market-research`, '市场调研已生成')}>
              {market ? '重新生成' : '生成市场调研'}
            </button>
          </div>
          {market?.content_md ? (
            <MarkdownReport markdown={market.content_md} title={`${repo?.full_name || 'plugin'}-market`} />
          ) : (
            <p className="sr-card p-6 text-sm text-muted">还没有市场调研报告。将生成 PEST、政策、至少 5 个竞品、痛点论证和 MVP。</p>
          )}
        </div>
      )}

      {tab === 'commercial' && (
        <div>
          <div className="mb-3 flex flex-wrap gap-2">
            <button disabled={busy} onClick={() => void run(`/api/v1/repos/${id}/commercial-report`, '商业拆解已生成')}>
              {commercial ? '重新生成' : '生成商业拆解'}
            </button>
          </div>
          {commercial?.content_md ? (
            <MarkdownReport markdown={commercial.content_md} title={`${repo?.full_name || 'plugin'}-commercial`} />
          ) : (
            <p className="sr-card p-6 text-sm text-muted">商业拆解会自动带上第 5 章「需求调研详细分析」，数据来自市场调研模块。</p>
          )}
        </div>
      )}
    </Shell>
  );
}
