/**
 * InvestorRails.js — Phase H1.1
 *
 * Institutional Banking Rails (SEPA + SWIFT) — investor side.
 *
 * UX scope:
 *   • Submit SEPA / SEPA-Instant / SWIFT transfer instructions.
 *   • Live IBAN + BIC validation (mod-97 / ISO 9362) BEFORE submit.
 *   • Transfer queue with status badges, currency, amount, reference.
 *   • Detail panel with full timeline (events[]) + bank beneficiary block.
 *   • Cancel pending transfers.
 *   • Clear warning to put the reference in the payment purpose field.
 */
import { useCallback, useEffect, useState } from 'react';
import { lumen, lumenError, formatDateUk } from '@/lib/lumenApi';
import {
  Landmark, Send, ArrowDownToLine, ArrowUpFromLine, Loader2, X,
  AlertTriangle, CheckCircle2, Banknote, RefreshCw, Copy, Clock,
  Building2, FileText, Globe2, Zap, ShieldCheck,
} from 'lucide-react';

const STATUS_META = {
  draft:     { label: 'Чернетка',         cls: 'bg-muted text-muted-foreground' },
  pending:   { label: 'Очікує',           cls: 'bg-amber-100 text-amber-900' },
  initiated: { label: 'Ініційовано',      cls: 'bg-sky-100 text-sky-900' },
  sent:      { label: 'Відправлено',      cls: 'bg-indigo-100 text-indigo-900' },
  confirmed: { label: 'Підтверджено',     cls: 'bg-emerald-100 text-emerald-900' },
  failed:    { label: 'Помилка',          cls: 'bg-red-100 text-red-800' },
  returned:  { label: 'Повернено',        cls: 'bg-rose-100 text-rose-800' },
  cancelled: { label: 'Скасовано',        cls: 'bg-zinc-200 text-zinc-700' },
};

const CANCELLABLE = ['draft', 'pending'];

const SWIFT_CURRENCIES = ['USD', 'EUR', 'GBP', 'CHF', 'JPY', 'CAD', 'AUD',
                           'NOK', 'SEK', 'DKK'];

function formatMoney(amount, currency) {
  const n = Number(amount);
  if (isNaN(n)) return '—';
  try {
    return n.toLocaleString('uk-UA', {
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    }) + ' ' + (currency || '');
  } catch (_e) { return `${n.toFixed(2)} ${currency || ''}`; }
}

function formatIban(iban) {
  if (!iban) return '—';
  return iban.replace(/(.{4})/g, '$1 ').trim();
}

