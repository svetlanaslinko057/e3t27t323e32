/**
 * AdminCommChannels — F5 Communication Provider Layer console.
 * Tabs: Providers (registry) · Feed (unified cross-provider log) · Send (compose).
 * Structural abstraction — manual is active; Ringostat/Gmail/Twilio/etc are
 * dormant until F6–F8 (their adapters plug in without touching this UI).
 */
import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError, formatDateUk } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import { useAuth } from '@/App';
import {
  Radio, Loader2, RefreshCw, Phone, Mail, MessageSquare, Hand, Send,
  ArrowDownLeft, ArrowUpRight, CheckCircle2, Clock, XCircle, Plug, Power,
  Zap, Inbox, ListFilter,
} from 'lucide-react';

const PRIVILEGED = new Set(['admin', 'owner', 'master_admin', 'team_lead']);

const TYPE_ICON = { voice: Phone, email: Mail, messaging: MessageSquare, manual: Hand };

const STATUS = {
  active: { cls: 'bg-emerald-500/10 text-emerald-700 border-emerald-200', dot: 'bg-emerald-500', uk: 'Активний', en: 'Active' },
  not_connected: { cls: 'bg-slate-500/10 text-slate-600 border-slate-200', dot: 'bg-slate-400', uk: 'Не під’єднано', en: 'Not connected' },
  disabled: { cls: 'bg-rose-500/10 text-rose-700 border-rose-200', dot: 'bg-rose-500', uk: 'Вимкнено', en: 'Disabled' },
};

const SYNC = {
  logged: { cls: 'bg-slate-100 text-slate-600', icon: CheckCircle2, uk: 'Записано', en: 'Logged' },
  queued: { cls: 'bg-amber-100 text-amber-700', icon: Clock, uk: 'У черзі', en: 'Queued' },
  sent: { cls: 'bg-sky-100 text-sky-700', icon: ArrowUpRight, uk: 'Надіслано', en: 'Sent' },
  delivered: { cls: 'bg-emerald-100 text-emerald-700', icon: CheckCircle2, uk: 'Доставлено', en: 'Delivered' },
  received: { cls: 'bg-emerald-100 text-emerald-700', icon: Inbox, uk: 'Отримано', en: 'Received' },
  failed: { cls: 'bg-rose-100 text-rose-700', icon: XCircle, uk: 'Помилка', en: 'Failed' },
  not_connected: { cls: 'bg-slate-100 text-slate-500', icon: Plug, uk: 'Не під’єднано', en: 'Not connected' },
};

const ITYPE_LABEL = {
  call: { uk: 'Дзвінок', en: 'Call' }, email: { uk: 'Email', en: 'Email' },
  telegram: { uk: 'Telegram', en: 'Telegram' }, whatsapp: { uk: 'WhatsApp', en: 'WhatsApp' },
  sms: { uk: 'SMS', en: 'SMS' }, meeting: { uk: 'Зустріч', en: 'Meeting' },
  document: { uk: 'Документ', en: 'Document' }, note: { uk: 'Нотатка', en: 'Note' },
  in_app: { uk: 'У застосунку', en: 'In-app' }, other: { uk: 'Інше', en: 'Other' },
};

export default function AdminCommChannels() {
  const { bi, lang } = useLang();
  const { user } = useAuth();
  const privileged = PRIVILEGED.has((user?.role || '').toLowerCase());
  const [tab, setTab] = useState('providers');

  const TABS = [
    { id: 'providers', icon: Plug, label: bi('Провайдери', 'Providers') },
    { id: 'feed', icon: ListFilter, label: bi('Стрічка', 'Feed') },
    { id: 'send', icon: Send, label: bi('Надіслати', 'Send') },
  ];

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="admin-comm-channels">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-token-muted flex items-center gap-2">
          <Radio className="w-3.5 h-3.5" /> F5 · {bi('Рівень провайдерів зв’язку', 'Communication Provider Layer')}
        </div>
        <h1 className="mt-2 text-2xl font-bold">{bi('Канали зв’язку', 'Communication Channels')}</h1>
        <p className="mt-1 text-token-muted text-sm max-w-2xl">
          {bi('Єдиний інтерфейс для всіх каналів. Ringostat / Gmail / Twilio / Telegram під’єднаються пізніше без змін у CRM, Timeline та аналітиці.',
              'One interface for every channel. Ringostat / Gmail / Twilio / Telegram plug in later with no changes to CRM, Timeline or analytics.')}
        </p>
      </div>

      <div className="flex gap-1 border-b border-border overflow-x-auto" data-testid="comm-tabs">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)} data-testid={`comm-tab-${t.id}`}
            className={`inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition whitespace-nowrap ${
              tab === t.id ? 'border-[#2E5D4F] text-token-primary' : 'border-transparent text-token-muted hover:text-token-secondary'}`}>
            <t.icon className="w-4 h-4" /> {t.label}
          </button>
        ))}
      </div>

      {tab === 'providers' && <ProvidersTab bi={bi} lang={lang} privileged={privileged} />}
      {tab === 'feed' && <FeedTab bi={bi} lang={lang} />}
      {tab === 'send' && <SendTab bi={bi} lang={lang} />}
    </div>
  );
}

