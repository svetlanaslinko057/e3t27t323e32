/**
 * AdminStaffSecurity — F3 Staff Security Center.
 * Tabs: Online · Sessions · Suspicious · Failed Logins.
 * Built on Manager OS M5 (login audit + sessions) + F2 presence.
 */
import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError, formatDateUk } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import { useAuth } from '@/App';
import {
  ShieldCheck, Loader2, RefreshCw, Monitor, AlertTriangle, Radio, LogOut,
  Wifi, WifiOff, Clock, Smartphone, Globe, ShieldAlert, KeyRound, UserX,
} from 'lucide-react';

const PRIVILEGED = new Set(['admin', 'owner', 'master_admin', 'team_lead']);

const PRESENCE = {
  online: { cls: 'text-emerald-600', dot: 'bg-emerald-500', icon: Wifi, uk: 'Онлайн', en: 'Online' },
  away: { cls: 'text-amber-600', dot: 'bg-amber-500', icon: Clock, uk: 'Відійшов', en: 'Away' },
  offline: { cls: 'text-slate-400', dot: 'bg-slate-400', icon: WifiOff, uk: 'Офлайн', en: 'Offline' },
};

const SEV = {
  high: { cls: 'bg-rose-500/10 text-rose-700 border-rose-200', uk: 'Високий', en: 'High' },
  medium: { cls: 'bg-amber-500/10 text-amber-700 border-amber-200', uk: 'Середній', en: 'Medium' },
  low: { cls: 'bg-sky-500/10 text-sky-700 border-sky-200', uk: 'Низький', en: 'Low' },
};

const SIGNAL_LABEL = {
  failed_burst: { uk: 'Серія невдалих входів', en: 'Failed login burst' },
  rapid_ip_switch: { uk: 'Швидка зміна IP', en: 'Rapid IP switch' },
  new_device: { uk: 'Новий пристрій', en: 'New device' },
  ip_changed: { uk: 'Зміна IP', en: 'IP changed' },
  concurrent_sessions: { uk: 'Багато сесій', en: 'Concurrent sessions' },
};

export default function AdminStaffSecurity() {
  const { bi, lang } = useLang();
  const { user } = useAuth();
  const privileged = PRIVILEGED.has((user?.role || '').toLowerCase());
  const [tab, setTab] = useState('online');

  const TABS = [
    { id: 'online', icon: Radio, label: bi('Онлайн', 'Online') },
    { id: 'sessions', icon: Monitor, label: bi('Сесії', 'Sessions') },
    { id: 'suspicious', icon: ShieldAlert, label: bi('Підозрілі', 'Suspicious') },
    { id: 'failed', icon: KeyRound, label: bi('Невдалі входи', 'Failed Logins') },
  ];

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="admin-staff-security">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-token-muted flex items-center gap-2">
          <ShieldCheck className="w-3.5 h-3.5" /> F3 · {bi('Центр безпеки персоналу', 'Staff Security Center')}
        </div>
        <h1 className="mt-2 text-2xl font-bold">{bi('Безпека та сесії персоналу', 'Staff Security & Sessions')}</h1>
        <p className="mt-1 text-token-muted text-sm max-w-2xl">
          {bi('Хто онлайн, де залогінений, підозрілі входи та примусове завершення сесій.',
              'Who is online, where they are logged in, suspicious logins, and force logout.')}
        </p>
      </div>

      <div className="flex gap-1 border-b border-border overflow-x-auto" data-testid="staff-sec-tabs">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)} data-testid={`staff-tab-${t.id}`}
            className={`inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition whitespace-nowrap ${
              tab === t.id ? 'border-[#2E5D4F] text-token-primary' : 'border-transparent text-token-muted hover:text-token-secondary'}`}>
            <t.icon className="w-4 h-4" /> {t.label}
          </button>
        ))}
      </div>

      {tab === 'online' && <OnlineTab bi={bi} lang={lang} privileged={privileged} />}
      {tab === 'sessions' && <SessionsTab bi={bi} lang={lang} privileged={privileged} />}
      {tab === 'suspicious' && <SuspiciousTab bi={bi} lang={lang} />}
      {tab === 'failed' && <FailedTab bi={bi} lang={lang} />}
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

function RefreshBtn({ onClick, loading, bi }) {
  return (
    <button onClick={onClick} data-testid="sec-refresh" className="h-9 px-3 rounded-lg text-sm border border-border hover:bg-muted inline-flex items-center gap-1.5">
      {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} {bi('Оновити', 'Refresh')}
    </button>
  );
}

