import { useCallback, useEffect, useState } from 'react';
import { lumen, formatDateUk, lumenError } from '@/lib/lumenApi';
import {
  Activity, Database, Layers, HardDrive, FileSearch, AlertTriangle,
  ShieldCheck, LifeBuoy, Archive, Bug, Loader2, RefreshCw, ChevronDown,
  ChevronRight, CheckCircle2, XCircle, AlertCircle, Plus, Trash2,
  Server,
} from 'lucide-react';
import { Link } from 'react-router-dom';

const ICONS = {
  consistency:     <Layers className="w-5 h-5" />,
  db:              <Database className="w-5 h-5" />,
  queues:          <Activity className="w-5 h-5" />,
  storage:         <HardDrive className="w-5 h-5" />,
  file_audit:      <FileSearch className="w-5 h-5" />,
  failures:        <AlertTriangle className="w-5 h-5" />,
  security:        <ShieldCheck className="w-5 h-5" />,
  dr:              <LifeBuoy className="w-5 h-5" />,
  backups:         <Archive className="w-5 h-5" />,
  audit:           <Server className="w-5 h-5" />,
  error_tracking:  <Bug className="w-5 h-5" />,
};

const statusColor = (s) => {
  if (s === 'ok')      return { bg: 'rgba(16,185,129,0.10)', border: 'rgba(16,185,129,0.30)', text: 'rgb(5,150,105)' };
  if (s === 'warning') return { bg: 'rgba(245,158,11,0.10)', border: 'rgba(245,158,11,0.30)', text: 'rgb(180,83,9)' };
  return { bg: 'rgba(239,68,68,0.10)', border: 'rgba(239,68,68,0.30)', text: 'rgb(185,28,28)' };
};

const StatusIcon = ({ status, className }) => {
  if (status === 'ok')      return <CheckCircle2 className={className} style={{ color: 'rgb(5,150,105)' }} />;
  if (status === 'warning') return <AlertCircle className={className}  style={{ color: 'rgb(180,83,9)' }} />;
  return <XCircle className={className} style={{ color: 'rgb(185,28,28)' }} />;
};

