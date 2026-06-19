import { useCallback, useEffect, useState } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import {
  ShieldCheck, Loader2, CheckCircle2, AlertTriangle, Clock, XCircle,
  FileCheck2, Plus,
} from 'lucide-react';

const STATUS_STYLE = {
  approved: { cls: 'text-emerald-600', icon: CheckCircle2 },
  verified: { cls: 'text-emerald-600', icon: CheckCircle2 },
  provided: { cls: 'text-sky-600', icon: FileCheck2 },
  under_review: { cls: 'text-sky-600', icon: Clock },
  pending: { cls: 'text-amber-600', icon: Clock },
  self_declared: { cls: 'text-sky-600', icon: FileCheck2 },
  missing: { cls: 'text-muted-foreground', icon: AlertTriangle },
  rejected: { cls: 'text-red-600', icon: XCircle },
  expired: { cls: 'text-red-600', icon: AlertTriangle },
  not_started: { cls: 'text-muted-foreground', icon: AlertTriangle },
};

function ScoreRing({ score }) {
  const r = 52, c = 2 * Math.PI * r;
  const color = score >= 90 ? '#059669' : score >= 60 ? '#0284c7' : '#d97706';
  return (
    <div className="relative w-[140px] h-[140px]" data-testid="compliance-score-ring">
      <svg width="140" height="140" className="-rotate-90">
        <circle cx="70" cy="70" r={r} fill="none" stroke="currentColor" strokeWidth="12" className="text-muted/40" />
        <circle cx="70" cy="70" r={r} fill="none" stroke={color} strokeWidth="12" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c - (c * score) / 100} style={{ transition: 'stroke-dashoffset .6s' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-3xl font-bold" style={{ color }}>{score}</div>
        <div className="text-[10px] uppercase tracking-widest text-muted-foreground">/ 100</div>
      </div>
    </div>
  );
}

export default function InvestorCompliance() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    try { const r = await lumen.get('/investor/compliance'); setData(r.data); }
    catch (e) { setErr(lumenError(e)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const attest = async (slot) => {
    setBusy(slot); setErr('');
    try { await lumen.post('/investor/compliance/attest', { slot, valid_months: 12 }); await load(); }
    catch (e) { setErr(lumenError(e)); } finally { setBusy(null); }
  };

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;

  const bandLabel = { ready: 'Готово до інституційного онбордингу', partial: 'Частково заповнено', incomplete: 'Неповний профіль' };
  const attestableMissing = (data.items || []).filter(
    (i) => ['sof', 'aml_questionnaire', 'tax_form', 'risk_acknowledgement', 'voting_consent'].includes(i.key)
      && ['missing', 'expired', 'rejected'].includes(i.status));

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6" data-testid="investor-compliance">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Phase G15 · Compliance Vault</div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><ShieldCheck className="w-5 h-5 text-[#2E5D4F]" /> Комплаєнс-профіль</h1>
        <p className="text-sm text-muted-foreground mt-1">Єдиний реєстр усіх ваших комплаєнс-документів для онбордингу.</p>
      </div>

      {/* score header */}
      <div className="rounded-2xl border border-border bg-card p-6 flex flex-col sm:flex-row items-center gap-6">
        <ScoreRing score={data.score} />
        <div className="flex-1">
          <div className={`text-sm font-semibold ${data.institutional_ready ? 'text-emerald-600' : 'text-amber-600'}`}>
            {bandLabel[data.score_band]}
          </div>
          {data.reasons.length > 0 ? (
            <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
              {data.reasons.map((r, i) => <li key={i} className="flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5 text-amber-500" />{r}</li>)}
            </ul>
          ) : <div className="mt-2 text-sm text-emerald-600 flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4" />Усі обов'язкові документи надані.</div>}
          <div className="mt-3 flex gap-4 text-xs text-muted-foreground">
            <span>Сертифікатів: <b className="text-foreground">{data.certificates}</b></span>
            <span>Підписаних договорів: <b className="text-foreground">{data.contracts_signed}</b></span>
            <span>UBO: <b className="text-foreground">{data.ubo_count}</b></span>
          </div>
        </div>
      </div>

      {/* expirations */}
      {data.expirations.length > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4" data-testid="compliance-expirations">
          <div className="text-sm font-semibold text-amber-900 flex items-center gap-1.5"><Clock className="w-4 h-4" />Терміни дії</div>
          <ul className="mt-2 space-y-1 text-sm text-amber-900">
            {data.expirations.map((e) => (
              <li key={e.key}>{e.label}: {e.expired ? <b>прострочено</b> : <span>спливає через {e.days_left} дн.</span>}</li>
            ))}
          </ul>
        </div>
      )}

      {/* checklist */}
      <div className="rounded-2xl border border-border bg-card divide-y divide-border overflow-hidden" data-testid="compliance-checklist">
        {data.items.map((it) => {
          const st = STATUS_STYLE[it.status] || STATUS_STYLE.missing;
          const Icon = st.icon;
          const canAttest = ['sof', 'aml_questionnaire', 'tax_form', 'risk_acknowledgement', 'voting_consent'].includes(it.key)
            && ['missing', 'expired', 'rejected'].includes(it.status);
          return (
            <div key={it.key} className="px-4 py-3 flex items-center justify-between gap-3" data-testid={`compliance-item-${it.key}`}>
              <div className="flex items-center gap-3">
                <Icon className={`w-5 h-5 ${st.cls}`} />
                <div>
                  <div className="font-medium text-sm flex items-center gap-2">{it.label}{it.required && <span className="text-[10px] text-muted-foreground">обов'язково</span>}</div>
                  <div className="text-[11px] text-muted-foreground">{it.detail ? `${it.detail} · ` : ''}вага {it.weight}</div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className={`text-xs font-medium ${st.cls}`}>{it.status_label}</span>
                {canAttest && (
                  <button onClick={() => attest(it.key)} disabled={busy === it.key} data-testid={`attest-${it.key}`}
                    className="h-8 px-3 rounded-lg text-xs bg-[#2E5D4F] text-white inline-flex items-center gap-1 hover:opacity-90 disabled:opacity-50">
                    {busy === it.key ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}Надати
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
      {err && <p className="text-sm text-red-600">{err}</p>}
      {attestableMissing.length > 0 && (
        <p className="text-xs text-muted-foreground">Натисніть «Надати», щоб задекларувати документ (самодекларація). Комплаєнс-офіцер перевірить його згодом.</p>
      )}
    </div>
  );
}
