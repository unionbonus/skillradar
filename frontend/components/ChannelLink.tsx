'use client';

import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';

export type ChannelLive = {
  type: 'feishu' | 'wecom';
  label: string;
  connected: boolean;
  live: boolean;
  keep_alive: boolean;
  display_name?: string | null;
  avatar_url?: string | null;
  ticket?: string | null;
  qr_svg?: string;
  bind_url?: string | null;
  expires_at?: string;
};

type LiveSnap = { keep_alive?: boolean; channels?: Record<string, ChannelLive> };

const BRAND: Record<string, { src: string; ring: string }> = {
  feishu: { src: '/brand/feishu.svg', ring: '#3370FF' },
  wecom: { src: '/brand/wecom.svg', ring: '#00C48C' },
};

function token() {
  return typeof window !== 'undefined' ? localStorage.getItem('sr_token') || '' : '';
}

export function ChannelLinkPanel({ onMsg }: { onMsg: (s: string) => void }) {
  const [snap, setSnap] = useState<LiveSnap | null>(null);
  const [err, setErr] = useState('');

  const apply = (data: LiveSnap) => setSnap(data);

  useEffect(() => {
    let stop = false;
    let es: EventSource | null = null;
    let ws: WebSocket | null = null;
    const boot = async () => {
      try {
        const r = await api<LiveSnap>('/api/v1/channels/live/status');
        if (!stop) apply(r.data);
      } catch (e) {
        if (!stop) setErr(e instanceof Error ? e.message : '渠道状态失败');
      }
      const t = token();
      if (!t) return;
      const sse = `/api/v1/channels/live/stream?token=${encodeURIComponent(t)}`;
      es = new EventSource(sse);
      es.onmessage = (ev) => {
        try {
          apply(JSON.parse(ev.data) as LiveSnap);
        } catch {
          /* ignore keep-alive comments */
        }
      };
      es.onerror = () => {
        es?.close();
        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${proto}//${window.location.host}/api/v1/channels/live?token=${encodeURIComponent(t)}`);
        ws.onmessage = (ev) => {
          try {
            apply(JSON.parse(ev.data) as LiveSnap);
          } catch {
            /* ping */
          }
        };
      };
    };
    void boot();
    return () => {
      stop = true;
      es?.close();
      ws?.close();
    };
  }, []);

  const feishu = snap?.channels?.feishu;
  const wecom = snap?.channels?.wecom;

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted">
        飞书 / 企业微信未连接时请用客户端扫码。连接成功后显示头像与在线绿钩，默认保持长连接。
      </p>
      {err && <p className="text-sm text-danger">{err}</p>}
      <div className="grid gap-3 sm:grid-cols-2">
        <ChannelCard
          item={feishu}
          fallbackType="feishu"
          onMsg={onMsg}
          onSnap={apply}
        />
        <ChannelCard item={wecom} fallbackType="wecom" onMsg={onMsg} onSnap={apply} />
      </div>
    </div>
  );
}

function ChannelCard({
  item,
  fallbackType,
  onMsg,
  onSnap,
}: {
  item?: ChannelLive;
  fallbackType: 'feishu' | 'wecom';
  onMsg: (s: string) => void;
  onSnap: (s: LiveSnap) => void;
}) {
  const type = item?.type || fallbackType;
  const brand = BRAND[type];
  const label = item?.label || (type === 'feishu' ? '飞书' : '企业微信');
  const connected = Boolean(item?.connected);
  const [busy, setBusy] = useState(false);

  const qr = useMemo(() => item?.qr_svg || '', [item?.qr_svg]);

  const act = async (path: string, okMsg: string) => {
    setBusy(true);
    try {
      const r = await api<LiveSnap>(path, { method: 'POST', body: '{}' });
      onSnap(r.data);
      onMsg(okMsg);
    } catch (e) {
      onMsg(e instanceof Error ? e.message : '操作失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card p-4">
      <div className="mb-3 flex items-center justify-between">
        <strong>{label}</strong>
        <span className={`text-[11px] ${connected ? 'text-success' : 'text-muted'}`}>
          {connected ? (item?.live ? '长连接在线' : '已绑定') : '未连接'}
        </span>
      </div>
      {connected ? (
        <div className="flex flex-col items-center gap-3 py-2">
          <div className="relative h-20 w-20">
            <img
              src={item?.avatar_url || brand.src}
              alt={label}
              className="h-20 w-20 rounded-full border object-cover"
              style={{ borderColor: brand.ring }}
            />
            <span className="absolute -bottom-0.5 -right-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-success text-[11px] font-bold text-white shadow-card">
              ✓
            </span>
          </div>
          <p className="text-sm">{item?.display_name || `${label}客户端`}</p>
          <p className="text-[11px] text-muted">默认保持长连接 · 心跳 15s</p>
          <div className="flex gap-2">
            <button className="ghost text-xs" disabled={busy} onClick={() => void act(`/api/v1/channels/live/${type}/disconnect`, `${label}已断开`)}>
              断开
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3">
          <div className="scope-frame bg-white p-2">
            {qr ? (
              <div className="h-40 w-40" dangerouslySetInnerHTML={{ __html: qr }} />
            ) : (
              <div className="flex h-40 w-40 items-center justify-center text-xs text-muted">正在生成二维码…</div>
            )}
          </div>
          <p className="text-center text-[11px] text-muted">打开{label}扫描二维码完成绑定</p>
          <div className="flex gap-2">
            <button className="ghost text-xs" disabled={busy} onClick={() => void act(`/api/v1/channels/live/${type}/refresh`, '已刷新二维码')}>
              刷新
            </button>
            <button className="text-xs" disabled={busy} onClick={() => void act(`/api/v1/channels/live/${type}/confirm`, `${label}已连接`)}>
              本机确认
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
