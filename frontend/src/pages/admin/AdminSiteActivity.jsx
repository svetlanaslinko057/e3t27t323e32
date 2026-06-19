/**
 * AdminSiteActivity — F2 main screen ("Активність сайту").
 * Tabs: Overview · Live · Abandonment · Attribution · Top Pages · Timeline.
 * Reads the F2 Lumen Activity Layer (/api/admin/activity/*).
 */
import { useEffect, useState, useCallback } from 'react';
import { lumen, formatUSD, usdFromUah } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import LiveActivityWidget from '@/components/lumen/LiveActivityWidget';
import ActivityTimeline from '@/components/lumen/ActivityTimeline';
import {
  Activity, Radio, AlertTriangle, BarChart3, FileText, Search,
  Loader2, TrendingDown, Users, Eye, MousePointerClick, UserPlus, RefreshCw,
} from 'lucide-react';

const RANGES = [
  { id: '24h', uk: '24 год', en: '24h' },
  { id: '7d', uk: '7 днів', en: '7d' },
  { id: '30d', uk: '30 днів', en: '30d' },
  { id: '90d', uk: '90 днів', en: '90d' },
];

function Stat({ icon: Icon, label, value, accent }) {
  return (
    <div className="rounded-2xl border border-app bg-app-surface p-5" data-testid="activity-stat">
      <div className="flex items-center gap-2 text-token-muted text-[11px] uppercase tracking-wider">
        <Icon className="w-4 h-4" /> {label}
      </div>
      <div className={`mt-2 text-3xl font-bold tabular-nums ${accent || 'text-token-primary'}`}>{value}</div>
    </div>
  );
}

function TabButton({ active, onClick, icon: Icon, label, testid }) {
  return (
    <button
      onClick={onClick}
      data-testid={testid}
      className={`inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition whitespace-nowrap ${
        active ? 'border-[#2E5D4F] text-token-primary' : 'border-transparent text-token-muted hover:text-token-secondary'
      }`}
    >
      <Icon className="w-4 h-4" /> {label}
    </button>
  );
}

