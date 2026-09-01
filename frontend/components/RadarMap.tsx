'use client';

import { useEffect, useRef } from 'react';

export type RadarNode = {
  id: string;
  type?: string;
  position?: { x: number; y: number };
  data?: {
    label?: string;
    kind?: string;
    stars?: number;
    star_delta?: number;
    fingerprint?: string | null;
    repo_id?: number;
    is_ai_skill?: boolean;
    keywords?: string[];
    html_url?: string;
  };
};

export type RadarEdge = {
  id: string;
  source: string;
  target: string;
  data?: { rel?: string };
};

const IFF: Record<string, string> = {
  claude_skill: '#00C48C',
  mcp_server: '#4F8CFF',
  langchain_tool: '#94A3B8',
  keyword: '#4F8CFF',
  default: '#4F8CFF',
};

function hashAngle(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i += 1) h = (h * 33 + id.charCodeAt(i)) >>> 0;
  return (h % 360) * (Math.PI / 180);
}

function polarOf(n: RadarNode, maxR: number): { r: number; a: number } {
  const stars = n.data?.stars ?? 0;
  const heat = Math.min(1, Math.log10(stars + 1) / 4);
  const r = 28 + (1 - heat) * Math.max(40, maxR - 48);
  return { r, a: hashAngle(n.id) };
}

