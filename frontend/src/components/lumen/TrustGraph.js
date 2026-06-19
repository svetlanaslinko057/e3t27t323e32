import { useMemo } from 'react';

/**
 * Trust Graph (G10) — layered SVG visualization of the ownership chain
 *   Investor → Certificate → SPV → Operator/Fund → Asset
 * Pure SVG, no external deps. Nodes grouped into columns by type.
 */
const COLUMN = { investor: 0, certificate: 1, spv: 2, fund: 3, operator: 3, asset: 4 };
const COL_LABELS = ['Інвестори', 'Сертифікати', 'SPV', 'Фонд / Оператор', 'Активи'];
const TYPE_COLOR = {
  investor: '#2563eb', certificate: '#7c3aed', spv: '#0891b2',
  fund: '#9333ea', operator: '#2E5D4F', asset: '#d97706',
};

export default function TrustGraph({ data, height = 520 }) {
  const { nodes = [], edges = [] } = data || {};

  const layout = useMemo(() => {
    const cols = [[], [], [], [], []];
    nodes.forEach((n) => {
      const c = COLUMN[n.type] ?? 0;
      cols[c].push(n);
    });
    const colW = 230;
    const nodeH = 46;
    const gap = 14;
    const maxRows = Math.max(1, ...cols.map((c) => c.length));
    const svgH = Math.max(height, maxRows * (nodeH + gap) + 60);
    const pos = {};
    cols.forEach((col, ci) => {
      const totalH = col.length * (nodeH + gap);
      const startY = (svgH - totalH) / 2 + 30;
      col.forEach((n, ri) => {
        pos[n.id] = { x: ci * colW + 20, y: startY + ri * (nodeH + gap), w: colW - 50, h: nodeH };
      });
    });
    return { pos, svgW: 5 * colW, svgH, nodeH };
  }, [nodes, height]);

  if (!nodes.length) {
    return <div className="text-sm text-muted-foreground py-12 text-center">Немає даних для побудови графа.</div>;
  }

  return (
    <div className="overflow-auto rounded-2xl border border-border bg-card" data-testid="trust-graph">
      <svg width={layout.svgW} height={layout.svgH} style={{ minWidth: layout.svgW }}>
        {COL_LABELS.map((l, i) => (
          <text key={l} x={i * 230 + 20} y={20} fontSize={11} fontWeight={700} fill="currentColor" opacity={0.55}>{l.toUpperCase()}</text>
        ))}
        {edges.map((e, i) => {
          const a = layout.pos[e.from]; const b = layout.pos[e.to];
          if (!a || !b) return null;
          const x1 = a.x + a.w, y1 = a.y + a.h / 2, x2 = b.x, y2 = b.y + b.h / 2;
          const mx = (x1 + x2) / 2;
          return <path key={i} d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`} fill="none" stroke="currentColor" strokeOpacity={0.18} strokeWidth={1.5} />;
        })}
        {nodes.map((n) => {
          const p = layout.pos[n.id]; if (!p) return null;
          const color = TYPE_COLOR[n.type] || '#64748b';
          return (
            <g key={n.id}>
              <rect x={p.x} y={p.y} width={p.w} height={p.h} rx={10} fill={color} fillOpacity={0.10} stroke={color} strokeOpacity={0.5} />
              <rect x={p.x} y={p.y} width={4} height={p.h} rx={2} fill={color} />
              <text x={p.x + 12} y={p.y + 19} fontSize={12} fontWeight={600} fill="currentColor">{truncate(n.label, 24)}</text>
              <text x={p.x + 12} y={p.y + 34} fontSize={10} fill="currentColor" opacity={0.6}>
                {n.type}{n.verified ? ' · ✓' : ''}{n.ownership_percent != null ? ` · ${n.ownership_percent}%` : ''}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function truncate(s, n) { s = String(s || ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; }