export default function AdminSiteActivity() {
  const { bi, lang } = useLang();
  const [tab, setTab] = useState('overview');
  const [range, setRange] = useState('7d');

  const L = (uk, en) => bi(uk, en);
  const pick = (obj) => obj ? (lang === 'en' ? obj.en : obj.uk) : '';

  return (
    <div className="p-6 md:p-10 max-w-7xl mx-auto" data-testid="admin-site-activity">
      <header className="mb-6 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <p className="text-xs uppercase tracking-widest text-token-muted flex items-center gap-2">
            <Activity className="w-3.5 h-3.5" /> F2 · Lumen Activity Layer
          </p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-token-primary">{L('Активність сайту', 'Site Activity')}</h1>
          <p className="mt-1 text-token-muted max-w-2xl">
            {L('Реальна поведінка відвідувачів: від першого візиту до активного інвестора. Де саме втрачається інвестор.',
               'Real visitor behaviour from first visit to active investor. Exactly where investors are lost.')}
          </p>
        </div>
        <div className="flex items-center gap-1 bg-app-elevated rounded-xl p-1" data-testid="activity-range">
          {RANGES.map((r) => (
            <button key={r.id} onClick={() => setRange(r.id)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition ${range === r.id ? 'bg-app-surface text-token-primary shadow-sm' : 'text-token-muted'}`}
              data-testid={`range-${r.id}`}>
              {lang === 'en' ? r.en : r.uk}
            </button>
          ))}
        </div>
      </header>

      <div className="flex gap-1 border-b border-app mb-6 overflow-x-auto" data-testid="activity-tabs">
        <TabButton active={tab === 'overview'} onClick={() => setTab('overview')} icon={BarChart3} label={L('Огляд', 'Overview')} testid="tab-overview" />
        <TabButton active={tab === 'live'} onClick={() => setTab('live')} icon={Radio} label={L('Наживо', 'Live')} testid="tab-live" />
        <TabButton active={tab === 'abandonment'} onClick={() => setTab('abandonment')} icon={AlertTriangle} label={L('Покинуті', 'Abandonment')} testid="tab-abandonment" />
        <TabButton active={tab === 'attribution'} onClick={() => setTab('attribution')} icon={TrendingDown} label={L('Атрибуція', 'Attribution')} testid="tab-attribution" />
        <TabButton active={tab === 'pages'} onClick={() => setTab('pages')} icon={FileText} label={L('Топ сторінок', 'Top Pages')} testid="tab-pages" />
        <TabButton active={tab === 'timeline'} onClick={() => setTab('timeline')} icon={Search} label={L('Стрічка', 'Timeline')} testid="tab-timeline" />
      </div>

      {tab === 'overview' && <OverviewTab range={range} L={L} pick={pick} />}
      {tab === 'live' && <LiveActivityWidget />}
      {tab === 'abandonment' && <AbandonmentTab L={L} pick={pick} />}
      {tab === 'attribution' && <AttributionTab range={range} L={L} pick={pick} />}
      {tab === 'pages' && <AttributionTab range={range} L={L} pick={pick} pagesOnly />}
      {tab === 'timeline' && <TimelineSearchTab L={L} />}
    </div>
  );
}

function useFetch(url, deps) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    setLoading(true);
    try { const r = await lumen.get(url); setData(r.data); }
    catch (_) { setData(null); }
    finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { reload(); }, [reload]);
  return { data, loading, reload };
}

function OverviewTab({ range, L }) {
  const { data, loading } = useFetch(`/admin/activity/overview?range=${range}`, [range]);
  if (loading && !data) return <Loading />;
  const by = data?.by_event || {};
  return (
    <div className="space-y-6" data-testid="overview-tab">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat icon={Users} label={L('Унікальні відвідувачі', 'Unique visitors')} value={data?.unique_visitors ?? 0} />
        <Stat icon={Eye} label={L('Перегляди сторінок', 'Page views')} value={by.page_view || 0} />
        <Stat icon={MousePointerClick} label={L('Кліки CTA', 'CTA clicks')} value={by.cta_click || 0} accent="text-sky-600" />
        <Stat icon={UserPlus} label={L('Нові ліди', 'New leads')} value={data?.leads ?? 0} accent="text-[#2E5D4F]" />
      </div>

      <div className="rounded-2xl border border-app bg-app-surface p-5">
        <h3 className="font-semibold text-token-primary mb-3">{L('Динаміка (днів)', 'Daily trend')}</h3>
        <DailyBars daily={data?.daily || []} L={L} />
      </div>

      <div className="rounded-2xl border border-app bg-app-surface p-5">
        <h3 className="font-semibold text-token-primary mb-3">{L('Події за типом', 'Events by type')}</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Object.entries(by).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
            <div key={k} className="flex items-center justify-between text-sm px-3 py-2 rounded-lg bg-app-elevated">
              <span className="text-token-muted truncate">{k}</span>
              <span className="font-bold text-token-primary tabular-nums">{v}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function DailyBars({ daily, L }) {
  if (!daily.length) return <div className="text-sm text-token-muted">{L('Немає даних', 'No data')}</div>;
  const max = Math.max(1, ...daily.map((d) => d.events));
  return (
    <div className="flex items-end gap-1.5 h-40" data-testid="daily-bars">
      {daily.map((d, i) => (
        <div key={i} className="flex-1 flex flex-col items-center gap-1 group">
          <div className="w-full bg-[#2E5D4F]/15 rounded-t relative" style={{ height: `${(d.events / max) * 100}%`, minHeight: 2 }}>
            <div className="absolute inset-x-0 bottom-0 bg-[#2E5D4F] rounded-t" style={{ height: d.events ? '100%' : 0 }} />
            <span className="absolute -top-5 left-1/2 -translate-x-1/2 text-[10px] text-token-muted opacity-0 group-hover:opacity-100 whitespace-nowrap">{d.events}</span>
          </div>
          <span className="text-[9px] text-token-muted whitespace-nowrap">{(d.date || '').slice(5)}</span>
        </div>
      ))}
    </div>
  );
}

function AbandonmentTab({ L, pick }) {
  const [idle, setIdle] = useState(3);
  const { data, loading } = useFetch(`/admin/activity/abandonment?idle_days=${idle}`, [idle]);
  if (loading && !data) return <Loading />;
  const rows = data?.rows || [];
  return (
    <div className="space-y-5" data-testid="abandonment-tab">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <span className="text-sm text-token-muted">{L('Простій понад', 'Idle more than')}</span>
          <select value={idle} onChange={(e) => setIdle(Number(e.target.value))}
            className="bg-app-surface border border-app rounded-lg px-3 py-1.5 text-sm" data-testid="abandon-idle-select">
            {[0, 1, 3, 7, 14, 30].map((d) => <option key={d} value={d}>{d} {L('днів', 'days')}</option>)}
          </select>
        </div>
        <div className="text-sm text-token-muted">
          {L('Знайдено', 'Found')}: <span className="font-bold text-rose-600" data-testid="abandon-count">{data?.abandoned_count ?? 0}</span>
        </div>
      </div>

      {Object.keys(data?.by_stage || {}).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(data.by_stage).map(([stage, n]) => (
            <span key={stage} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-rose-500/10 text-rose-700 text-xs font-medium">
              {stage} · {n}
            </span>
          ))}
        </div>
      )}

      <div className="rounded-2xl border border-app bg-app-surface overflow-hidden">
        {rows.length === 0 ? (
          <div className="py-10 text-center text-sm text-token-muted">{L('Покинутих лідів не знайдено', 'No abandoned leads found')}</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-token-muted border-b border-app">
                <th className="px-4 py-3">{L('Інвестор / Лід', 'Investor / Lead')}</th>
                <th className="px-4 py-3">{L('Покинута стадія', 'Abandoned stage')}</th>
                <th className="px-4 py-3 text-right">{L('Днів простою', 'Days idle')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-b border-app last:border-0 hover:bg-app-elevated" data-testid="abandon-row">
                  <td className="px-4 py-3 font-medium text-token-primary">{r.identity}</td>
                  <td className="px-4 py-3">
                    <span className="inline-flex px-2 py-0.5 rounded-lg bg-amber-500/10 text-amber-700 text-xs font-medium">
                      {pick(r.abandoned_stage_label) || r.abandoned_stage}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-bold tabular-nums text-rose-600">{r.days_idle}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function AttributionTab({ range, L, pagesOnly = false }) {
  const { data, loading } = useFetch(`/admin/activity/attribution?range=${range}`, [range]);
  if (loading && !data) return <Loading />;
  const pages = data?.top_pages || [];
  const leadsByPage = data?.leads_by_page || [];
  const assets = data?.assets || [];
  const managers = data?.manager_conversion || [];

  return (
    <div className="space-y-6" data-testid="attribution-tab">
      <div className="rounded-2xl border border-app bg-app-surface overflow-hidden">
        <div className="px-5 py-4 border-b border-app font-semibold text-token-primary">{L('Топ сторінок', 'Top pages')}</div>
        {pages.length === 0 ? <Empty L={L} /> : (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] uppercase tracking-wider text-token-muted border-b border-app">
              <th className="px-5 py-3">{L('Сторінка', 'Page')}</th>
              <th className="px-4 py-3 text-right">{L('Перегляди', 'Views')}</th>
              <th className="px-4 py-3 text-right">{L('Унікальні', 'Unique')}</th>
              <th className="px-4 py-3 text-right">CTA</th>
              <th className="px-4 py-3 text-right">{L('Ліди', 'Leads')}</th>
              <th className="px-4 py-3 text-right">{L('Конверсія', 'Conv.')}</th>
            </tr></thead>
            <tbody>
              {pages.map((p, i) => (
                <tr key={i} className="border-b border-app last:border-0 hover:bg-app-elevated" data-testid="page-row">
                  <td className="px-5 py-3 font-medium text-token-primary truncate max-w-[280px]">{p.path}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{p.views}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-token-muted">{p.unique_visitors}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-sky-600">{p.ctas}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-[#2E5D4F] font-medium">{p.leads}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{(p.lead_conversion * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {!pagesOnly && (
        <>
          <div className="grid md:grid-cols-2 gap-6">
            <div className="rounded-2xl border border-app bg-app-surface overflow-hidden">
              <div className="px-5 py-4 border-b border-app font-semibold text-token-primary">{L('Ліди за сторінкою', 'Leads by page')}</div>
              {leadsByPage.length === 0 ? <Empty L={L} /> : (
                <ul className="divide-y divide-app">
                  {leadsByPage.map((r, i) => (
                    <li key={i} className="px-5 py-3 flex items-center justify-between text-sm">
                      <span className="truncate text-token-secondary">{r.path}</span>
                      <span className="font-bold text-[#2E5D4F] tabular-nums">{r.leads}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="rounded-2xl border border-app bg-app-surface overflow-hidden">
              <div className="px-5 py-4 border-b border-app font-semibold text-token-primary">{L('Перегляди об\u0027єктів → Funding', 'Asset views → Funding')}</div>
              {assets.length === 0 ? <Empty L={L} /> : (
                <ul className="divide-y divide-app">
                  {assets.map((a, i) => (
                    <li key={i} className="px-5 py-3 flex items-center justify-between text-sm gap-3">
                      <span className="truncate text-token-secondary">{a.title || a.asset_id}</span>
                      <span className="flex items-center gap-3 shrink-0">
                        <span className="text-token-muted tabular-nums">{a.views} {L('перегл.', 'views')}</span>
                        {a.funding?.certificate_value_uah ? (
                          <span className="font-bold text-[#2E5D4F] tabular-nums">{formatUSD(usdFromUah(a.funding.certificate_value_uah))}</span>
                        ) : null}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-app bg-app-surface overflow-hidden">
            <div className="px-5 py-4 border-b border-app font-semibold text-token-primary">{L('Конверсія менеджерів', 'Manager conversion')}</div>
            {managers.length === 0 ? <Empty L={L} /> : (
              <table className="w-full text-sm">
                <thead><tr className="text-left text-[11px] uppercase tracking-wider text-token-muted border-b border-app">
                  <th className="px-5 py-3">{L('Менеджер', 'Manager')}</th>
                  <th className="px-4 py-3 text-right">{L('Контакти', 'Touched')}</th>
                  <th className="px-4 py-3 text-right">Funding</th>
                  <th className="px-4 py-3 text-right">{L('Конверсія', 'Conv.')}</th>
                </tr></thead>
                <tbody>
                  {managers.map((m, i) => (
                    <tr key={i} className="border-b border-app last:border-0 hover:bg-app-elevated">
                      <td className="px-5 py-3 font-medium text-token-primary">{m.manager_name || m.manager_id}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{m.touched_identities}</td>
                      <td className="px-4 py-3 text-right tabular-nums text-[#2E5D4F] font-medium">{m.funded}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{(m.conversion * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function TimelineSearchTab({ L }) {
  const [field, setField] = useState('user_id');
  const [val, setVal] = useState('');
  const [query, setQuery] = useState(null);

  const submit = (e) => { e.preventDefault(); if (val.trim()) setQuery({ field, val: val.trim() }); };

  return (
    <div className="space-y-5" data-testid="timeline-tab">
      <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
        <select value={field} onChange={(e) => setField(e.target.value)}
          className="bg-app-surface border border-app rounded-lg px-3 py-2 text-sm" data-testid="timeline-field">
          <option value="user_id">user_id</option>
          <option value="lead_id">lead_id</option>
          <option value="visitor_id">visitor_id</option>
        </select>
        <input value={val} onChange={(e) => setVal(e.target.value)}
          placeholder={L('Введіть ідентифікатор…', 'Enter identifier…')}
          className="flex-1 min-w-[220px] bg-app-surface border border-app rounded-lg px-3 py-2 text-sm" data-testid="timeline-input" />
        <button type="submit" className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#2E5D4F] text-white text-sm font-semibold hover:bg-[#274f43] transition" data-testid="timeline-search-btn">
          <Search className="w-4 h-4" /> {L('Знайти', 'Search')}
        </button>
      </form>

      <div className="rounded-2xl border border-app bg-app-surface p-5">
        {query ? (
          <ActivityTimeline
            userId={query.field === 'user_id' ? query.val : undefined}
            leadId={query.field === 'lead_id' ? query.val : undefined}
            visitorId={query.field === 'visitor_id' ? query.val : undefined}
            limit={300}
          />
        ) : (
          <div className="py-8 text-center text-sm text-token-muted">
            {L('Введіть ідентифікатор, щоб побачити повну стрічку активності.', 'Enter an identifier to see the full activity timeline.')}
          </div>
        )}
      </div>
    </div>
  );
}

function Loading() {
  return <div className="py-16 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
}
function Empty({ L }) {
  return <div className="py-8 text-center text-sm text-token-muted">{L('Немає даних за цей період', 'No data for this period')}</div>;
}
