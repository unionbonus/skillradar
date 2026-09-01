'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { api } from '@/lib/api';
import { Shell } from '@/components/Shell';
import { GraphView } from '@/components/GraphView';

type Plugin = {
  id: number;
  full_name: string;
  html_url: string;
  description?: string;
  stargazers_count: number;
  star_delta?: number;
  fingerprint_type?: string | null;
  source?: string;
  license?: string | null;
  source_keywords?: string[];
};

const TABS = [
  ['overview', '概览'],
  ['graph', '架构图'],
  ['deep', '深度分析'],
  ['motivation', '动机'],
  ['market', '市场调研'],
  ['report', '报告'],
] as const;

export default function PluginPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [tab, setTab] = useState<(typeof TABS)[number][0]>('overview');
  const [repo, setRepo] = useState<Plugin | null>(null);
  const [graph, setGraph] = useState<{ nodes: any[]; edges: any[]; source?: string }>({ nodes: [], edges: [] });
  const [mot, setMot] = useState<any>(null);
  const [deep, setDeep] = useState<any>(null);
  const [market, setMarket] = useState<any>(null);
  const [reportId, setReportId] = useState<string | null>(null);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const r = await api<Plugin>(`/api/v1/plugins/${id}`);
    setRepo(r.data);
    try {
      const g = await api<{ nodes: any[]; edges: any[]; source?: string }>(`/api/v1/plugins/${id}/graph?type=data_flow`);
      setGraph(g.data);
    } catch {
      setGraph({ nodes: [], edges: [] });
    }
    try {
      setMot((await api(`/api/v1/plugins/${id}/motivation`)).data);
    } catch {
      setMot(null);
    }
    try {
      setDeep((await api(`/api/v1/plugins/${id}/deep-dive`)).data);
    } catch {
      setDeep(null);
    }
    try {
      setMarket((await api(`/api/v1/plugins/${id}/market-research`)).data);
    } catch {
      setMarket(null);
    }
  };

  useEffect(() => {
    void load().catch((e) => setErr(e instanceof Error ? e.message : '加载失败'));
  }, [id]);

  const run = async (path: string, label: string) => {
    setBusy(true);
    setMsg(`${label}…`);
    try {
      const body =
        path.includes('reports/generate') ? JSON.stringify({ plugin_id: Number(id) }) : JSON.stringify({});
      const res = await api<any>(path, { method: 'POST', body });
      setMsg(`${label}完成`);
      if (path.includes('motivation')) setMot(res.data.motivation || res.data);
      if (path.includes('deep-dive')) setDeep(res.data);
      if (path.includes('market')) setMarket(res.data);
      if (path.includes('reports')) setReportId(res.data.id);
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
        <Link href="/radar">← 雷达</Link>
      </p>
      <h1 className="mb-1 text-[20px] font-semibold">{repo?.full_name || '插件详情'}</h1>
      {err && <p className="text-danger">{err}</p>}
      <p className="mb-3 text-sm text-muted">{repo?.description}</p>
      {repo && (
        <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Metric label="星标" value={String(repo.stargazers_count)} />
          <Metric label="来源" value={repo.source || 'github'} />
          <Metric label="指纹" value={repo.fingerprint_type || '—'} />
          <Metric label="许可证" value={repo.license || '未知'} />
        </div>
      )}
      <div className="mb-3 flex flex-wrap gap-2">
        <button disabled={busy} onClick={() => void run(`/api/v1/plugins/${id}/deep-dive`, '深度分析')}>
          深度分析
        </button>
        <button className="ghost" disabled={busy} onClick={() => void run(`/api/v1/plugins/${id}/motivation`, '动机分析')}>
          动机分析
        </button>
        <button className="ghost" disabled={busy} onClick={() => void run(`/api/v1/plugins/${id}/market-research`, '市场调研')}>
          市场调研
        </button>
        <button
          className="ghost"
          disabled={busy}
          onClick={() => void run(`/api/v1/reports/generate`, '生成报告')}
        >
          生成报告
        </button>
        {repo?.html_url && (
          <a href={repo.html_url} target="_blank" rel="noreferrer">
            <button className="ghost">打开源</button>
          </a>
        )}
      </div>
      {msg && <p className="mb-3 text-sm text-accent">{msg}</p>}
      <div className="mb-4 flex gap-2 overflow-x-auto">
        {TABS.map(([key, label]) => (
          <button key={key} className={tab === key ? '' : 'ghost'} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>
      {tab === 'overview' && (
        <div className="card p-4 text-sm text-slate-300">
          <p>标签：{(repo?.source_keywords || []).join('、') || '暂无命中词'}</p>
          <p className="mt-2">热度变化：{repo?.star_delta || 0}</p>
        </div>
      )}
      {tab === 'graph' &&
        (graph.nodes?.length ? (
          <GraphView nodes={graph.nodes || []} edges={graph.edges || []} />
        ) : (
          <Empty text="尚未拆解。回到雷达对该仓执行拆解。" />
        ))}
      {tab === 'deep' &&
        (deep ? (
          <pre className="card overflow-auto p-3 text-xs">{JSON.stringify(deep, null, 2)}</pre>
        ) : (
          <Empty text="点「深度分析」生成架构风格、模块与调用链。" />
        ))}
      {tab === 'motivation' &&
        (mot ? (
          <pre className="card overflow-auto p-3 text-xs">{JSON.stringify(mot, null, 2)}</pre>
        ) : (
          <Empty text="点「动机分析」推断设计理念与痛点。" />
        ))}
      {tab === 'market' &&
        (market ? (
          <pre className="card overflow-auto p-3 text-xs">{JSON.stringify(market, null, 2)}</pre>
        ) : (
          <Empty text="点「市场调研」生成 PEST、竞品与 MVP 建议。" />
        ))}
      {tab === 'report' && (
        <div className="card p-4">
          {reportId ? (
            <div>
              <p className="mb-2 text-sm">已生成商业拆解报告。</p>
              <Link href={`/reports/${reportId}`}>
                <button>查看完整报告</button>
              </Link>
            </div>
          ) : (
            <Empty text="点「生成报告」整合架构、亮点与市场调研。" />
          )}
          <p className="mt-3 text-xs text-muted">
            旧版 PRD 仍可在 <Link href={`/prd/${id}`}>工作台</Link> 编辑。
          </p>
        </div>
      )}
    </Shell>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="card px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div className="text-lg font-bold">{value}</div>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="card border-dashed p-6 text-sm text-muted">{text}</p>;
}