export default function InvestorRails() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [flash, setFlash] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [rail, setRail] = useState('sepa');
  const [detail, setDetail] = useState(null);
  const [detailEvents, setDetailEvents] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await lumen.get('/lumen/institutional/rails/transfers?limit=100');
      setItems(r.data?.items || []);
      setErr('');
    } catch (e) {
      setErr(lumenError(e, 'Не вдалось завантажити перекази'));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (id) => {
    try {
      const r = await lumen.get(`/lumen/institutional/rails/transfers/${id}`);
      setDetail(r.data?.transfer || null);
      setDetailEvents(r.data?.events || []);
    } catch (e) {
      setErr(lumenError(e, 'Не вдалось відкрити переказ'));
    }
  };

  const cancelTransfer = async (id) => {
    if (!window.confirm('Скасувати цей переказ? Дія незворотна.')) return;
    try {
      await lumen.post(`/lumen/institutional/rails/transfers/${id}/cancel`);
      setFlash('Переказ скасовано.');
      setDetail(null);
      load();
    } catch (e) { setErr(lumenError(e, 'Не вдалось скасувати переказ')); }
  };

  const copyToClipboard = async (s) => {
    try {
      await navigator.clipboard.writeText(s);
      setFlash('Скопійовано до буфера обміну.');
      setTimeout(() => setFlash(''), 2000);
    } catch (_e) { /* ignore */ }
  };

  return (
    <div className="p-6 md:p-10 max-w-6xl mx-auto" data-testid="investor-rails">
      <header className="mb-8 flex items-start justify-between flex-wrap gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">
            Інституційні банківські рейки
          </p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight flex items-center gap-2">
            <Landmark className="w-7 h-7 text-signal" />
            SEPA / SWIFT перекази
          </h1>
          <p className="mt-2 text-muted-foreground max-w-2xl">
            Подайте інструкцію на банківський переказ через SEPA (EUR-зона) або
            SWIFT (міжнародні). LUMEN підтвердить отримання після зарахування на
            рахунок та сформує проводку в реєстрі.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="px-3 py-2 rounded-lg border border-border text-sm hover:bg-muted transition flex items-center gap-1.5"
            data-testid="rails-refresh-btn"
            title="Оновити"
          >
            <RefreshCw className="w-4 h-4" /> Оновити
          </button>
          <button
            onClick={() => { setShowForm(true); setRail('sepa'); }}
            className="px-4 py-2 rounded-lg bg-signal text-signal-foreground text-sm font-medium hover:opacity-90 transition flex items-center gap-1.5"
            data-testid="rails-new-btn"
          >
            <Send className="w-4 h-4" /> Новий переказ
          </button>
        </div>
      </header>

      {/* Inline alerts */}
      {flash && (
        <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-900 px-4 py-3 text-sm flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" /> {flash}
        </div>
      )}
      {err && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm flex items-start gap-2" data-testid="rails-error">
          <AlertTriangle className="w-4 h-4 mt-0.5" />
          <div>{err}</div>
        </div>
      )}

      {/* Reference warning — institutional context */}
      <div className="mb-6 rounded-2xl border border-amber-200 bg-amber-50 text-amber-900 px-5 py-4 flex items-start gap-3" data-testid="rails-reference-warning">
        <AlertTriangle className="w-5 h-5 mt-0.5 flex-shrink-0" />
        <div className="text-sm">
          <p className="font-medium mb-1">Важливо: вкажіть reference у призначенні платежу</p>
          <p className="leading-relaxed">
            LUMEN ідентифікує транзакцію за полем <span className="font-mono font-medium">reference</span>.
            Якщо банк не передасть цей рядок у виписці, ми не зможемо зіставити
            ваш переказ з вашим LP-зобовʼязанням і кошти можуть бути повернені.
            Скопіюйте reference точно як показано.
          </p>
        </div>
      </div>

      {/* Transfer list */}
      <section className="rounded-2xl border border-border bg-card shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-border flex items-center justify-between">
          <h2 className="text-sm font-semibold tracking-wide uppercase text-muted-foreground">
            Мої перекази ({items.length})
          </h2>
        </div>
        {loading ? (
          <div className="p-10 flex items-center justify-center text-muted-foreground gap-2">
            <Loader2 className="w-5 h-5 animate-spin" /> Завантаження…
          </div>
        ) : items.length === 0 ? (
          <div className="p-10 text-center">
            <Banknote className="w-12 h-12 text-muted-foreground mx-auto mb-3" />
            <p className="text-muted-foreground">У вас ще немає переказів.</p>
            <button
              onClick={() => { setShowForm(true); setRail('sepa'); }}
              className="mt-4 px-4 py-2 rounded-lg bg-signal text-signal-foreground text-sm font-medium hover:opacity-90 transition"
              data-testid="rails-empty-cta"
            >
              Створити перший переказ
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="rails-table">
              <thead className="bg-muted/40">
                <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-5 py-3">Reference</th>
                  <th className="px-5 py-3">Rail</th>
                  <th className="px-5 py-3">Напрям</th>
                  <th className="px-5 py-3 text-right">Сума</th>
                  <th className="px-5 py-3">Бенефіціар</th>
                  <th className="px-5 py-3">Статус</th>
                  <th className="px-5 py-3">Створено</th>
                  <th className="px-5 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {items.map(t => {
                  const meta = STATUS_META[t.status] || { label: t.status, cls: 'bg-muted' };
                  return (
                    <tr key={t.id} className="border-t border-border hover:bg-muted/30 transition" data-testid={`rails-row-${t.id}`}>
                      <td className="px-5 py-3 font-mono text-xs">{t.reference}</td>
                      <td className="px-5 py-3">
                        <span className="inline-flex items-center gap-1 text-xs font-medium">
                          {t.rail === 'sepa_instant' && <Zap className="w-3 h-3 text-amber-500" />}
                          {t.rail.replace('_', ' ').toUpperCase()}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-xs">
                        {t.direction === 'inbound' ? (
                          <span className="inline-flex items-center gap-1 text-emerald-700"><ArrowDownToLine className="w-3.5 h-3.5" /> Вхідний</span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-sky-700"><ArrowUpFromLine className="w-3.5 h-3.5" /> Вихідний</span>
                        )}
                      </td>
                      <td className="px-5 py-3 text-right font-medium">{formatMoney(t.amount, t.currency)}</td>
                      <td className="px-5 py-3 text-xs">{t.beneficiary_name}</td>
                      <td className="px-5 py-3">
                        <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${meta.cls}`}>{meta.label}</span>
                      </td>
                      <td className="px-5 py-3 text-xs text-muted-foreground">{formatDateUk(t.created_at)}</td>
                      <td className="px-5 py-3 text-right">
                        <button
                          onClick={() => openDetail(t.id)}
                          className="text-signal hover:underline text-xs font-medium"
                          data-testid={`rails-open-${t.id}`}
                        >
                          Деталі →
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Submit form modal */}
      {showForm && (
        <RailsSubmitModal
          rail={rail}
          onClose={() => setShowForm(false)}
          onChangeRail={setRail}
          onSubmitted={(msg) => {
            setFlash(msg || 'Переказ створено.');
            setShowForm(false);
            load();
          }}
          onError={(m) => setErr(m)}
        />
      )}

      {/* Detail drawer */}
      {detail && (
        <DetailDrawer
          transfer={detail}
          events={detailEvents}
          onClose={() => setDetail(null)}
          onCopy={copyToClipboard}
          onCancel={CANCELLABLE.includes(detail.status) ? () => cancelTransfer(detail.id) : null}
        />
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/* Submit modal                                                            */
/* ────────────────────────────────────────────────────────────────────── */
function RailsSubmitModal({ rail, onChangeRail, onClose, onSubmitted, onError }) {
  const [form, setForm] = useState({
    direction: 'inbound',
    amount: '',
    currency: 'EUR',
    beneficiary_name: '',
    beneficiary_iban: '',
    beneficiary_bic: '',
    intermediary_bic: '',
    charges: 'SHA',
    instant: false,
    purpose: '',
    fund_id: '',
    reference: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [ibanCheck, setIbanCheck] = useState({ checking: false, ok: null, info: null });
  const [bicCheck, setBicCheck] = useState({ checking: false, ok: null, info: null });
  const [errMsg, setErrMsg] = useState('');

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const checkIban = useCallback(async (iban) => {
    if (!iban || iban.length < 10) { setIbanCheck({ checking: false, ok: null, info: null }); return; }
    setIbanCheck({ checking: true, ok: null, info: null });
    try {
      const r = await lumen.get(`/lumen/institutional/rails/iban/validate?iban=${encodeURIComponent(iban)}`);
      setIbanCheck({ checking: false, ok: !!r.data?.ok, info: r.data });
    } catch (_e) {
      setIbanCheck({ checking: false, ok: false, info: { error: 'Перевірка не вдалась' } });
    }
  }, []);

  const checkBic = useCallback(async (bic) => {
    if (!bic || bic.length < 6) { setBicCheck({ checking: false, ok: null, info: null }); return; }
    setBicCheck({ checking: true, ok: null, info: null });
    try {
      const r = await lumen.get(`/lumen/institutional/rails/bic/validate?bic=${encodeURIComponent(bic)}`);
      setBicCheck({ checking: false, ok: !!r.data?.ok, info: r.data });
    } catch (_e) {
      setBicCheck({ checking: false, ok: false, info: { error: 'Перевірка не вдалась' } });
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => checkIban(form.beneficiary_iban), 350);
    return () => clearTimeout(t);
  }, [form.beneficiary_iban, checkIban]);

  useEffect(() => {
    if (rail !== 'swift') return;
    const t = setTimeout(() => checkBic(form.beneficiary_bic), 350);
    return () => clearTimeout(t);
  }, [form.beneficiary_bic, rail, checkBic]);

  // SEPA → currency locked to EUR, hide BIC fields
  useEffect(() => {
    if (rail === 'sepa') set('currency', 'EUR');
  }, [rail]);

  const submit = async (e) => {
    e?.preventDefault?.();
    setErrMsg('');
    if (ibanCheck.ok === false) {
      setErrMsg('IBAN не пройшов перевірку — виправте перед відправкою.');
      return;
    }
    if (rail === 'swift' && bicCheck.ok === false) {
      setErrMsg('BIC не пройшов перевірку — виправте перед відправкою.');
      return;
    }
    setSubmitting(true);
    try {
      const base = {
        direction: form.direction,
        amount: Number(form.amount),
        currency: form.currency.toUpperCase(),
        beneficiary_name: form.beneficiary_name.trim(),
        beneficiary_iban: form.beneficiary_iban.replace(/\s+/g, '').toUpperCase(),
        purpose: form.purpose || null,
        fund_id: form.fund_id || null,
        reference: form.reference || null,
      };
      let url, payload;
      if (rail === 'swift') {
        url = '/lumen/institutional/rails/swift/transfers';
        payload = {
          ...base,
          beneficiary_bic: form.beneficiary_bic.replace(/\s+/g, '').toUpperCase(),
          intermediary_bic: form.intermediary_bic ? form.intermediary_bic.replace(/\s+/g, '').toUpperCase() : null,
          charges: form.charges,
        };
      } else {
        url = '/lumen/institutional/rails/sepa/transfers';
        payload = { ...base, instant: !!form.instant };
      }
      const r = await lumen.post(url, payload);
      onSubmitted(`Переказ створено: ${r.data?.reference}`);
    } catch (e) {
      const m = lumenError(e, 'Не вдалось створити переказ');
      setErrMsg(m);
      onError?.(m);
    } finally { setSubmitting(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto" data-testid="rails-submit-modal">
      <form onSubmit={submit} className="bg-card text-foreground rounded-2xl border border-border shadow-2xl w-full max-w-2xl my-8">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Send className="w-5 h-5 text-signal" /> Новий переказ
          </h2>
          <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground" data-testid="rails-modal-close">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-5">
          {/* Rail picker */}
          <div className="grid grid-cols-3 gap-2" data-testid="rails-picker">
            <RailButton active={rail === 'sepa'} onClick={() => onChangeRail('sepa')}
              icon={<Globe2 className="w-4 h-4" />} title="SEPA"
              subtitle="EUR · 1 день · €" />
            <RailButton active={rail === 'sepa_instant'} onClick={() => { onChangeRail('sepa'); set('instant', true); }}
              icon={<Zap className="w-4 h-4" />} title="SEPA Instant"
              subtitle="EUR · до 10 сек" />
            <RailButton active={rail === 'swift'} onClick={() => onChangeRail('swift')}
              icon={<Building2 className="w-4 h-4" />} title="SWIFT"
              subtitle="USD/EUR/GBP · T+2" />
          </div>

          {errMsg && (
            <div className="rounded-lg border border-red-200 bg-red-50 text-red-800 px-3 py-2 text-sm flex items-start gap-2" data-testid="rails-form-error">
              <AlertTriangle className="w-4 h-4 mt-0.5" /> {errMsg}
            </div>
          )}

          {/* Direction */}
          <div>
            <label className="block text-xs uppercase tracking-wider text-muted-foreground mb-2">Напрям</label>
            <div className="flex gap-2">
              <DirChip active={form.direction === 'inbound'} onClick={() => set('direction', 'inbound')}
                icon={<ArrowDownToLine className="w-4 h-4" />} label="Вхідний (LP commitment)" />
              <DirChip active={form.direction === 'outbound'} onClick={() => set('direction', 'outbound')}
                icon={<ArrowUpFromLine className="w-4 h-4" />} label="Вихідний (виплата)" />
            </div>
          </div>

          {/* Amount + currency */}
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <label className="block text-xs uppercase tracking-wider text-muted-foreground mb-1">Сума</label>
              <input type="number" step="0.01" min="0" value={form.amount}
                onChange={e => set('amount', e.target.value)} required
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-foreground focus:ring-2 focus:ring-signal focus:outline-none"
                placeholder={rail === 'swift' ? 'мін. 10 000' : 'мін. 1 000'}
                data-testid="rails-amount-input" />
            </div>
            <div>
              <label className="block text-xs uppercase tracking-wider text-muted-foreground mb-1">Валюта</label>
              {rail === 'swift' ? (
                <select value={form.currency} onChange={e => set('currency', e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-foreground focus:ring-2 focus:ring-signal focus:outline-none"
                  data-testid="rails-currency-select">
                  {SWIFT_CURRENCIES.map(c => <option key={c}>{c}</option>)}
                </select>
              ) : (
                <div className="w-full px-3 py-2 rounded-lg border border-border bg-muted text-muted-foreground font-mono text-sm">
                  EUR
                </div>
              )}
            </div>
          </div>

          {/* Beneficiary name */}
          <div>
            <label className="block text-xs uppercase tracking-wider text-muted-foreground mb-1">Бенефіціар (отримувач)</label>
            <input value={form.beneficiary_name}
              onChange={e => set('beneficiary_name', e.target.value)} required minLength={2}
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-foreground focus:ring-2 focus:ring-signal focus:outline-none"
              placeholder="Назва компанії або повне імʼя"
              data-testid="rails-beneficiary-input" />
          </div>

          {/* IBAN */}
          <div>
            <label className="block text-xs uppercase tracking-wider text-muted-foreground mb-1">IBAN бенефіціара</label>
            <input value={form.beneficiary_iban}
              onChange={e => set('beneficiary_iban', e.target.value.toUpperCase())}
              required minLength={15}
              className={`w-full px-3 py-2 rounded-lg border bg-background text-foreground font-mono focus:ring-2 focus:outline-none ${
                ibanCheck.ok === false ? 'border-red-300 focus:ring-red-300' :
                ibanCheck.ok === true ? 'border-emerald-300 focus:ring-emerald-300' :
                'border-border focus:ring-signal'
              }`}
              placeholder="DE89 3704 0044 0532 0130 00"
              data-testid="rails-iban-input" />
            <IbanFeedback rail={rail} check={ibanCheck} />
          </div>

          {/* SWIFT-only fields */}
          {rail === 'swift' && (
            <>
              <div>
                <label className="block text-xs uppercase tracking-wider text-muted-foreground mb-1">BIC бенефіціара</label>
                <input value={form.beneficiary_bic}
                  onChange={e => set('beneficiary_bic', e.target.value.toUpperCase())}
                  required minLength={8} maxLength={11}
                  className={`w-full px-3 py-2 rounded-lg border bg-background text-foreground font-mono focus:ring-2 focus:outline-none ${
                    bicCheck.ok === false ? 'border-red-300 focus:ring-red-300' :
                    bicCheck.ok === true ? 'border-emerald-300 focus:ring-emerald-300' :
                    'border-border focus:ring-signal'
                  }`}
                  placeholder="DEUTDEFFXXX"
                  data-testid="rails-bic-input" />
                <BicFeedback check={bicCheck} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs uppercase tracking-wider text-muted-foreground mb-1">BIC посередника (опціонально)</label>
                  <input value={form.intermediary_bic}
                    onChange={e => set('intermediary_bic', e.target.value.toUpperCase())}
                    className="w-full px-3 py-2 rounded-lg border border-border bg-background text-foreground font-mono focus:ring-2 focus:ring-signal focus:outline-none"
                    placeholder="опційно"
                    data-testid="rails-intermediary-bic-input" />
                </div>
                <div>
                  <label className="block text-xs uppercase tracking-wider text-muted-foreground mb-1">Charges</label>
                  <select value={form.charges} onChange={e => set('charges', e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-border bg-background text-foreground focus:ring-2 focus:ring-signal focus:outline-none"
                    data-testid="rails-charges-select">
                    <option value="SHA">SHA · спільно</option>
                    <option value="OUR">OUR · відправник</option>
                    <option value="BEN">BEN · бенефіціар</option>
                  </select>
                </div>
              </div>
            </>
          )}

          {/* SEPA instant toggle */}
          {rail === 'sepa' && (
            <label className="flex items-center gap-2 text-sm cursor-pointer" data-testid="rails-instant-toggle">
              <input type="checkbox" checked={!!form.instant}
                onChange={e => set('instant', e.target.checked)}
                className="w-4 h-4 rounded border-border" />
              <Zap className="w-4 h-4 text-amber-500" />
              <span>SEPA Instant (до 10 секунд, доступно у більшості банків ЄС)</span>
            </label>
          )}

          {/* Reference + purpose */}
          <div>
            <label className="block text-xs uppercase tracking-wider text-muted-foreground mb-1">Reference (опційно, інакше згенеруємо)</label>
            <input value={form.reference}
              onChange={e => set('reference', e.target.value)} maxLength={140}
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-foreground font-mono focus:ring-2 focus:ring-signal focus:outline-none"
              placeholder="LP-COMMIT-2026-001"
              data-testid="rails-reference-input" />
            <p className="text-xs text-muted-foreground mt-1">
              Унікальний код переказу. <strong>Обовʼязково вказати у призначенні платежу банку.</strong>
            </p>
          </div>
          <div>
            <label className="block text-xs uppercase tracking-wider text-muted-foreground mb-1">Призначення (опціонально)</label>
            <textarea value={form.purpose}
              onChange={e => set('purpose', e.target.value)} rows={2} maxLength={240}
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-foreground focus:ring-2 focus:ring-signal focus:outline-none"
              placeholder="LP commitment Lumen Flagship Fund II"
              data-testid="rails-purpose-input" />
          </div>
        </div>

        <div className="px-6 py-4 bg-muted/30 border-t border-border flex items-center justify-end gap-2 rounded-b-2xl">
          <button type="button" onClick={onClose} disabled={submitting}
            className="px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted">
            Скасувати
          </button>
          <button type="submit" disabled={submitting || ibanCheck.checking || ibanCheck.ok === false}
            className="px-5 py-2 rounded-lg bg-signal text-signal-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center gap-2"
            data-testid="rails-submit-btn">
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            Створити переказ
          </button>
        </div>
      </form>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/* Sub-components                                                          */
/* ────────────────────────────────────────────────────────────────────── */
function RailButton({ active, onClick, icon, title, subtitle }) {
  return (
    <button type="button" onClick={onClick}
      className={`text-left rounded-xl border p-3 transition ${
        active ? 'border-signal bg-signal/5 text-foreground'
               : 'border-border hover:border-foreground/30 text-muted-foreground'}`}>
      <div className="flex items-center gap-1.5 text-sm font-medium">{icon} {title}</div>
      <div className="text-[11px] mt-1">{subtitle}</div>
    </button>
  );
}

function DirChip({ active, onClick, icon, label }) {
  return (
    <button type="button" onClick={onClick}
      className={`flex-1 rounded-lg border px-3 py-2 text-sm flex items-center gap-2 transition ${
        active ? 'border-signal bg-signal/10 text-foreground'
               : 'border-border hover:border-foreground/30 text-muted-foreground'}`}>
      {icon} {label}
    </button>
  );
}

function IbanFeedback({ rail, check }) {
  if (check.checking) {
    return <p className="text-xs mt-1 text-muted-foreground flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" /> Перевіряю IBAN…</p>;
  }
  if (check.ok === false) {
    return <p className="text-xs mt-1 text-red-700 flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> {check.info?.error || 'IBAN некоректний'}</p>;
  }
  if (check.ok === true) {
    if (rail === 'sepa' && !check.info?.sepa_eligible) {
      return <p className="text-xs mt-1 text-amber-800 flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> Країна <strong>{check.info?.country}</strong> поза SEPA-зоною — оберіть SWIFT.</p>;
    }
    return <p className="text-xs mt-1 text-emerald-700 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> IBAN валідний · країна {check.info?.country}{check.info?.sepa_eligible ? ' · SEPA' : ''}</p>;
  }
  return <p className="text-xs mt-1 text-muted-foreground">Перевірка контрольної суми (mod-97) автоматично.</p>;
}

function BicFeedback({ check }) {
  if (check.checking) return <p className="text-xs mt-1 text-muted-foreground"><Loader2 className="w-3 h-3 animate-spin inline" /> Перевіряю BIC…</p>;
  if (check.ok === false) return <p className="text-xs mt-1 text-red-700 flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> {check.info?.error || 'BIC некоректний'}</p>;
  if (check.ok === true) return <p className="text-xs mt-1 text-emerald-700 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> BIC валідний (ISO 9362)</p>;
  return null;
}

/* ────────────────────────────────────────────────────────────────────── */
/* Detail drawer                                                           */
/* ────────────────────────────────────────────────────────────────────── */
function DetailDrawer({ transfer, events, onClose, onCopy, onCancel }) {
  const t = transfer;
  const meta = STATUS_META[t.status] || { label: t.status, cls: 'bg-muted' };
  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex justify-end" data-testid="rails-detail-drawer">
      <div className="w-full max-w-2xl bg-card text-foreground h-full overflow-y-auto border-l border-border shadow-2xl">
        <div className="sticky top-0 bg-card/95 backdrop-blur z-10 px-6 py-4 border-b border-border flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground">{t.rail.toUpperCase().replace('_', ' ')} переказ</p>
            <h2 className="text-lg font-semibold mt-0.5">{t.reference}</h2>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground" data-testid="rails-detail-close">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          <div className="flex items-center gap-3">
            <span className={`px-3 py-1 rounded-md text-sm font-medium ${meta.cls}`}>{meta.label}</span>
            <span className="text-xl font-bold">{formatMoney(t.amount, t.currency)}</span>
            <span className="text-sm text-muted-foreground">· {t.direction === 'inbound' ? 'Вхідний' : 'Вихідний'}</span>
          </div>

          {/* Bank beneficiary */}
          <section className="rounded-xl border border-border bg-muted/20 p-4 space-y-2">
            <h3 className="text-xs uppercase tracking-wider text-muted-foreground font-medium">Реквізити бенефіціара</h3>
            <DetailRow label="Бенефіціар" value={t.beneficiary_name} />
            <DetailRow label="IBAN" value={formatIban(t.beneficiary_iban)} copyValue={t.beneficiary_iban} onCopy={onCopy} mono />
            {t.beneficiary_bic && <DetailRow label="BIC" value={t.beneficiary_bic} copyValue={t.beneficiary_bic} onCopy={onCopy} mono />}
            {t.intermediary_bic && <DetailRow label="Intermediary BIC" value={t.intermediary_bic} mono />}
            {t.charges && <DetailRow label="Charges" value={t.charges} />}
            <DetailRow label="Країна" value={t.beneficiary_country || '—'} />
          </section>

          {/* Reference block with warning */}
          <section className="rounded-xl border-2 border-amber-300 bg-amber-50/60 p-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-700 mt-0.5 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-semibold text-amber-900">Reference для призначення платежу</h3>
                <p className="text-xs text-amber-800 mt-1 mb-2">
                  Скопіюйте та вкажіть у банку у полі <em>&laquo;Призначення платежу&raquo;</em>.
                  Без цього LUMEN не зможе зіставити переказ.
                </p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 px-3 py-2 rounded-md bg-white border border-amber-200 text-amber-900 font-mono text-sm break-all" data-testid="rails-detail-reference">{t.reference}</code>
                  <button onClick={() => onCopy(t.reference)} className="px-3 py-2 rounded-md bg-amber-200 text-amber-900 text-xs font-medium hover:bg-amber-300 flex items-center gap-1.5" data-testid="rails-copy-reference">
                    <Copy className="w-3.5 h-3.5" /> Копіювати
                  </button>
                </div>
              </div>
            </div>
          </section>

          {/* Meta */}
          <section className="rounded-xl border border-border p-4 space-y-2">
            <h3 className="text-xs uppercase tracking-wider text-muted-foreground font-medium">Деталі переказу</h3>
            <DetailRow label="ID" value={t.id} mono />
            {t.fund_id && <DetailRow label="Fund" value={t.fund_id} />}
            {t.purpose && <DetailRow label="Призначення" value={t.purpose} />}
            <DetailRow label="Створено" value={formatDateUk(t.created_at)} />
            {t.settled_at && <DetailRow label="Зараховано" value={formatDateUk(t.settled_at)} />}
            {t.provider_ref && <DetailRow label="Bank ref" value={t.provider_ref} mono />}
            {t.failure_reason && <DetailRow label="Причина відхилення" value={t.failure_reason} accent="text-red-700" />}
          </section>

          {/* Reconciliation block (if present) */}
          {t.reconciliation && (
            <section className={`rounded-xl border p-4 ${t.reconciliation.matched ? 'border-emerald-200 bg-emerald-50/60' : 'border-rose-200 bg-rose-50/60'}`}>
              <h3 className="text-xs uppercase tracking-wider text-muted-foreground font-medium mb-2 flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4" /> Реконсиляція
              </h3>
              <div className="text-sm space-y-1">
                <DetailRow label="Зіставлено" value={t.reconciliation.matched ? '✓ так' : '✗ ні'} accent={t.reconciliation.matched ? 'text-emerald-700' : 'text-rose-700'} />
                <DetailRow label="Дельта" value={`${t.reconciliation.delta_amount >= 0 ? '+' : ''}${t.reconciliation.delta_amount} ${t.currency}`} />
                {t.reconciliation.currency_mismatch && <DetailRow label="Валюта" value="⚠ невідповідність" accent="text-rose-700" />}
                <DetailRow label="Bank statement" value={t.reconciliation.bank_statement_ref} mono />
              </div>
            </section>
          )}

          {/* Timeline */}
          <section>
            <h3 className="text-xs uppercase tracking-wider text-muted-foreground font-medium mb-3 flex items-center gap-1.5">
              <Clock className="w-4 h-4" /> Історія подій
            </h3>
            <ol className="space-y-3" data-testid="rails-detail-events">
              {events.map((ev, idx) => (
                <li key={ev.id || idx} className="flex gap-3">
                  <div className={`w-2 h-2 rounded-full mt-2 flex-shrink-0 ${STATUS_META[ev.status]?.cls?.includes('emerald') ? 'bg-emerald-500' : STATUS_META[ev.status]?.cls?.includes('red') || STATUS_META[ev.status]?.cls?.includes('rose') ? 'bg-red-500' : 'bg-signal'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium ${STATUS_META[ev.status]?.cls || 'bg-muted'}`}>{STATUS_META[ev.status]?.label || ev.status}</span>
                      <span className="text-xs text-muted-foreground">{formatDateUk(ev.at)}</span>
                    </div>
                    {ev.message && <p className="text-sm text-foreground mt-1">{ev.message}</p>}
                    {ev.meta && Object.keys(ev.meta).length > 0 && (
                      <pre className="text-[11px] text-muted-foreground mt-1 bg-muted/30 rounded px-2 py-1 overflow-x-auto">{JSON.stringify(ev.meta, null, 0)}</pre>
                    )}
                  </div>
                </li>
              ))}
              {events.length === 0 && <p className="text-sm text-muted-foreground">Подій ще немає.</p>}
            </ol>
          </section>

          {onCancel && (
            <div className="pt-2 border-t border-border">
              <button onClick={onCancel}
                className="w-full px-4 py-2.5 rounded-lg border border-red-200 bg-red-50 text-red-700 text-sm font-medium hover:bg-red-100 flex items-center justify-center gap-2"
                data-testid="rails-cancel-btn">
                <X className="w-4 h-4" /> Скасувати переказ
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DetailRow({ label, value, mono, accent, copyValue, onCopy }) {
  return (
    <div className="flex items-start gap-3 text-sm">
      <span className="w-32 text-xs uppercase tracking-wider text-muted-foreground flex-shrink-0">{label}</span>
      <span className={`flex-1 min-w-0 break-words ${mono ? 'font-mono text-sm' : ''} ${accent || ''}`}>{value}</span>
      {copyValue && onCopy && (
        <button type="button" onClick={() => onCopy(copyValue)} className="text-muted-foreground hover:text-foreground" title="Копіювати">
          <Copy className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}
