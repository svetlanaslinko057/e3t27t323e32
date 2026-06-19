/**
 * InvestorCertificates — LUMEN 2.0 / Phase A2.
 * "Мої сертифікати" — investor-facing Investment Certificates issued on top of
 * the unit registry. Active + historical, PDF download, public verify link,
 * per-certificate event history.
 */
import { useEffect, useState, useCallback } from 'react';
import {
  Award, Download, ShieldCheck, ExternalLink, Activity, ArrowLeft,
  RefreshCw, FileText, Clock, CheckCircle2, XCircle, RefreshCcw,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/components/Toast';
import { formatUAH, formatDateUk } from '@/lib/lumenApi';
import { trackEvent } from '@/lib/activityTracker';

const nfmt = (n) => (n === null || n === undefined || isNaN(n))
  ? '—' : Number(n).toLocaleString('uk-UA', { maximumFractionDigits: 0 });

const STATUS_META = {
  active:   { label: 'Активний',  cls: 'text-emerald-600 bg-emerald-500/10', icon: CheckCircle2 },
  voided:   { label: 'Анульовано', cls: 'text-rose-600 bg-rose-500/10',      icon: XCircle },
  replaced: { label: 'Замінено',  cls: 'text-amber-600 bg-amber-500/10',     icon: RefreshCcw },
  expired:  { label: 'Прострочено', cls: 'text-token-muted bg-app-elevated', icon: Clock },
  draft:    { label: 'Чернетка',  cls: 'text-token-muted bg-app-elevated',   icon: FileText },
};

const EVENT_LABEL = {
  issued: 'Випущено', voided: 'Анульовано', reissued: 'Перевипущено',
  transferred: 'Передано', verified: 'Перевірено', downloaded: 'Завантажено',
};

function StatusBadge({ status }) {
  const m = STATUS_META[status] || STATUS_META.draft;
  const Icon = m.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-lg ${m.cls}`}>
      <Icon className="w-3.5 h-3.5" /> {m.label}
    </span>
  );
}

function CertCard({ c, onPdf, onHistory }) {
  return (
    <div className="rounded-2xl border border-app bg-app-surface overflow-hidden" data-testid={`cert-${c.id}`}>
      <div className="h-1.5 bg-[#2E5D4F]" />
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[11px] uppercase tracking-wider font-bold text-token-muted">Сертифікат</div>
            <div className="text-lg font-bold text-token-primary tabular-nums">{c.certificate_number}</div>
          </div>
          <StatusBadge status={c.status} />
        </div>
        <h3 className="mt-3 font-semibold text-token-primary truncate">{c.asset_title}</h3>
        <div className="text-[12px] text-token-muted">{c.spv_name}</div>

        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          <div>
            <div className="text-base font-bold text-token-primary tabular-nums">{nfmt(c.units)}</div>
            <div className="text-[10px] uppercase tracking-wider text-token-muted">одиниць</div>
          </div>
          <div>
            <div className="text-base font-bold text-[#2E5D4F] tabular-nums">{Number(c.ownership_percent).toFixed(2)}%</div>
            <div className="text-[10px] uppercase tracking-wider text-token-muted">частка</div>
          </div>
          <div>
            <div className="text-base font-bold text-token-primary tabular-nums">{formatUAH(c.value_uah)}</div>
            <div className="text-[10px] uppercase tracking-wider text-token-muted">вартість</div>
          </div>
        </div>

        <div className="mt-3 text-[12px] text-token-muted">Випущено {formatDateUk(c.issue_date)} · код {c.verify_code}</div>

        <div className="mt-4 flex items-center gap-2 flex-wrap">
          <button onClick={() => onPdf(c)} data-testid={`cert-pdf-${c.id}`}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-[#2E5D4F] text-white text-xs font-semibold hover:bg-[#274f43] transition">
            <Download className="w-3.5 h-3.5" /> PDF
          </button>
          <a href={`/certificates/verify/${c.verify_code}`} target="_blank" rel="noreferrer"
            data-testid={`cert-verify-${c.id}`}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-app text-xs font-semibold text-token-secondary hover:text-token-primary hover:border-app-strong transition">
            <ShieldCheck className="w-3.5 h-3.5" /> Перевірити <ExternalLink className="w-3 h-3" />
          </a>
          <button onClick={() => onHistory(c)} data-testid={`cert-history-${c.id}`}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-app text-xs font-semibold text-token-secondary hover:text-token-primary hover:border-app-strong transition">
            <Activity className="w-3.5 h-3.5" /> Історія
          </button>
        </div>
      </div>
    </div>
  );
}

export default function InvestorCertificates() {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [drawer, setDrawer] = useState(null);
  const [events, setEvents] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.get('/investor/certificates'));
    } catch {
      toast.error('Не вдалось завантажити сертифікати');
    } finally { setLoading(false); }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const certs = (data?.active || []).concat(data?.history || []);
    if (certs.length) { try { trackEvent('certificate_viewed', { surface: 'investor', count: certs.length }); } catch (_) {} }
  }, [data]);

  const openPdf = (c) => {
    try { trackEvent('certificate_downloaded', { surface: 'investor', certificate_id: c.id, asset_id: c.asset_id }); } catch (_) {}
    window.open(`${api.baseURL}/investor/certificates/${c.id}/pdf`, '_blank');
  };

  const openHistory = async (c) => {
    setDrawer(c);
    try {
      const r = await api.get(`/investor/certificates/${c.id}/timeline`);
      setEvents(r.items || []);
    } catch { setEvents([]); }
  };

  const active = data?.active || [];
  const history = data?.history || [];

  return (
    <div className="px-[50px] py-8 pb-20" data-testid="investor-certificates">
      <div className="flex items-start justify-between gap-6 mb-6 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-token-kicker"><Award className="w-4 h-4" /> Certificates · A2</div>
          <h1 className="text-h1 mb-1 mt-1">Мої сертифікати</h1>
          <p className="text-small-token max-w-2xl">
            Інвестиційні сертифікати підтверджують ваше володіння одиницями активу.
            Кожен сертифікат можна завантажити (PDF) та публічно перевірити за QR-кодом.
          </p>
        </div>
        <button onClick={load} disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-app text-sm font-semibold text-token-secondary hover:text-token-primary hover:border-app-strong transition disabled:opacity-50"
          data-testid="certs-refresh">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Оновити
        </button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => <div key={i} className="h-64 rounded-2xl bg-app-elevated animate-pulse" />)}
        </div>
      ) : active.length === 0 && history.length === 0 ? (
        <div className="rounded-2xl border border-app bg-app-surface p-10 text-center">
          <Award className="w-10 h-10 mx-auto text-token-muted mb-3" />
          <p className="text-token-secondary font-medium">У вас поки немає сертифікатів</p>
          <p className="text-sm text-token-muted mt-1">Сертифікат випускається автоматично після підтвердження володіння.</p>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
            <h2 className="text-lg font-semibold text-token-primary">Активні ({active.length})</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="certs-active">
            {active.map((c) => <CertCard key={c.id} c={c} onPdf={openPdf} onHistory={openHistory} />)}
          </div>

          {history.length > 0 && (
            <>
              <div className="flex items-center gap-2 mt-8 mb-4">
                <Clock className="w-4 h-4 text-token-muted" />
                <h2 className="text-lg font-semibold text-token-primary">Історія ({history.length})</h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 opacity-80" data-testid="certs-history">
                {history.map((c) => <CertCard key={c.id} c={c} onPdf={openPdf} onHistory={openHistory} />)}
              </div>
            </>
          )}
        </>
      )}

      {/* History drawer */}
      {drawer && (
        <div className="fixed inset-0 z-50 flex justify-end" data-testid="cert-history-drawer">
          <div className="absolute inset-0 bg-black/40" onClick={() => setDrawer(null)} />
          <div className="relative w-full max-w-md bg-app-surface h-full overflow-y-auto shadow-xl">
            <div className="px-5 py-4 border-b border-app flex items-center gap-3 sticky top-0 bg-app-surface">
              <button onClick={() => setDrawer(null)} className="text-token-muted hover:text-token-primary"><ArrowLeft className="w-5 h-5" /></button>
              <div className="min-w-0">
                <div className="text-token-kicker">Історія сертифіката</div>
                <h3 className="font-semibold text-token-primary truncate">{drawer.certificate_number}</h3>
              </div>
            </div>
            {events.length === 0 ? (
              <div className="p-10 text-center text-sm text-token-muted">Подій ще немає.</div>
            ) : (
              <ul className="divide-y divide-app/60">
                {events.map((e, i) => (
                  <li key={i} className="px-5 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium text-token-primary">{e.event_label || EVENT_LABEL[e.event] || e.event}</span>
                      <span className="text-[11px] text-token-muted">{formatDateUk(e.at)}</span>
                    </div>
                    {e.summary && <div className="text-[12px] text-token-muted mt-0.5">{e.summary}</div>}
                    {e.amount_uah ? <div className="mt-1 text-[12px] font-semibold text-[#2E5D4F]">{formatUAH(e.amount_uah)}</div> : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