function formatBytes(n) {
  if (n === null || n === undefined) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = Number(n); let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${units[i]}`;
}

export default function AdminSystemHealth() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [open, setOpen] = useState({});
  const [busy, setBusy] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await lumen.get('/admin/system-health');
      setData(r.data);
    } catch (e) {
      setError(lumenError(e, 'Не вдалось завантажити System Health'));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const createBackup = async () => {
    setBusy('backup');
    try {
      await lumen.post('/admin/backups', null, { params: { label: 'manual' } });
      await load();
    } catch (e) { setError(lumenError(e, 'Не вдалось створити бекап')); }
    finally { setBusy(''); }
  };

  const deleteBackup = async (id) => {
    if (!window.confirm(`Видалити бекап ${id}?`)) return;
    setBusy(id);
    try {
      await lumen.delete(`/admin/backups/${id}`);
      await load();
    } catch (e) { setError(lumenError(e, 'Не вдалось видалити бекап')); }
    finally { setBusy(''); }
  };

  if (loading && !data) {
    return (
      <div className="p-6 md:p-10" data-testid="admin-system-health-loading">
        <div className="space-y-3">
          {[1,2,3,4,5,6].map(i => <div key={i} className="h-24 rounded-2xl bg-muted/40 animate-pulse" />)}
        </div>
      </div>
    );
  }

  const overall = data?.overall || 'ok';
  const oc = statusColor(overall);

  return (
    <div className="p-6 md:p-10" data-testid="admin-system-health">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-widest text-token-muted">Sprint 10 · Production Hardening</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">System Health</h1>
          <p className="mt-1 text-token-muted text-sm">
            Цілісність даних, безпека, моніторинг та аудит. Перевірено: {formatDateUk(data?.checked_at)}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div
            className="px-3 py-1.5 rounded-full text-sm font-semibold flex items-center gap-2"
            style={{ background: oc.bg, border: `1px solid ${oc.border}`, color: oc.text }}
            data-testid="health-overall-badge"
          >
            <StatusIcon status={overall} className="w-4 h-4" />
            {overall === 'ok' ? 'Все добре' : overall === 'warning' ? 'Попередження' : 'Виявлено проблеми'}
          </div>
          <Link
            to="/admin/audit-log"
            className="px-3 py-1.5 rounded-full text-sm bg-card border border-border hover:bg-muted/50"
            data-testid="link-audit-log"
          >
            Audit Trail →
          </Link>
          <button
            onClick={load}
            className="px-3 py-1.5 rounded-full text-sm bg-card border border-border hover:bg-muted/50 flex items-center gap-2"
            data-testid="btn-refresh-health"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Оновити
          </button>
        </div>
      </header>

      {error && (
        <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>
      )}

      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3" data-testid="health-cards">
        {(data?.cards || []).map((card) => {
          const c = statusColor(card.summary.status);
          const isOpen = !!open[card.key];
          return (
            <div
              key={card.key}
              className="rounded-2xl border bg-card overflow-hidden"
              style={{ borderColor: 'var(--token-border)' }}
              data-testid={`health-card-${card.key}`}
            >
              <button
                onClick={() => setOpen(s => ({ ...s, [card.key]: !s[card.key] }))}
                className="w-full text-left p-4 hover:bg-muted/30 flex items-start gap-3"
              >
                <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                  style={{ background: c.bg, color: c.text, border: `1px solid ${c.border}` }}>
                  {ICONS[card.key] || <Activity className="w-5 h-5" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-sm text-token-primary">{card.title}</h3>
                    <StatusIcon status={card.summary.status} className="w-3.5 h-3.5" />
                  </div>
                  <p className="text-xs text-token-muted mt-0.5 truncate">{card.summary.label}</p>
                </div>
                {isOpen ? <ChevronDown className="w-4 h-4 text-token-muted shrink-0" /> : <ChevronRight className="w-4 h-4 text-token-muted shrink-0" />}
              </button>
              {isOpen && (
                <div className="border-t border-border p-4 bg-muted/20 text-xs">
                  {card.key === 'consistency' && <ConsistencyDetail data={card.data} />}
                  {card.key === 'db' && <KVDetail data={card.data} />}
                  {card.key === 'queues' && <QueuesDetail data={card.data} />}
                  {card.key === 'storage' && <StorageDetail data={card.data} />}
                  {card.key === 'file_audit' && <FileAuditDetail data={card.data} />}
                  {card.key === 'failures' && <KVDetail data={card.data} />}
                  {card.key === 'security' && <SecurityDetail data={card.data} />}
                  {card.key === 'dr' && <DRDetail data={card.data} />}
                  {card.key === 'audit' && <KVDetail data={card.data} />}
                  {card.key === 'error_tracking' && <KVDetail data={card.data} />}
                  {card.key === 'backups' && (
                    <BackupsDetail data={card.data} onCreate={createBackup} onDelete={deleteBackup} busy={busy} />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

const Row = ({ k, v }) => (
  <div className="flex items-center justify-between py-1.5 border-b border-border/30 last:border-0">
    <span className="text-token-muted">{k}</span>
    <span className="font-mono">{String(v)}</span>
  </div>
);

function KVDetail({ data }) {
  if (!data) return null;
  const entries = Object.entries(data).filter(([, v]) => typeof v !== 'object' || v === null);
  return <div>{entries.map(([k, v]) => <Row key={k} k={k} v={v} />)}</div>;
}

function ConsistencyDetail({ data }) {
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-3 gap-2 text-xs mb-2">
        <div><span className="text-token-muted">Загалом:</span> <span className="font-semibold">{data?.overall}</span></div>
        <div><span className="text-token-muted">Broken:</span> <span className="font-semibold text-red-600">{data?.broken}</span></div>
        <div><span className="text-token-muted">Warnings:</span> <span className="font-semibold" style={{ color: 'rgb(180,83,9)' }}>{data?.warnings}</span></div>
      </div>
      <div className="space-y-1.5">
        {(data?.checks || []).map((c) => (
          <div key={c.code} className="flex items-start gap-2 p-2 rounded-lg bg-card border border-border">
            <StatusIcon status={c.status} className="w-3.5 h-3.5 mt-0.5" />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-muted">{c.code}</span>
                <span className="font-semibold truncate">{c.name}</span>
                {c.breaches > 0 && <span className="text-red-600 font-mono">×{c.breaches}</span>}
              </div>
              <p className="text-token-muted text-[11px] mt-0.5">{c.details}</p>
              {c.sample?.length > 0 && (
                <pre className="mt-1 text-[10px] bg-muted/40 p-1.5 rounded overflow-x-auto leading-tight">{JSON.stringify(c.sample, null, 1)}</pre>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function QueuesDetail({ data }) {
  return (
    <div className="space-y-1.5">
      {(data?.queues || []).map((q) => (
        <div key={q.queue} className="flex items-center justify-between py-1 border-b border-border/30 last:border-0">
          <span className="text-token-muted">{q.queue}</span>
          <div className="flex items-center gap-2">
            <span className="font-mono">{q.depth} / {q.threshold}</span>
            <StatusIcon status={q.healthy ? 'ok' : 'warning'} className="w-3.5 h-3.5" />
          </div>
        </div>
      ))}
    </div>
  );
}

function StorageDetail({ data }) {
  return (
    <div className="space-y-2">
      <Row k="Uploads" v={formatBytes(data?.uploads_total_bytes)} />
      <Row k="Backups" v={formatBytes(data?.backups_total_bytes)} />
      <Row k="Disk used %" v={`${data?.disk?.used_pct ?? '—'}%`} />
      <Row k="Disk free" v={formatBytes(data?.disk?.free_bytes)} />
      <div className="mt-2 pt-2 border-t border-border/40">
        <div className="text-token-muted mb-1">Breakdown:</div>
        {Object.entries(data?.uploads_breakdown_bytes || {}).map(([k, v]) => <Row key={k} k={k} v={formatBytes(v)} />)}
      </div>
    </div>
  );
}

function FileAuditDetail({ data }) {
  return (
    <div className="space-y-2">
      {Object.entries(data?.findings || {}).map(([area, f]) => (
        <div key={area} className="p-2 rounded-lg bg-card border border-border">
          <div className="font-semibold capitalize mb-1">{area}</div>
          <Row k="on disk" v={f.on_disk} />
          <Row k="referenced" v={f.referenced} />
          <Row k="orphan files" v={f.orphan_files} />
          <Row k="missing files" v={f.missing_files} />
        </div>
      ))}
    </div>
  );
}

function SecurityDetail({ data }) {
  return (
    <div className="space-y-2">
      <Row k="Scope" v={data?.scope} />
      <Row k="Checked" v={data?.checked} />
      <Row k="Broken" v={data?.broken} />
      <Row k="Skipped (non-lumen)" v={data?.skipped_non_lumen} />
      {data?.sample?.length > 0 && (
        <div className="mt-2 space-y-1">
          <div className="font-semibold">Broken endpoints:</div>
          {data.sample.map((s, i) => (
            <div key={i} className="p-1.5 rounded bg-red-50 border border-red-200 text-red-700 text-[10px]">
              <span className="font-mono">{s.methods.join(',')} {s.path}</span> — expected {s.expected}, got {s.actual_guards.join(',')}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DRDetail({ data }) {
  return (
    <div className="space-y-2">
      <Row k="Healthy" v={String(data?.healthy)} />
      <Row k="Scenarios found" v={data?.scenario_count} />
      {(data?.findings || []).map((f, i) => (
        <div key={i} className="p-2 rounded-lg bg-card border border-border">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] px-1.5 py-0.5 rounded"
              style={{ background: f.severity === 'high' ? 'rgba(239,68,68,0.10)' : 'rgba(245,158,11,0.10)',
                       color: f.severity === 'high' ? 'rgb(185,28,28)' : 'rgb(180,83,9)' }}>{f.severity}</span>
            <span className="font-semibold">{f.scenario}</span>
          </div>
          <p className="mt-1 text-token-muted">{f.detail}</p>
          {f.count !== undefined && <Row k="count" v={f.count} />}
        </div>
      ))}
    </div>
  );
}

function BackupsDetail({ data, onCreate, onDelete, busy }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Row k="Total backups" v={data?.total ?? 0} />
        <button
          onClick={onCreate}
          disabled={busy === 'backup'}
          className="ml-2 px-2 py-1 text-[11px] rounded-md bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50 flex items-center gap-1"
          data-testid="btn-create-backup"
        >
          {busy === 'backup' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
          Створити бекап
        </button>
      </div>
      {(data?.items || []).map((b) => (
        <div key={b.id} className="p-2 rounded-lg bg-card border border-border">
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="font-mono text-[11px] truncate">{b.id}</div>
              <div className="text-token-muted text-[10px]">{formatBytes(b.size_bytes)} · {formatDateUk(b.manifest?.created_at)}</div>
            </div>
            <button
              onClick={() => onDelete(b.id)}
              disabled={busy === b.id}
              className="p-1 rounded text-red-600 hover:bg-red-50 disabled:opacity-50"
              data-testid={`btn-delete-backup-${b.id}`}
              title="Видалити"
            >
              {busy === b.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
