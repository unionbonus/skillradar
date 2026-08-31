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
  repository: '#3ec6ff',
  skill: '#86f0c6',
  tool: '#f7c56b',
  module: '#9bb6d4',
  prompt: '#c9b6ff',
  external: '#f08a8a',
  keyword: '#e8d27a',
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
            border: `1px solid ${KIND[kind] || '#8aa4c7'}`,
            background: '#10233a',
            color: '#d7e6f5',
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