function PresenceBadge({ status, lang }) {
  const p = PRESENCE[status] || PRESENCE.offline;
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${p.cls}`}>
      <span className={`w-2 h-2 rounded-full ${p.dot}`} /> {lang === 'en' ? p.en : p.uk}
    </span>
  );
}

async function doRevoke(kind, id, bi, reload) {
  const reason = window.prompt(bi('Причина завершення сесій (необов’язково):', 'Reason for logout (optional):'), '');
  if (reason === null) return;
  try {
    if (kind === 'session') await lumen.post(`/admin/staff/sessions/${id}/revoke`, { reason });
    else await lumen.post(`/admin/staff/sessions/user/${id}/revoke-all`, { reason });
    await reload();
  } catch (e) {
    alert(lumenError(e, bi('Не вдалось завершити сесію', 'Failed to revoke session')));
  }
}

// ── Online ──
function OnlineTab({ bi, lang, privileged }) {
  const { data, loading, err, reload } = useApi('/admin/staff/sessions/online', []);
  const staff = data?.staff || [];
  const c = data?.counts || {};
  return (
    <div className="space-y-4" data-testid="online-tab">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-3">
          {['online', 'away', 'offline'].map((k) => {
            const P = PRESENCE[k];
            return (
              <div key={k} className="rounded-xl border border-border bg-card px-4 py-2.5 flex items-center gap-2" data-testid={`online-count-${k}`}>
                <span className={`w-2.5 h-2.5 rounded-full ${P.dot}`} />
                <span className="text-2xl font-bold tabular-nums">{c[k] ?? 0}</span>
                <span className="text-xs text-token-muted">{lang === 'en' ? P.en : P.uk}</span>
              </div>
            );
          })}
        </div>
        <RefreshBtn onClick={reload} loading={loading} bi={bi} />
      </div>
      {err && <p className="text-sm text-rose-600">{err}</p>}
      <div className="rounded-2xl border border-border bg-card overflow-x-auto">
        {loading && !data ? <Loading /> : staff.length === 0 ? <Empty bi={bi} /> : (
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-xs uppercase tracking-wider text-token-muted">
              <tr>
                <th className="text-left px-4 py-2.5">{bi('Користувач', 'User')}</th>
                <th className="text-left px-4 py-2.5">{bi('Статус', 'Status')}</th>
                <th className="text-left px-4 py-2.5">{bi('Остання активність', 'Last seen')}</th>
                <th className="text-center px-4 py-2.5">{bi('Сесії', 'Sessions')}</th>
                <th className="text-center px-4 py-2.5">IP</th>
                {privileged && <th className="text-right px-4 py-2.5">{bi('Дія', 'Action')}</th>}
              </tr>
            </thead>
            <tbody>
              {staff.map((s) => (
                <tr key={s.user_id} className="border-t border-border" data-testid="online-row">
                  <td className="px-4 py-2.5"><div className="font-medium">{s.name || '—'}</div><div className="text-[11px] text-token-muted">{s.email}</div></td>
                  <td className="px-4 py-2.5"><PresenceBadge status={s.status} lang={lang} /></td>
                  <td className="px-4 py-2.5 text-token-muted">{s.last_seen_at ? formatDateUk(s.last_seen_at) : '—'}</td>
                  <td className="px-4 py-2.5 text-center tabular-nums">
                    <span className={s.session_count >= 5 ? 'text-rose-600 font-bold' : s.session_count >= 3 ? 'text-amber-600 font-semibold' : ''}>{s.session_count}</span>
                  </td>
                  <td className="px-4 py-2.5 text-center tabular-nums">{s.distinct_ips}</td>
                  {privileged && (
                    <td className="px-4 py-2.5 text-right">
                      <button onClick={() => doRevoke('user', s.user_id, bi, reload)} data-testid={`revoke-all-${s.user_id}`}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-rose-200 text-rose-700 text-xs font-medium hover:bg-rose-50 transition">
                        <UserX className="w-3.5 h-3.5" /> {bi('Завершити всі', 'Logout all')}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ── Sessions ──
function SessionsTab({ bi, lang, privileged }) {
  const { data, loading, err, reload } = useApi('/admin/staff/sessions/list', []);
  const sessions = data?.sessions || [];
  return (
    <div className="space-y-4" data-testid="sessions-tab">
      <div className="flex items-center justify-between">
        <div className="text-sm text-token-muted">{bi('Активні сесії', 'Active sessions')}: <span className="font-bold text-token-primary">{sessions.length}</span></div>
        <RefreshBtn onClick={reload} loading={loading} bi={bi} />
      </div>
      {err && <p className="text-sm text-rose-600">{err}</p>}
      <div className="rounded-2xl border border-border bg-card overflow-x-auto">
        {loading && !data ? <Loading /> : sessions.length === 0 ? <Empty bi={bi} /> : (
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-xs uppercase tracking-wider text-token-muted">
              <tr>
                <th className="text-left px-4 py-2.5">{bi('Користувач', 'User')}</th>
                <th className="text-left px-4 py-2.5">{bi('Пристрій', 'Device')}</th>
                <th className="text-left px-4 py-2.5">IP</th>
                <th className="text-left px-4 py-2.5">{bi('Статус', 'Status')}</th>
                <th className="text-left px-4 py-2.5">{bi('Перша / Остання', 'First / Last')}</th>
                {privileged && <th className="text-right px-4 py-2.5">{bi('Дія', 'Action')}</th>}
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.session_id} className="border-t border-border" data-testid="session-row">
                  <td className="px-4 py-2.5"><div className="font-medium">{s.name || '—'}</div><div className="text-[11px] text-token-muted">{s.email}</div></td>
                  <td className="px-4 py-2.5"><span className="inline-flex items-center gap-1.5"><Smartphone className="w-3.5 h-3.5 text-token-muted" />{s.device || '—'}</span></td>
                  <td className="px-4 py-2.5 font-mono text-[11px] text-token-muted"><span className="inline-flex items-center gap-1"><Globe className="w-3 h-3" />{s.ip || '—'}</span></td>
                  <td className="px-4 py-2.5"><PresenceBadge status={s.status} lang={lang} /></td>
                  <td className="px-4 py-2.5 text-[11px] text-token-muted">
                    <div>{s.first_seen_at ? formatDateUk(s.first_seen_at) : '—'}</div>
                    <div>{s.last_seen_at ? formatDateUk(s.last_seen_at) : '—'}</div>
                  </td>
                  {privileged && (
                    <td className="px-4 py-2.5 text-right">
                      <button onClick={() => doRevoke('session', s.session_id, bi, reload)} data-testid={`revoke-session-${s.session_id}`}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border text-token-secondary text-xs font-medium hover:bg-muted transition">
                        <LogOut className="w-3.5 h-3.5" /> {bi('Завершити', 'Logout')}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ── Suspicious ──
function SuspiciousTab({ bi, lang }) {
  const { data, loading, err, reload } = useApi('/admin/staff/sessions/suspicious?hours=24', []);
  const findings = data?.findings || [];
  const tally = data?.tally || {};
  return (
    <div className="space-y-4" data-testid="suspicious-tab">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-2">
          {['high', 'medium', 'low'].map((k) => (
            <span key={k} className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border ${SEV[k].cls}`} data-testid={`sev-count-${k}`}>
              {lang === 'en' ? SEV[k].en : SEV[k].uk}: {tally[k] ?? 0}
            </span>
          ))}
        </div>
        <RefreshBtn onClick={reload} loading={loading} bi={bi} />
      </div>
      {err && <p className="text-sm text-rose-600">{err}</p>}
      {loading && !data ? <Loading /> : findings.length === 0 ? (
        <div className="rounded-2xl border border-border bg-card py-10 text-center text-sm text-token-muted" data-testid="suspicious-empty">
          <ShieldCheck className="w-8 h-8 mx-auto mb-2 text-emerald-500" />
          {bi('Підозрілої активності не виявлено', 'No suspicious activity detected')}
        </div>
      ) : (
        <div className="space-y-3">
          {findings.map((f) => (
            <div key={f.key} className="rounded-2xl border border-border bg-card p-4" data-testid="suspicious-card">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-semibold text-token-primary">{f.name || f.email || f.key}</div>
                  <div className="text-[11px] text-token-muted">{f.email} {f.role ? `· ${f.role}` : ''}</div>
                </div>
                <span className={`shrink-0 px-2.5 py-1 rounded-full text-[11px] font-semibold border ${SEV[f.max_severity]?.cls}`}>
                  {lang === 'en' ? SEV[f.max_severity]?.en : SEV[f.max_severity]?.uk}
                </span>
              </div>
              <div className="mt-3 space-y-1.5">
                {f.signals.map((sig, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm" data-testid="suspicious-signal">
                    <AlertTriangle className={`w-3.5 h-3.5 shrink-0 ${sig.severity === 'high' ? 'text-rose-600' : sig.severity === 'medium' ? 'text-amber-600' : 'text-sky-600'}`} />
                    <span className="font-medium text-token-secondary">{lang === 'en' ? SIGNAL_LABEL[sig.type]?.en : SIGNAL_LABEL[sig.type]?.uk}</span>
                    <span className="text-token-muted">— {sig.detail}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Failed Logins ──
function FailedTab({ bi }) {
  const { data, loading, err, reload } = useApi('/admin/staff/sessions/failed-logins?hours=24', []);
  const byTarget = data?.by_target || [];
  const recent = data?.recent || [];
  return (
    <div className="space-y-4" data-testid="failed-tab">
      <div className="flex items-center justify-between">
        <div className="text-sm text-token-muted">{bi('Невдалих входів за 24 год', 'Failed logins (24h)')}: <span className="font-bold text-rose-600">{data?.total_failures ?? 0}</span></div>
        <RefreshBtn onClick={reload} loading={loading} bi={bi} />
      </div>
      {err && <p className="text-sm text-rose-600">{err}</p>}
      <div className="rounded-2xl border border-border bg-card overflow-x-auto">
        <div className="px-5 py-3 border-b border-border font-semibold text-sm">{bi('За ціллю', 'By target')}</div>
        {loading && !data ? <Loading /> : byTarget.length === 0 ? <Empty bi={bi} /> : (
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-xs uppercase tracking-wider text-token-muted">
              <tr><th className="text-left px-4 py-2.5">Email</th><th className="text-center px-4 py-2.5">{bi('Спроби', 'Attempts')}</th><th className="text-center px-4 py-2.5">IP</th><th className="text-left px-4 py-2.5">{bi('Остання', 'Last')}</th><th className="text-right px-4 py-2.5">{bi('Прапор', 'Flag')}</th></tr>
            </thead>
            <tbody>
              {byTarget.map((t, i) => (
                <tr key={i} className="border-t border-border" data-testid="failed-target-row">
                  <td className="px-4 py-2.5 font-medium">{t.email}</td>
                  <td className="px-4 py-2.5 text-center tabular-nums font-bold">{t.attempts}</td>
                  <td className="px-4 py-2.5 text-center tabular-nums">{t.distinct_ips}</td>
                  <td className="px-4 py-2.5 text-token-muted text-[11px]">{t.last_at ? formatDateUk(t.last_at) : '—'}</td>
                  <td className="px-4 py-2.5 text-right">
                    {t.brute_force && <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-700 text-[11px] font-semibold"><ShieldAlert className="w-3 h-3" /> {bi('Брутфорс', 'Brute force')}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="rounded-2xl border border-border bg-card overflow-x-auto">
        <div className="px-5 py-3 border-b border-border font-semibold text-sm">{bi('Останні спроби', 'Recent attempts')}</div>
        {recent.length === 0 ? <Empty bi={bi} /> : (
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-xs uppercase tracking-wider text-token-muted">
              <tr><th className="text-left px-4 py-2.5">Email</th><th className="text-left px-4 py-2.5">IP</th><th className="text-left px-4 py-2.5">{bi('Пристрій', 'Device')}</th><th className="text-left px-4 py-2.5">{bi('Коли', 'When')}</th></tr>
            </thead>
            <tbody>
              {recent.slice(0, 100).map((r, i) => (
                <tr key={i} className="border-t border-border" data-testid="failed-recent-row">
                  <td className="px-4 py-2.5">{r.email || '—'}</td>
                  <td className="px-4 py-2.5 font-mono text-[11px] text-token-muted">{r.ip || '—'}</td>
                  <td className="px-4 py-2.5 text-token-muted text-[11px]">{r.device}</td>
                  <td className="px-4 py-2.5 text-token-muted text-[11px]">{r.at ? formatDateUk(r.at) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Loading() { return <div className="py-12 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto text-token-muted" /></div>; }
function Empty({ bi }) { return <p className="p-6 text-sm text-token-muted text-center">{bi('Немає даних.', 'No data.')}</p>; }
