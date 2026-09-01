'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { Shell } from '@/components/Shell';
import { RadarMap, type RadarEdge, type RadarNode } from '@/components/RadarMap';
import { SearchBox } from '@/components/SearchBox';

type Keyword = {
  id: string;
  query: string;
  search_type: string;
  enabled: boolean;
  interval_hours: number;
  limit: number;
  last_run_at?: string | null;
  last_status: string;
  last_count: number;
  last_error?: string | null;
  is_due?: boolean;
  next_due_at?: string | null;
};

type Task = { task_id: string; status: string; query: string; kind: string; error_message?: string | null };
type Repo = {
  id: number;
  full_name: string;
  description?: string;
  stargazers_count: number;
  star_delta?: number;
  fingerprint_type?: string | null;
  is_ai_skill: boolean;
  source_keywords?: string[];
  html_url?: string;
};

type RadarData = {
  stats: {
    repositories: number;
    ai_skills: number;
    keywords_active: number;
    last_scan?: string | null;
    graph: { backend: string; connected: boolean; nodes?: number | null };
  };
  keywords: Keyword[];
  tasks: Task[];
  items: Repo[];
  graph: { nodes: RadarNode[]; edges: RadarEdge[]; backend?: string };
};

const FILTERS = [
  { id: 'all', label: '全部' },
  { id: 'claude_skill', label: 'Claude Skill' },
  { id: 'mcp_server', label: 'MCP' },
  { id: 'langchain_tool', label: 'LangChain' },
  { id: 'none', label: '未分类' },
];

const STATUS_LABEL: Record<string, string> = {
  idle: '待命',
  running: '扫描中',
  success: '成功',
  failed: '失败',
};