export function RadarMap({
  nodes,
  edges = [],
  selectedId,
  onSelect,
  scanning = false,
}: {
  nodes: RadarNode[];
  edges?: RadarEdge[];
  selectedId?: string | null;
  onSelect?: (node: RadarNode) => void;
  scanning?: boolean;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const hover = useRef<RadarNode | null>(null);
  const layout = useRef<Map<string, { x: number; y: number; r: number; a: number }>>(new Map());

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    let frame = 0;
    let alive = true;
    let lastW = 0;
    let lastH = 0;
    const paint = () => {
      if (!alive) return;
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (w !== lastW || h !== lastH) {
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        lastW = w;
        lastH = h;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const cx = w / 2;
      const cy = h / 2 + 6;
      const maxR = Math.max(80, Math.min(w, h) * 0.42);

      ctx.fillStyle = '#070b10';
      ctx.fillRect(0, 0, w, h);
      const vignette = ctx.createRadialGradient(cx, cy, 8, cx, cy, maxR * 1.35);
      vignette.addColorStop(0, 'rgba(15, 28, 42, 0.9)');
      vignette.addColorStop(0.55, 'rgba(10, 16, 24, 0.35)');
      vignette.addColorStop(1, 'rgba(0, 0, 0, 0.55)');
      ctx.fillStyle = vignette;
      ctx.fillRect(0, 0, w, h);

      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, maxR + 10, 0, Math.PI * 2);
      ctx.clip();

      ctx.strokeStyle = 'rgba(79,140,255,0.07)';
      ctx.lineWidth = 1;
      for (let a = 0; a < 360; a += 10) {
        const rad = (a * Math.PI) / 180;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + Math.cos(rad) * maxR, cy + Math.sin(rad) * maxR);
        ctx.stroke();
      }

      const rings = [0.25, 0.5, 0.75, 1];
      rings.forEach((t, i) => {
        ctx.beginPath();
        ctx.strokeStyle = i === rings.length - 1 ? 'rgba(79,140,255,0.45)' : 'rgba(79,140,255,0.18)';
        ctx.lineWidth = i === rings.length - 1 ? 1.4 : 1;
        ctx.arc(cx, cy, maxR * t, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fillStyle = 'rgba(148,163,184,0.55)';
        ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
        ctx.fillText(`${Math.round(t * 100)}`, cx + 6, cy - maxR * t + 3);
      });

      ctx.strokeStyle = 'rgba(79,140,255,0.28)';
      ctx.beginPath();
      ctx.moveTo(cx - maxR, cy);
      ctx.lineTo(cx + maxR, cy);
      ctx.moveTo(cx, cy - maxR);
      ctx.lineTo(cx, cy + maxR);
      ctx.stroke();

      const headings = [
        [0, 'E'],
        [Math.PI / 2, 'S'],
        [Math.PI, 'W'],
        [-Math.PI / 2, 'N'],
      ] as const;
      ctx.fillStyle = '#4F8CFF';
      ctx.font = '11px ui-monospace, Menlo, Consolas, monospace';
      ctx.textAlign = 'center';
      headings.forEach(([a, label]) => {
        ctx.fillText(label, cx + Math.cos(a) * (maxR + 16), cy + Math.sin(a) * (maxR + 16) + 4);
      });
      ctx.textAlign = 'left';

      const speed = scanning ? 28 : 52;
      const sweep = ((frame / speed) % (Math.PI * 2)) - Math.PI / 2;
      const trail = scanning ? 48 : 36;
      for (let i = trail; i >= 0; i -= 1) {
        const ang = sweep - (i / trail) * 0.95;
        const alpha = (1 - i / trail) * 0.22;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.fillStyle = `rgba(79,140,255,${alpha})`;
        ctx.arc(cx, cy, maxR, ang - 0.04, ang + 0.02);
        ctx.closePath();
        ctx.fill();
      }
      const beam = ctx.createLinearGradient(cx, cy, cx + Math.cos(sweep) * maxR, cy + Math.sin(sweep) * maxR);
      beam.addColorStop(0, 'rgba(0,196,140,0)');
      beam.addColorStop(0.65, 'rgba(79,140,255,0.15)');
      beam.addColorStop(1, 'rgba(0,196,140,0.85)');
      ctx.strokeStyle = beam;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(sweep) * maxR, cy + Math.sin(sweep) * maxR);
      ctx.stroke();
      ctx.lineWidth = 1;

      ctx.fillStyle = '#00C48C';
      ctx.beginPath();
      ctx.arc(cx, cy, 3, 0, Math.PI * 2);
      ctx.fill();

      const nextLayout = new Map<string, { x: number; y: number; r: number; a: number }>();
      const contacts = nodes.filter((n) => n.type !== 'keyword');
      for (const n of contacts) {
        const p = polarOf(n, maxR);
        nextLayout.set(n.id, {
          x: cx + Math.cos(p.a) * p.r,
          y: cy + Math.sin(p.a) * p.r,
          r: p.r,
          a: p.a,
        });
      }
      layout.current = nextLayout;

      ctx.lineWidth = 1;
      for (const e of edges) {
        if (e.data?.rel !== 'RELATED_TO') continue;
        const a = nextLayout.get(e.source);
        const b = nextLayout.get(e.target);
        if (!a || !b) continue;
        ctx.strokeStyle = 'rgba(0,196,140,0.12)';
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }

      for (const n of contacts) {
        const pos = nextLayout.get(n.id);
        if (!pos) continue;
        const fp = n.data?.fingerprint || 'default';
        const color = IFF[fp] || IFF.default;
        const selected = n.id === selectedId;
        const lit = hover.current?.id === n.id || selected;
        const delta = ((pos.a - sweep + Math.PI * 2) % (Math.PI * 2));
        const justPainted = delta < 0.55 || delta > Math.PI * 2 - 0.08;
        const glow = justPainted ? 0.95 : 0.45;
        ctx.save();
        ctx.globalAlpha = glow;
        if (selected) {
          ctx.strokeStyle = color;
          ctx.strokeRect(pos.x - 8, pos.y - 8, 16, 16);
          ctx.beginPath();
          ctx.moveTo(pos.x, pos.y - 12);
          ctx.lineTo(pos.x, pos.y + 12);
          ctx.moveTo(pos.x - 12, pos.y);
          ctx.lineTo(pos.x + 12, pos.y);
          ctx.stroke();
        }
        ctx.fillStyle = color;
        ctx.shadowColor = color;
        ctx.shadowBlur = selected ? 16 : justPainted ? 10 : 4;
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, selected ? 4.5 : n.data?.is_ai_skill ? 3.4 : 2.6, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;
        if (lit) {
          ctx.fillStyle = '#E2E8F0';
          ctx.font = '11px ui-monospace, Menlo, Consolas, monospace';
          const label = String(n.data?.label || '');
          ctx.fillText(label, pos.x + 10, pos.y - 8);
          const az = ((pos.a * 180) / Math.PI + 90 + 360) % 360;
          ctx.fillStyle = '#94A3B8';
          ctx.fillText(`AZ ${az.toFixed(0).padStart(3, '0')}  R ${Math.round((pos.r / maxR) * 100)}`, pos.x + 10, pos.y + 6);
        }
        ctx.restore();
      }
      ctx.restore();

      ctx.fillStyle = 'rgba(148,163,184,0.7)';
      ctx.font = '10px ui-monospace, Menlo, Consolas, monospace';
      ctx.fillText('SKILLRADAR  //  PPI-A', 14, 18);
      ctx.fillText(`CNT ${contacts.length.toString().padStart(3, '0')}`, 14, 34);
      ctx.fillText(scanning ? 'MODE  SWEEP-FAST' : 'MODE  SEARCH', 14, 50);
      ctx.fillStyle = '#00C48C';
      ctx.fillText('IFF  SKL/MCP  ONLINE', w - 148, 18);
      ctx.fillStyle = 'rgba(148,163,184,0.45)';
      ctx.fillText('N-UP   BRG REL TRUE', w - 148, 34);

      frame += 1;
      requestAnimationFrame(paint);
    };
    paint();
    const hit = (ev: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const x = ev.clientX - rect.left;
      const y = ev.clientY - rect.top;
      let best: RadarNode | null = null;
      let bestD = 16;
      for (const n of nodes) {
        if (n.type === 'keyword') continue;
        const p = layout.current.get(n.id);
        if (!p) continue;
        const d = Math.hypot(p.x - x, p.y - y);
        if (d < bestD) {
          bestD = d;
          best = n;
        }
      }
      return best;
    };
    const onMove = (ev: MouseEvent) => {
      hover.current = hit(ev);
      canvas.style.cursor = hover.current ? 'pointer' : 'crosshair';
    };
    const onClick = (ev: MouseEvent) => {
      const n = hit(ev);
      if (n && onSelect) onSelect(n);
    };
    canvas.addEventListener('mousemove', onMove);
    canvas.addEventListener('click', onClick);
    return () => {
      alive = false;
      canvas.removeEventListener('mousemove', onMove);
      canvas.removeEventListener('click', onClick);
    };
  }, [nodes, edges, onSelect, selectedId, scanning]);

  return (
    <canvas
      ref={ref}
      className="radar-scope h-[420px] w-full cursor-crosshair rounded-xl sm:h-[560px]"
      aria-label="军事 PPI 情报雷达"
    />
  );
}
