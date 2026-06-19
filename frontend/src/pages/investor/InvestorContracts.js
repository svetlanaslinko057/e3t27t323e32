import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { lumen, formatUAH, formatDateUk, API, lumenError } from '@/lib/lumenApi';
import {
  FileSignature, FileText, Download, Loader2, CheckCircle2,
  AlertCircle, ShieldCheck, Clock,
} from 'lucide-react';
import { trackEvent } from '@/lib/activityTracker';

const STATUS_BADGE = {
  draft:     { label: 'Чернетка',        cls: 'bg-muted text-muted-foreground' },
  generated: { label: 'Згенеровано',     cls: 'bg-muted text-muted-foreground' },
  sent:      { label: 'Очікує підпису',  cls: 'bg-amber-100 text-amber-800' },
  viewed:    { label: 'Переглянуто',     cls: 'bg-sky-100 text-sky-800' },
  signed:    { label: 'Підписано',       cls: 'bg-emerald-100 text-emerald-800' },
  expired:   { label: 'Прострочено',     cls: 'bg-red-100 text-red-700' },
  cancelled: { label: 'Скасовано',       cls: 'bg-red-100 text-red-700' },
};

const SIGNABLE = ['generated', 'sent', 'viewed'];

export default function InvestorContracts() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [agree, setAgree] = useState(false);
  const [signing, setSigning] = useState(false);
  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');
  const [searchParams] = useSearchParams();

  const loadList = useCallback(async () => {
    try {
      const r = await lumen.get('/investor/contracts');
      const list = r.data?.items || [];
      setItems(list);
      return list;
    } catch (_e) {
      setItems([]);
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  const openDetail = useCallback(async (id) => {
    setDetailLoading(true);
    setError('');
    setAgree(false);
    try {
      const r = await lumen.get(`/investor/contracts/${id}`);
      setSelected(r.data);
      try { trackEvent('contract_opened', { contract_id: id, surface: 'investor' }); } catch (_) {}
      // detail marks `viewed` on the backend — sync the list badge
      setItems((prev) => prev.map((c) =>
        c.id === id && ['generated', 'sent'].includes(c.status)
          ? { ...c, status: 'viewed' } : c));
    } catch (e) {
      setError(lumenError(e, 'Не вдалось відкрити договір'));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    loadList().then((list) => {
      const target = searchParams.get('id');
      const first = target && list.find((c) => c.id === target)
        ? target
        : (list.find((c) => SIGNABLE.includes(c.status)) || list[0])?.id;
      if (first) openDetail(first);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sign = async () => {
    if (!selected || !agree) return;
    setSigning(true);
    setError('');
    try {
      const r = await lumen.post(`/investor/contracts/${selected.id}/sign`, { agree: true });
      const data = r.data || {};
      try { trackEvent('contract_signed', { contract_id: selected.id, surface: 'investor' }); } catch (_) {}
      setFlash(data.investment_status === 'active'
        ? 'Договір підписано — інвестицію активовано'
        : 'Договір підписано. Інвестиція активується після підтвердження верифікації (KYC).');
      setTimeout(() => setFlash(''), 6000);
      await loadList();
      await openDetail(selected.id);
    } catch (e) {
      setError(lumenError(e, 'Не вдалось підписати договір'));
    } finally {
      setSigning(false);
    }
  };

  const pendingCount = items.filter((c) => SIGNABLE.includes(c.status)).length;

  return (
    <div className="p-6 md:p-10 max-w-7xl mx-auto" data-testid="investor-contracts">
      <header className="mb-8">
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Юридичний контур</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Мої договори</h1>
        <p className="mt-1 text-muted-foreground">
          Кожна інвестиція активується після підписання договору. Електронне прийняття умов має юридичну силу — фіксуються дата, час, IP та пристрій.
        </p>
      </header>

      {flash && (
        <div className="mb-4 p-3 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-800 text-sm flex items-center gap-2" data-testid="contracts-flash">
          <CheckCircle2 className="w-4 h-4" /> {flash}
        </div>
      )}
      {error && (
        <div className="mb-4 p-3 rounded-xl border border-red-200 bg-red-50 text-red-700 text-sm flex items-center gap-2" data-testid="contracts-error">
          <AlertCircle className="w-4 h-4" /> {String(error)}
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => <div key={i} className="h-16 rounded-xl bg-muted/40 animate-pulse" />)}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-border bg-card p-10 text-center" data-testid="contracts-empty">
          <FileSignature className="w-7 h-7 mx-auto mb-3 text-muted-foreground opacity-50" />
          <p className="font-semibold">Договорів ще немає</p>
          <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">
            Договір генерується автоматично після підтвердження вашої заявки на інвестицію.
          </p>
        </div>
      ) : (
        <div className="grid lg:grid-cols-5 gap-6">
          {/* list */}
          <div className="lg:col-span-2">
            {pendingCount > 0 && (
              <p className="text-xs text-amber-700 mb-2 flex items-center gap-1.5" data-testid="contracts-pending-hint">
                <Clock className="w-3.5 h-3.5" /> Очікує вашого підпису: {pendingCount}
              </p>
            )}
            <ul className="rounded-2xl border border-border bg-card divide-y divide-border overflow-hidden" data-testid="contracts-list">
              {items.map((c) => {
                const b = STATUS_BADGE[c.status] || STATUS_BADGE.generated;
                return (
                  <li key={c.id}>
                    <button
                      onClick={() => openDetail(c.id)}
                      className={`w-full text-left px-4 py-3.5 hover:bg-muted/50 transition ${selected?.id === c.id ? 'bg-muted/60' : ''}`}
                      data-testid={`contract-item-${c.id}`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="font-medium text-sm truncate">{c.number}</p>
                        <span className={`text-[11px] px-2 py-0.5 rounded-full whitespace-nowrap font-medium ${b.cls}`}>{b.label}</span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5 truncate">
                        {c.asset_title} · {formatUAH(c.amount)}
                      </p>
                      <p className="text-[11px] text-muted-foreground mt-0.5">{c.template_kind_label} · {formatDateUk(c.generated_at)}</p>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          {/* detail */}
          <div className="lg:col-span-3">
            {detailLoading ? (
              <div className="rounded-2xl border border-border bg-card p-10 flex justify-center">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : !selected ? (
              <div className="rounded-2xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
                <FileText className="w-6 h-6 mx-auto mb-2 opacity-40" />
                Оберіть договір зі списку
              </div>
            ) : (
              <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="contract-detail">
                <div className="px-6 py-5 border-b border-border flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="font-bold text-lg">{selected.title || selected.number}</h2>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {selected.asset_title} · {formatUAH(selected.amount)} · {formatDateUk(selected.generated_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {(() => {
                      const b = STATUS_BADGE[selected.status] || STATUS_BADGE.generated;
                      return <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${b.cls}`} data-testid="contract-detail-status">{b.label}</span>;
                    })()}
                    <a
                      href={`${API}/contracts/${selected.id}/pdf`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 px-3.5 h-9 rounded-full border border-border hover:border-[#2E5D4F] hover:text-[#2E5D4F] text-sm transition"
                      data-testid="contract-pdf-link"
                    >
                      <Download className="w-3.5 h-3.5" /> PDF
                    </a>
                  </div>
                </div>

                {/* body */}
                <div className="px-6 py-5 max-h-[420px] overflow-y-auto text-sm leading-relaxed" data-testid="contract-body">
                  <ContractBody text={selected.body_text} />
                </div>

                {/* signature footer */}
                <div className="px-6 py-5 border-t border-border bg-muted/30">
                  {selected.status === 'signed' ? (
                    <div className="flex items-start gap-3" data-testid="contract-signed-block">
                      <ShieldCheck className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                      <div className="text-sm">
                        <p className="font-semibold text-emerald-800">Підписано електронно (Electronic Acceptance)</p>
                        <p className="text-muted-foreground mt-0.5">
                          {formatDateUk(selected.signed_at)} · IP: {selected.signature?.ip || '—'}
                        </p>
                        {selected.investment_status === 'active' && (
                          <p className="text-emerald-700 mt-1">Інвестицію активовано — частку зараховано у ваш портфель.</p>
                        )}
                        {selected.investment_status === 'kyc_pending' && (
                          <p className="text-amber-700 mt-1">Інвестиція активується після підтвердження верифікації (KYC).</p>
                        )}
                      </div>
                    </div>
                  ) : selected.status === 'cancelled' ? (
                    <p className="text-sm text-red-700" data-testid="contract-cancelled-block">
                      Договір скасовано{selected.cancel_reason ? `: ${selected.cancel_reason}` : ''}.
                    </p>
                  ) : SIGNABLE.includes(selected.status) ? (
                    <div data-testid="contract-sign-block">
                      <label className="flex items-start gap-3 cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={agree}
                          onChange={(e) => setAgree(e.target.checked)}
                          className="mt-1 w-4 h-4 accent-[#2E5D4F]"
                          data-testid="contract-agree-checkbox"
                        />
                        <span className="text-sm">
                          Я ознайомився(-лась) з умовами договору, розумію ризики інвестування та погоджуюсь з усіма положеннями. Підтверджую електронне підписання.
                        </span>
                      </label>
                      <button
                        onClick={sign}
                        disabled={!agree || signing}
                        className="mt-4 inline-flex items-center gap-2 px-6 h-11 rounded-full bg-[#2E5D4F] text-white text-sm font-semibold hover:opacity-90 transition disabled:opacity-40"
                        data-testid="contract-sign-btn"
                      >
                        {signing ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileSignature className="w-4 h-4" />}
                        Підписати договір
                      </button>
                      <p className="text-[11px] text-muted-foreground mt-2">
                        Фіксуються дата, час, IP-адреса та параметри пристрою — відповідно до ЗУ «Про електронні довірчі послуги».
                      </p>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">Підписання недоступне для цього статусу.</p>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** Line-oriented contract markup: `# ` title, `## ` heading, else paragraph. */
const ContractBody = ({ text }) => (
  <div>
    {(text || '').split('\n').map((raw, i) => {
      const line = raw.trim();
      if (!line) return <div key={i} className="h-2" />;
      if (line.startsWith('# ')) {
        return <h2 key={i} className="text-base font-bold text-[#1A3C32] dark:text-emerald-200 mt-1 mb-2">{line.slice(2)}</h2>;
      }
      if (line.startsWith('## ')) {
        return <h3 key={i} className="text-sm font-semibold text-[#2E5D4F] dark:text-emerald-300 mt-4 mb-1">{line.slice(3)}</h3>;
      }
      return <p key={i} className="text-sm text-foreground/90 mb-1">{line}</p>;
    })}
  </div>
);
