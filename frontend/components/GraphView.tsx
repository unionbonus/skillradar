'use client';

import { useMemo } from 'react';
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

const KIND: Record<string, string> = {
  repository: '#4F8CFF',
  skill: '#00C48C',
  tool: '#4F8CFF',
  module: '#94A3B8',
  prompt: '#4F8CFF',
  external: '#FF6B6B',
  keyword: '#94A3B8',
};

export function GraphView({ nodes, edges }: { nodes: Node[]; edges: Edge[] }) {
  const layoutNodes = useMemo(
    () =>
      nodes.map((n, i) => {
        const kind = (n.data as { kind?: string } | undefined)?.kind || n.type || 'module';
        return {
          ...n,
          position: n.position || { x: (i % 6) * 180, y: Math.floor(i / 6) * 110 },
          style: {
            border: `1px solid ${KIND[kind] || '#4F8CFF'}`,
            background: '#1A2029',
            color: '#E2E8F0',
            borderRadius: 10,
            padding: 6,
            fontSize: 12,
          },
        };
      }),
    [nodes],
  );
  return (
    <div className="h-[520px] w-full rounded-xl border border-line bg-panel">
      <ReactFlow nodes={layoutNodes} edges={edges} fitView>
        <MiniMap />
        <Controls />
        <Background />
      </ReactFlow>
    </div>
  );
}