export default function RadarPage() {
  const [data, setData] = useState<RadarData | null>(null);
  const [query, setQuery] = useState('mcp server');
  const [kwType, setKwType] = useState<'keyword' | 'topic' | 'author'>('keyword');
  const [source, setSource] = useState('github');
  const [intervalHours, setIntervalHours] = useState(6);
  const [msg, setMsg] = useState('');
  const [filter, setFilter] = useState('all');
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [pending, setPending] = useState<string[]>([]);

  const load = useCallback(async () => {
    const res = await api<RadarData>('/api/v1/radar');
    setData(res.data);
  }, []);

  useEffect(() => {
    void load().catch((e) => setMsg(e instanceof Error ? e.message : '请先登录'));
  }, [load]);

  useEffect(() => {
    if (!pending.length) return;
    const t = setInterval(() => {
      void (async () => {
        const still: string[] = [];
        for (const id of pending) {
          try {
            const st = await api<Task>(`/api/v1/scan/tasks/${id}`);
            if (st.data.status === 'queued' || st.data.status === 'running') still.push(id);
            else if (st.data.status === 'failed') setMsg(st.data.error_message || '扫描失败');
            else setMsg(`「${st.data.query}」完成`);
          } catch (e) {
            setMsg(e instanceof Error ? e.message : '任务查询失败');
          }
        }
        setPending(still);
        await load().catch(() => undefined);
      })();
    }, 1200);
    return () => clearInterval(t);
  }, [pending, load]);

  const items = useMemo(() => {
    const rows = data?.items || [];
    if (filter === 'all') return rows;
    if (filter === 'none') return rows.filter((r) => !r.fingerprint_type);
    return rows.filter((r) => r.fingerprint_type === filter);
  }, [data, filter]);

  const allowedIds = useMemo(() => new Set(items.map((r) => `repo:${r.id}`)), [items]);

  const radarNodes = useMemo(() => {
    const nodes = data?.graph.nodes || [];
    if (filter === 'all') return nodes.filter((n) => n.type !== 'keyword');
    return nodes.filter((n) => n.type !== 'keyword' && allowedIds.has(n.id));
  }, [data, filter, allowedIds]);

  const radarEdges = useMemo(() => {
    const edges = data?.graph.edges || [];
    const ids = new Set(radarNodes.map((n) => n.id));
    return edges.filter((e) => ids.has(e.source) && ids.has(e.target));
  }, [data, radarNodes]);

  const selectedNode = radarNodes.find((n) => n.id === selected) || null;
  const selectedRepo = selectedNode?.data?.repo_id
    ? items.find((r) => r.id === selectedNode.data?.repo_id) || data?.items.find((r) => r.id === selectedNode.data?.repo_id)
    : null;

  const queueTasks = (ids: string[]) => {
    if (!ids.length) return;
    setPending((p) => [...p, ...ids]);
  };

  const scanNow = async (watch: boolean) => {
    const q = query.trim();
    if (!q) {
      setMsg('请输入关键词');
      return;
    }
    setBusy(true);
    setMsg('');
    try {
      const res = await api<{ task_id: string }>('/api/v1/scan/github', {
        method: 'POST',
        body: JSON.stringify({ query: q, type: kwType, limit: 20, watch, source }),
      });
      queueTasks([res.data.task_id]);
      setMsg(watch ? '已提交扫描，命中将加入监控列表' : '扫描任务已提交，雷达即将刷新');
    } catch (e) {
      setMsg(e instanceof Error ? e.message : '扫描失败');
    } finally {
      setBusy(false);
    }
  };

  const addKeyword = async () => {
    const q = query.trim();
    if (!q) {
      setMsg('请输入要监控的词');
      return;
    }
    setBusy(true);
    try {
      await api('/api/v1/scan/keywords', {
        method: 'POST',
        body: JSON.stringify({
          query: q,
          search_type: kwType,
          enabled: true,
          interval_hours: intervalHours,
          limit: 20,
        }),
      });
      setMsg(`已加入监控：${q}`);
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : '添加失败');
    } finally {
      setBusy(false);
    }
  };

  const runKw = async (id: string) => {
    setBusy(true);
    try {
      const res = await api<{ task_id: string }>(`/api/v1/scan/keywords/${id}/run`, { method: 'POST' });
      queueTasks([res.data.task_id]);
      setMsg('监控词立即扫描中…');
    } catch (e) {
      setMsg(e instanceof Error ? e.message : '触发失败');
    } finally {
      setBusy(false);
    }
  };

  const toggleKw = async (kw: Keyword) => {
    try {
      await api(`/api/v1/scan/keywords/${kw.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          query: kw.query,
          search_type: kw.search_type,
          enabled: !kw.enabled,
          interval_hours: kw.interval_hours,
          limit: kw.limit || 20,
        }),
      });
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : '更新失败');
    }
  };

  const deleteKw = async (kw: Keyword) => {
    if (!window.confirm(`停止监控「${kw.query}」？已入库的仓库会保留。`)) return;
    try {
      await api(`/api/v1/scan/keywords/${kw.id}`, { method: 'DELETE' });
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : '删除失败');
    }
  };

  const runDue = async () => {
    setBusy(true);
    try {
      const r = await api<{ due: number; task_ids: string[] }>('/api/v1/scan/keywords/run-due', { method: 'POST' });
      queueTasks(r.data.task_ids || []);
      setMsg(r.data.due ? `已触发 ${r.data.due} 个到期监控` : '当前没有到期的监控词');
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : '触发失败');
    } finally {
      setBusy(false);
    }
  };

  const stats = data?.stats;
  const scanning = pending.length > 0;
  return (
    <Shell>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">情报雷达</h1>
          <p className="mt-1 text-sm text-muted">
            关键词按间隔扫描多渠道插件，结果写入仓库库并同步到
            {stats?.graph.backend === 'neo4j' ? ' Neo4j 图' : ' 内存图'}
            ；语义检索覆盖已入库插件。
          </p>
        </div>
        <div className="flex gap-2 text-center text-xs">
          <Stat label="仓库" value={stats?.repositories ?? 0} />
          <Stat label="AI Skill" value={stats?.ai_skills ?? 0} />
          <Stat label="监控词" value={stats?.keywords_active ?? 0} />
          <Stat
            label="图存储"
            value={stats?.graph.backend ?? '—'}
            hint={stats?.graph.connected ? `在线${typeof stats.graph.nodes === 'number' ? ` · ${stats.graph.nodes}` : ''}` : '降级'}
          />
        </div>
      </div>

      <form
        className="mb-4 flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void scanNow(false);
        }}
      >
        <input
          className="max-w-xs"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="关键词 / topic / 作者"
          aria-label="扫描关键词"
        />
        <select className="w-auto" value={kwType} onChange={(e) => setKwType(e.target.value as typeof kwType)} aria-label="搜索类型">
          <option value="keyword">关键词</option>
          <option value="topic">Topic</option>
          <option value="author">作者</option>
        </select>
        <select className="w-auto" value={source} onChange={(e) => setSource(e.target.value)} aria-label="渠道">
          <option value="github">GitHub</option>
          <option value="npm">npm</option>
          <option value="pypi">PyPI</option>
          <option value="mcp_registry">MCP Registry</option>
          <option value="huggingface">Hugging Face</option>
          <option value="dockerhub">Docker Hub</option>
        </select>
        <select
          className="w-auto"
          value={intervalHours}
          onChange={(e) => setIntervalHours(Number(e.target.value))}
          aria-label="监控间隔"
        >
          <option value={6}>每 6 小时</option>
          <option value={12}>每 12 小时</option>
          <option value={24}>每天</option>
        </select>
        <button type="submit" disabled={busy}>
          扫描 GitHub
        </button>
        <button type="button" className="ghost" disabled={busy} onClick={() => void scanNow(true)}>
          扫描并监控
        </button>
        <button type="button" className="ghost" disabled={busy} onClick={() => void addKeyword()}>
          仅加入监控
        </button>
        <button type="button" className="ghost" disabled={busy} onClick={() => void runDue()}>
          跑到期监控
        </button>
      </form>
      <div className="card mb-4 p-3">
        <p className="mb-2 text-xs text-muted">已入库插件语义检索</p>
        <SearchBox placeholder="检索 MCP / Skill / 报告" />
      </div>
      {msg && (
        <p className="mb-3 text-sm text-accent" role="status">
          {scanning ? `同步中 · ${msg}` : msg}
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
        <aside className="space-y-2">
          <h2 className="text-sm font-semibold text-slate-300">监控关键词</h2>
          {(data?.keywords || []).length === 0 && (
            <p className="rounded-xl border border-dashed border-line p-3 text-xs text-slate-400">
              还没有监控词。输入关键词后点「仅加入监控」，调度器会按间隔自动扫 GitHub。
            </p>
          )}
          {(data?.keywords || []).map((kw) => (
            <div key={kw.id} className="rounded-xl border border-line bg-panel p-3">
              <div className="flex items-center justify-between gap-2">
                <strong className="text-sm">{kw.query}</strong>
                <span className={`text-[10px] ${kw.enabled ? 'text-accent' : 'text-slate-500'}`}>
                  {kw.enabled ? (kw.is_due ? '待扫描' : STATUS_LABEL[kw.last_status] || kw.last_status) : '已暂停'}
                </span>
              </div>
              <p className="mt-1 text-[11px] text-slate-400">
                {kw.search_type} · 每 {kw.interval_hours}h
                {kw.last_count ? ` · 上次 ${kw.last_count} 仓` : ''}
              </p>
              {kw.last_error && <p className="text-[11px] text-red-400">{kw.last_error}</p>}
              <div className="mt-2 flex gap-1">
                <button className="flex-1 px-2 py-1 text-xs" disabled={busy} onClick={() => void runKw(kw.id)}>
                  立即扫描
                </button>
                <button className="ghost px-2 py-1 text-xs" onClick={() => void toggleKw(kw)}>
                  {kw.enabled ? '暂停' : '开启'}
                </button>
                <button className="ghost px-2 py-1 text-xs" onClick={() => void deleteKw(kw)}>
                  删除
                </button>
              </div>
            </div>
          ))}
          <h2 className="pt-2 text-sm font-semibold text-slate-300">任务流</h2>
          {(data?.tasks || []).length === 0 && <p className="text-[11px] text-slate-500">暂无任务</p>}
          {(data?.tasks || []).slice(0, 8).map((t) => (
            <p key={t.task_id} className="text-[11px] text-slate-400">
              <span className={t.status === 'failed' ? 'text-red-400' : t.status === 'success' ? 'text-accent' : ''}>
                {t.status}
              </span>
              {' · '}
              {t.query}
            </p>
          ))}
        </aside>
        <section>
          <div className="relative">
            <RadarMap
              nodes={radarNodes}
              edges={radarEdges}
              selectedId={selected}
              scanning={scanning}
              onSelect={(n) => setSelected(n.id)}
            />
            {!radarNodes.length && (
              <div className="pointer-events-none absolute left-1/2 top-[56%] -translate-x-1/2">
                <p className="rounded border border-line/80 bg-[#070b10]/70 px-3 py-1 font-mono text-[11px] tracking-wide text-muted">
                  NO CONTACTS · AWAIT SCAN
                </p>
              </div>
            )}
            {selectedRepo && (
                  <div className="absolute bottom-3 left-3 right-3 rounded-xl border border-line bg-[#070b10]/95 p-3 shadow-lg">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <strong>{selectedRepo.full_name}</strong>
                    <p className="text-sm text-slate-300">{selectedRepo.description || '暂无描述'}</p>
                    <p className="text-xs text-accent">
                      {selectedRepo.fingerprint_type || 'unclassified'}
                      {selectedRepo.source_keywords?.length ? ` · 命中 ${selectedRepo.source_keywords.join(', ')}` : ''}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Link href={`/repos/${selectedRepo.id}`}>
                      <button className="text-xs">进入拆解</button>
                    </Link>
                    {selectedRepo.html_url ? (
                      <a href={selectedRepo.html_url} target="_blank" rel="noreferrer">
                        <button className="ghost text-xs">GitHub</button>
                      </a>
                    ) : null}
                    <button className="ghost text-xs" onClick={() => setSelected(null)}>
                      关闭
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {FILTERS.map((f) => (
              <button key={f.id} className={filter === f.id ? '' : 'ghost'} onClick={() => setFilter(f.id)}>
                {f.label}
              </button>
            ))}
            <span className="ml-auto text-[11px] font-mono text-slate-500">
              PPI 扫描线 · Skill 绿 · MCP 蓝 · 选中为 IFF 十字
            </span>
          </div>
          <div className="mt-3 grid gap-2">
            {items.length === 0 && (
              <p className="rounded-xl border border-dashed border-line p-4 text-sm text-slate-400">
                当前筛选下没有仓库。换一个指纹分类，或先跑一次扫描。
              </p>
            )}
            {items.map((r) => (
              <Link
                key={r.id}
                href={`/repos/${r.id}`}
                className={`block rounded-xl border p-3 ${
                  selected === `repo:${r.id}` ? 'border-accent bg-panel' : 'border-line bg-panel'
                }`}
              >
                <div className="flex justify-between gap-3">
                  <strong>{r.full_name}</strong>
                  <span className="text-sm">
                    ⭐ {r.stargazers_count}
                    {r.star_delta ? (
                      <span className="ml-1 text-accent">
                        ({r.star_delta > 0 ? '+' : ''}
                        {r.star_delta})
                      </span>
                    ) : null}
                  </span>
                </div>
                <p className="text-sm text-slate-300">{r.description}</p>
                <p className="text-xs text-accent">
                  {r.fingerprint_type || 'unclassified'}
                  {r.source_keywords?.length ? ` · 命中 ${r.source_keywords.join(', ')}` : ''}
                </p>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </Shell>
  );
}

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="min-w-[72px] rounded-xl border border-line bg-panel px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
      <div className="text-lg font-semibold text-white">{value}</div>
      {hint && <div className="text-[10px] text-accent">{hint}</div>}
    </div>
  );
}
