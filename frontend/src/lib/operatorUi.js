/**
 * Shared UI primitives + maps for the Operator OS (Phase F) surfaces.
 * Used by the operator portal, admin operator detail, and public leaderboard.
 */
import { ShieldCheck, ShieldAlert, ShieldX, BadgeCheck } from 'lucide-react';

export const PRIMARY = '#2E5D4F';

// ── SLA status ───────────────────────────────────────────────────────────────
export const SLA_TONE = {
  ok: { label: 'Гаразд', cls: 'bg-emerald-100 text-emerald-700 border-emerald-300', dot: 'bg-emerald-500' },
  warning: { label: 'Попередження', cls: 'bg-amber-100 text-amber-700 border-amber-300', dot: 'bg-amber-500' },
  critical: { label: 'Критично', cls: 'bg-orange-100 text-orange-700 border-orange-300', dot: 'bg-orange-500' },
  escalation: { label: 'Ескалація', cls: 'bg-rose-100 text-rose-700 border-rose-300', dot: 'bg-rose-500' },
};

export const slaTone = (status) => SLA_TONE[status] || SLA_TONE.ok;

// ── Verification status ──────────────────────────────────────────────────────
export const VERIFICATION_TONE = {
  draft: 'bg-muted text-muted-foreground border-border',
  applied: 'bg-sky-100 text-sky-700 border-sky-300',
  verified: 'bg-emerald-100 text-emerald-700 border-emerald-300',
  approved: 'bg-emerald-100 text-emerald-700 border-emerald-300',
  restricted: 'bg-amber-100 text-amber-700 border-amber-300',
  suspended: 'bg-rose-100 text-rose-700 border-rose-300',
};

export const VERIFICATION_LABELS = {
  draft: 'Чернетка', applied: 'Подано заявку', verified: 'Перевірено',
  approved: 'Затверджено', restricted: 'Обмежено', suspended: 'Призупинено',
};

// ── Reputation grade colour ──────────────────────────────────────────────────
export const gradeTone = (grade) => {
  const g = String(grade || '').toUpperCase();
  if (g.startsWith('AAA')) return 'text-emerald-600';
  if (g.startsWith('AA')) return 'text-emerald-600';
  if (g.startsWith('A')) return 'text-lime-600';
  if (g.startsWith('BBB')) return 'text-amber-600';
  if (g.startsWith('BB')) return 'text-orange-600';
  return 'text-rose-600';
};

export const scoreTone = (score) => {
  const s = Number(score || 0);
  if (s >= 80) return '#059669';
  if (s >= 65) return '#65a30d';
  if (s >= 50) return '#d97706';
  if (s >= 35) return '#ea580c';
  return '#e11d48';
};

// ── Components ────────────────────────────────────────────────────────────────
export function StatusPill({ status, label }) {
  const t = slaTone(status);
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11px] font-medium px-2 py-0.5 rounded-full border ${t.cls}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${t.dot}`} />
      {label || t.label}
    </span>
  );
}

export function VerifiedBadge({ verified, status, statusLabel }) {
  if (verified) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-[#2E5D4F] text-white">
        <BadgeCheck className="w-3.5 h-3.5" /> Verified Operator
      </span>
    );
  }
  const cls = VERIFICATION_TONE[status] || VERIFICATION_TONE.draft;
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full border ${cls}`}>
      {statusLabel || VERIFICATION_LABELS[status] || status}
    </span>
  );
}

export function KpiCard({ label, value, sub, accent }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-2xl font-bold mt-1" style={accent ? { color: accent } : undefined}>{value}</div>
      {sub && <div className="text-[11px] text-muted-foreground mt-0.5">{sub}</div>}
    </div>
  );
}

export function ReputationRing({ score, grade, size = 96 }) {
  const s = Math.max(0, Math.min(100, Number(score || 0)));
  const tone = scoreTone(s);
  const deg = s * 3.6;
  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <div className="rounded-full" style={{ width: size, height: size, background: `conic-gradient(${tone} ${deg}deg, var(--muted, #e5e7eb) ${deg}deg)` }} />
      <div className="absolute rounded-full bg-card flex flex-col items-center justify-center" style={{ width: size - 18, height: size - 18 }}>
        <span className="text-xl font-bold" style={{ color: tone }}>{s.toFixed(0)}</span>
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{grade}</span>
      </div>
    </div>
  );
}

export function SeverityIcon({ severity }) {
  if (severity === 'escalation' || severity === 'critical') return <ShieldX className="w-4 h-4 text-rose-600" />;
  if (severity === 'warning') return <ShieldAlert className="w-4 h-4 text-amber-600" />;
  return <ShieldCheck className="w-4 h-4 text-emerald-600" />;
}
