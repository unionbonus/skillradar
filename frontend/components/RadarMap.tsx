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

const COLORS: Record<string, string> = {
  claude_skill: '#7ee0ff',
  mcp_server: '#86f0c6',
  langchain_tool: '#f7c56b',
  keyword: '#c9b6ff',
  default: '#8aa4c7',
};

type Xform = { mapX: (x: number) => number; mapY: (y: number) => number };

function makeXform(nodes: RadarNode[], w: number, h: number): Xform {
  const repos = nodes.filter((n) => n.type === 'repository' || n.data?.kind === 'repository');
  if (!repos.length) {
    return { mapX: (x) => x, mapY: (y) => y };
  }
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const n of repos) {
    const x = n.position?.x ?? 0;
    const y = n.position?.y ?? 0;
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  }
  if (!(maxX > minX) || !(maxY > minY)) {
    const ox = Number.isFinite(minX) ? minX : 420;
    const oy = Number.isFinite(minY) ? minY : 300;
    return {
      mapX: (x) => w / 2 + (x - ox),
      mapY: (y) => h / 2 + (y - oy),
    };
  }
  const sx = (w - 80) / (maxX - minX);
  const sy = (h - 80) / (maxY - minY);
  const sc = Math.min(sx, sy, 1.35);
  return {
    mapX: (x) => 40 + (x - minX) * sc,
    mapY: (y) => 40 + (y - minY) * sc,
  };
}

export function RadarMap({
  nodes,
  edges = [],
  selectedId,
  onSelect,
}: {
  nodes: RadarNode[];
  edges?: RadarEdge[];
  selectedId?: string | null;
  onSelect?: (node: RadarNode) => void;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const hover = useRef<RadarNode | null>(null);
  const xf = useRef<Xform>({ mapX: (x) => x, mapY: (y) => y });

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
      xf.current = makeXform(nodes, w, h);
      ctx.clearRect(0, 0, w, h);
      const cx = w / 2;
      const cy = h / 2;
      ctx.strokeStyle = 'rgba(62,198,255,0.18)';
      for (let r = 70; r <= 260; r += 64) {
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.stroke();
      }
      const sweep = (frame / 48) % (Math.PI * 2);
      const grad = ctx.createLinearGradient(cx, cy, cx + Math.cos(sweep) * 280, cy + Math.sin(sweep) * 280);
      grad.addColorStop(0, 'rgba(62,198,255,0)');
      grad.addColorStop(1, 'rgba(62,198,255,0.35)');
      ctx.strokeStyle = grad;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(sweep) * 280, cy + Math.sin(sweep) * 280);
      ctx.stroke();
      ctx.fillStyle = 'rgba(62,198,255,0.08)';
      ctx.beginPath();
      ctx.arc(cx, cy, 16 + Math.sin(frame / 18) * 3, 0, Math.PI * 2);
      ctx.fill();

      const xy = new Map<string, { x: number; y: number }>();
      for (const n of nodes) {
        if (n.type === 'keyword') continue;
        xy.set(n.id, {
          x: xf.current.mapX(n.position?.x ?? cx),
          y: xf.current.mapY(n.position?.y ?? cy),
        });
      }
      ctx.lineWidth = 1;
      for (const e of edges) {
        if (e.data?.rel !== 'RELATED_TO') continue;
        const a = xy.get(e.source);
        const b = xy.get(e.target);
        if (!a || !b) continue;
        ctx.strokeStyle = 'rgba(134,240,198,0.16)';
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }

      for (const n of nodes) {
        if (n.type === 'keyword') continue;
        const pos = xy.get(n.id);
        if (!pos) continue;
        const { x, y } = pos;
        const fp = n.data?.fingerprint || 'default';
        const color = COLORS[fp] || COLORS.default;
        const pulse = n.id === selectedId ? 7 : 4 + (n.data?.is_ai_skill ? 2 : 0);
        ctx.beginPath();
        ctx.fillStyle = color;
        ctx.shadowColor = color;
        ctx.shadowBlur = n.id === selectedId ? 18 : 8;
        ctx.arc(x, y, pulse, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;
        if (hover.current?.id === n.id || n.id === selectedId) {
          ctx.fillStyle = '#e8f6ff';
          ctx.font = '12px sans-serif';
          ctx.fillText(String(n.data?.label || ''), x + 10, y - 8);
        }
      }
      frame += 1;
      requestAnimationFrame(paint);
    };
    paint();
    const hit = (ev: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const x = ev.clientX - rect.left;
      const y = ev.clientY - rect.top;
      return (
        nodes.find((n) => {
          if (n.type === 'keyword') return false;
          const nx = xf.current.mapX(n.position?.x ?? 0);
          const ny = xf.current.mapY(n.position?.y ?? 0);
          return Math.hypot(nx - x, ny - y) < 14;
        }) || null
      );
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
  }, [nodes, edges, onSelect, selectedId]);

  return <canvas ref={ref} className="h-[560px] w-full cursor-crosshair rounded-2xl border border-line bg-[#06101c]" />;
}