function useApi(url, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const reload = useCallback(async () => {
    setLoading(true); setErr('');
    try { const r = await lumen.get(url); setData(r.data); }
    catch (e) { setErr(lumenError(e)); }
    finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { reload(); }, [reload]);
  return { data, loading, err, reload };
}

function StatusBadge({ status, lang }) {
  const s = STATUS[status] || STATUS.not_connected;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium border ${s.cls}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} /> {lang === 'en' ? s.en : s.uk}
    </span>
  );
}

// ── Providers ──
function ProvidersTab({ bi, lang, privileged }) {
  const { data, loading, err, reload } = useApi('/admin/comms/providers', []);
  const [busy, setBusy] = useState('');
  const providers = data?.providers || [];

  const toggle = async (p) => {
    const next = p.status === 'disabled' ? 'not_connected' : p.status === 'active' ? 'disabled' : null;
    if (p.key === 'manual' && next === 'disabled') { alert(bi('Ручний канал не можна вимкнути', 'Manual channel cannot be disabled')); return; }
    setBusy(p.key);
    try { await lumen.patch(`/admin/comms/providers/${p.key}`, { status: next || 'not_connected' }); await reload(); }
    catch (e) { alert(lumenError(e)); }
    finally { setBusy(''); }
  };
  const test = async (p) => {
    setBusy(p.key);
    try { const r = await lumen.post(`/admin/comms/providers/${p.key}/test`); alert(r.data?.message || 'OK'); await reload(); }
    catch (e) { alert(lumenError(e)); }
    finally { setBusy(''); }
  };

  return (
    <div className="space-y-4" data-testid="providers-tab">
      <div className="flex items-center justify-between">
        <div className="text-sm text-token-muted">{bi('Зареєстровано каналів', 'Registered channels')}: <span className="font-bold text-token-primary">{providers.length}</span></div>
        <button onClick={reload} className="h-9 px-3 rounded-lg text-sm border border-border hover:bg-muted inline-flex items-center gap-1.5">{loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} {bi('Оновити', 'Refresh')}</button>
      </div>
      {err && <p className="text-sm text-rose-600">{err}</p>}
      {loading && !data ? <Loading /> : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {providers.map((p) => {
            const Icon = TYPE_ICON[p.provider_type] || Plug;
            return (
              <div key={p.key} className="rounded-2xl border border-border bg-card p-5 flex flex-col" data-testid={`provider-card-${p.key}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className={`w-10 h-10 rounded-xl grid place-items-center ${p.status === 'active' ? 'bg-[#2E5D4F]/10 text-[#2E5D4F]' : 'bg-muted text-token-muted'}`}>
                      <Icon className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="font-semibold text-token-primary">{lang === 'en' ? (p.name_en || p.name) : p.name}</div>
                      <div className="text-[11px] text-token-muted capitalize">{p.provider_type} · {p.direction}</div>
                    </div>
                  </div>
                  <StatusBadge status={p.status} lang={lang} />
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {(p.capabilities || []).slice(0, 6).map((c) => (
                    <span key={c} className="text-[10px] px-2 py-0.5 rounded-full bg-muted text-token-muted">{c}</span>
                  ))}
                </div>
                {p.future && p.status === 'not_connected' && (
                  <div className="mt-3 text-[11px] text-token-muted flex items-center gap-1.5"><Zap className="w-3 h-3" /> {bi('Інтеграція у F6–F8', 'Integration in F6–F8')}</div>
                )}
                {privileged && (
                  <div className="mt-4 pt-3 border-t border-border flex items-center gap-2">
                    <button onClick={() => test(p)} disabled={busy === p.key} data-testid={`provider-test-${p.key}`}
                      className="flex-1 h-8 rounded-lg text-xs border border-border hover:bg-muted inline-flex items-center justify-center gap-1.5">
                      {busy === p.key ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plug className="w-3.5 h-3.5" />} {bi('Тест', 'Test')}
                    </button>
                    {p.key !== 'manual' && (
                      <button onClick={() => toggle(p)} disabled={busy === p.key} data-testid={`provider-toggle-${p.key}`}
                        className={`flex-1 h-8 rounded-lg text-xs inline-flex items-center justify-center gap-1.5 border ${p.status === 'disabled' ? 'border-emerald-200 text-emerald-700 hover:bg-emerald-50' : 'border-rose-200 text-rose-700 hover:bg-rose-50'}`}>
                        <Power className="w-3.5 h-3.5" /> {p.status === 'disabled' ? bi('Увімкнути', 'Enable') : bi('Вимкнути', 'Disable')}
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Feed ──
function DirIcon({ direction }) {
  if (direction === 'inbound') return <ArrowDownLeft className="w-3.5 h-3.5 text-emerald-600" />;
  if (direction === 'internal') return <RefreshCw className="w-3.5 h-3.5 text-slate-500" />;
  return <ArrowUpRight className="w-3.5 h-3.5 text-sky-600" />;
}

function FeedTab({ bi, lang }) {
  const [provider, setProvider] = useState('');
  const [direction, setDirection] = useState('');
  const [threadRef, setThreadRef] = useState('');
  const qs = `?limit=150${provider ? `&provider=${provider}` : ''}${direction ? `&direction=${direction}` : ''}${threadRef ? `&thread_ref=${encodeURIComponent(threadRef)}` : ''}`;
  const { data, loading, err, reload } = useApi(`/admin/comms/feed${qs}`, [provider, direction, threadRef]);
  const { data: provData } = useApi('/admin/comms/providers', []);
  const items = data?.items || [];

  return (
    <div className="space-y-4" data-testid="feed-tab">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <select value={provider} onChange={(e) => setProvider(e.target.value)} className="bg-card border border-border rounded-lg px-3 py-1.5 text-sm" data-testid="feed-provider-filter">
            <option value="">{bi('Усі провайдери', 'All providers')}</option>
            {(provData?.providers || []).map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
          </select>
          <select value={direction} onChange={(e) => setDirection(e.target.value)} className="bg-card border border-border rounded-lg px-3 py-1.5 text-sm" data-testid="feed-direction-filter">
            <option value="">{bi('Усі напрямки', 'All directions')}</option>
            <option value="inbound">{bi('Вхідні', 'Inbound')}</option>
            <option value="outbound">{bi('Вихідні', 'Outbound')}</option>
          </select>
          {threadRef && (
            <button
              onClick={() => setThreadRef('')}
              data-testid="feed-thread-filter-clear"
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[12px] bg-[#2E5D4F]/10 text-[#2E5D4F] border border-[#2E5D4F]/20 hover:bg-[#2E5D4F]/15"
              title={bi('Прибрати фільтр гілки', 'Clear thread filter')}
            >
              <span className="font-mono truncate max-w-[180px]">{threadRef}</span>
              <span className="text-xs">×</span>
            </button>
          )}
        </div>
        <button onClick={reload} className="h-9 px-3 rounded-lg text-sm border border-border hover:bg-muted inline-flex items-center gap-1.5">{loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} {bi('Оновити', 'Refresh')}</button>
      </div>
      {err && <p className="text-sm text-rose-600">{err}</p>}
      <div className="rounded-2xl border border-border bg-card overflow-x-auto">
        {loading && !data ? <Loading /> : items.length === 0 ? <Empty bi={bi} /> : (
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-xs uppercase tracking-wider text-token-muted">
              <tr>
                <th className="text-left px-4 py-2.5">{bi('Канал', 'Channel')}</th>
                <th className="text-left px-4 py-2.5">{bi('Тип', 'Type')}</th>
                <th className="text-left px-4 py-2.5">{bi('Зміст', 'Content')}</th>
                <th className="text-left px-4 py-2.5">{bi('Гілка', 'Thread')}</th>
                <th className="text-left px-4 py-2.5">{bi('Статус', 'Status')}</th>
                <th className="text-left px-4 py-2.5">{bi('Коли', 'When')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => {
                const sync = SYNC[it.sync_status] || SYNC.logged;
                const SyncIcon = sync.icon;
                return (
                  <tr key={it.comm_id} className="border-t border-border" data-testid="feed-row">
                    <td className="px-4 py-2.5"><span className="inline-flex items-center gap-1.5 capitalize font-medium"><DirIcon direction={it.direction} />{it.provider}</span></td>
                    <td className="px-4 py-2.5">{ITYPE_LABEL[it.interaction_type] ? (lang === 'en' ? ITYPE_LABEL[it.interaction_type].en : ITYPE_LABEL[it.interaction_type].uk) : it.interaction_type}</td>
                    <td className="px-4 py-2.5"><div className="font-medium text-token-primary">{it.title || '—'}</div><div className="text-[11px] text-token-muted truncate max-w-[280px]">{it.detail || it.contact || ''}</div></td>
                    <td className="px-4 py-2.5">
                      {it.thread_ref ? (
                        <button
                          onClick={() => setThreadRef(it.thread_ref)}
                          data-testid="feed-thread-badge"
                          title={bi('Показати лише цю гілку', 'Show only this thread')}
                          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-mono bg-muted hover:bg-[#2E5D4F]/10 hover:text-[#2E5D4F] transition truncate max-w-[140px]"
                        >
                          {it.thread_ref.length > 14 ? `${it.thread_ref.slice(0, 14)}…` : it.thread_ref}
                        </button>
                      ) : (
                        <span className="text-token-muted">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5"><span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] ${sync.cls}`}><SyncIcon className="w-3 h-3" />{lang === 'en' ? sync.en : sync.uk}</span></td>
                    <td className="px-4 py-2.5 text-token-muted text-[11px]">{it.at ? formatDateUk(it.at) : '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ── Send ──
function SendTab({ bi, lang }) {
  const { data: provData } = useApi('/admin/comms/providers', []);
  const [form, setForm] = useState({ provider: 'manual', interaction_type: 'call', direction: 'outbound', contact: '', subject: '', body: '' });
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);
  const providers = (provData?.providers || []);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setSending(true); setResult(null);
    try {
      const r = await lumen.post('/comms/send', form);
      setResult({ ok: r.data?.ok, msg: r.data?.ok ? bi('Записано в журнал зв’язку', 'Recorded in communication log') : bi('Провайдер не під’єднано — інтенцію збережено', 'Provider not connected — intent saved'), sync: r.data?.sync_status });
      setForm((f) => ({ ...f, subject: '', body: '' }));
    } catch (err) { setResult({ ok: false, msg: lumenError(err) }); }
    finally { setSending(false); }
  };

  return (
    <div className="max-w-2xl" data-testid="send-tab">
      <form onSubmit={submit} className="rounded-2xl border border-border bg-card p-5 space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-xs text-token-muted">{bi('Провайдер', 'Provider')}</span>
            <select value={form.provider} onChange={set('provider')} className="mt-1 w-full bg-app-surface border border-border rounded-lg px-3 py-2 text-sm" data-testid="send-provider">
              {providers.map((p) => (
                <option key={p.key} value={p.key} disabled={p.status === 'disabled'}>
                  {p.name}{p.status !== 'active' ? ` (${lang === 'en' ? 'not connected' : 'не під’єднано'})` : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-xs text-token-muted">{bi('Тип', 'Type')}</span>
            <select value={form.interaction_type} onChange={set('interaction_type')} className="mt-1 w-full bg-app-surface border border-border rounded-lg px-3 py-2 text-sm" data-testid="send-type">
              {Object.keys(ITYPE_LABEL).map((k) => <option key={k} value={k}>{lang === 'en' ? ITYPE_LABEL[k].en : ITYPE_LABEL[k].uk}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-xs text-token-muted">{bi('Напрямок', 'Direction')}</span>
            <select value={form.direction} onChange={set('direction')} className="mt-1 w-full bg-app-surface border border-border rounded-lg px-3 py-2 text-sm" data-testid="send-direction">
              <option value="outbound">{bi('Вихідний', 'Outbound')}</option>
              <option value="inbound">{bi('Вхідний', 'Inbound')}</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs text-token-muted">{bi('Контакт (email / телефон)', 'Contact (email / phone)')}</span>
            <input value={form.contact} onChange={set('contact')} placeholder="investor@example.com" className="mt-1 w-full bg-app-surface border border-border rounded-lg px-3 py-2 text-sm" data-testid="send-contact" />
          </label>
        </div>
        <label className="block">
          <span className="text-xs text-token-muted">{bi('Тема', 'Subject')}</span>
          <input value={form.subject} onChange={set('subject')} className="mt-1 w-full bg-app-surface border border-border rounded-lg px-3 py-2 text-sm" data-testid="send-subject" />
        </label>
        <label className="block">
          <span className="text-xs text-token-muted">{bi('Повідомлення / нотатка', 'Message / note')}</span>
          <textarea value={form.body} onChange={set('body')} rows={4} className="mt-1 w-full bg-app-surface border border-border rounded-lg px-3 py-2 text-sm" data-testid="send-body" />
        </label>
        <div className="flex items-center justify-between gap-3">
          <button type="submit" disabled={sending} data-testid="send-submit"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#2E5D4F] text-white text-sm font-semibold hover:bg-[#274f43] transition disabled:opacity-60">
            {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} {bi('Записати / надіслати', 'Record / send')}
          </button>
          {result && (
            <span className={`text-sm ${result.ok ? 'text-emerald-700' : 'text-amber-700'}`} data-testid="send-result">{result.msg}</span>
          )}
        </div>
      </form>
    </div>
  );
}

function Loading() { return <div className="py-12 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto text-token-muted" /></div>; }
function Empty({ bi }) { return <p className="p-6 text-sm text-token-muted text-center">{bi('Немає даних.', 'No data.')}</p>; }
