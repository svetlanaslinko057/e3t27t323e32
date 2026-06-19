/**
 * ActivityTimeline — F2.3
 * Per-identity unified activity feed (page views, CTAs, asset/fund views,
 * KYC/contract/funding/certificate milestones). Resolves linked
 * visitor_id ↔ lead_id ↔ user_id server-side. Reusable in the admin
 * Site-Activity page and embedded in the Investor-Relations card.
 */
import { useEffect, useState, useCallback } from 'react';
import { lumen } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import {
  Activity, Eye, MousePointerClick, Building2, Landmark, UserPlus,
  CalendarClock, ShieldCheck, FileText, FileSignature, Wallet, Award,
  Loader2, RefreshCw,
} from 'lucide-react';

const EVENT_ICON = {
  page_view: Eye,
  session_start: Activity,
  session_end: Activity,
  cta_click: MousePointerClick,
  asset_view: Building2,
  fund_view: Landmark,
  lead_created: UserPlus,
  meeting_scheduled: CalendarClock,
  kyc_started: ShieldCheck,
  kyc_completed: ShieldCheck,
  contract_opened: FileText,
  contract_signed: FileSignature,
  funding_started: Wallet,
  funding_confirmed: Wallet,
  certificate_viewed: Award,
  certificate_downloaded: Award,
};

const STAGE_DOT = {
  visitor: 'bg-slate-400',
  lead: 'bg-sky-500',
  meeting: 'bg-indigo-500',
  kyc_started: 'bg-amber-500',
  kyc_completed: 'bg-amber-600',
  contract_opened: 'bg-violet-500',
  contract_signed: 'bg-violet-700',
  funding_started: 'bg-emerald-500',
  funding_confirmed: 'bg-emerald-700',
  certificate: 'bg-[#2E5D4F]',
};

function fmtTime(iso, lang) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString(lang === 'en' ? 'en-GB' : 'uk-UA', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    });
  } catch (_) { return iso; }
}

export default function ActivityTimeline({ userId, leadId, visitorId, limit = 100, compact = false }) {
  const { bi, lang } = useLang();
  const [events, setEvents] = useState([]);
  const [identity, setIdentity] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!userId && !leadId && !visitorId) { setLoading(false); return; }
    setLoading(true); setError('');
    try {
      const params = { limit };
      if (userId) params.user_id = userId;
      if (leadId) params.lead_id = leadId;
      if (visitorId) params.visitor_id = visitorId;
      const r = await lumen.get('/admin/activity/timeline', { params });
      setEvents(r.data?.events || []);
      setIdentity(r.data?.identity || null);
    } catch (e) {
      setError(bi('Не вдалось завантажити активність', 'Failed to load activity'));
    } finally { setLoading(false); }
  }, [userId, leadId, visitorId, limit, bi]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return <div className="py-8 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>;
  }
  if (error) {
    return <div className="py-4 text-sm text-rose-600">{error}</div>;
  }
  if (!events.length) {
    return (
      <div className="py-6 text-center text-sm text-muted-foreground" data-testid="activity-timeline-empty">
        {bi('Подій активності ще немає', 'No activity events yet')}
      </div>
    );
  }

  return (
    <div data-testid="activity-timeline">
      {!compact && identity && (
        <div className="mb-3 flex items-center justify-between">
          <div className="text-[11px] text-token-muted">
            {bi('Перший візит', 'First visit')}: <span className="font-medium text-token-secondary">{fmtTime(identity.first_visit_at, lang) || '—'}</span>
            {identity.visitor_ids?.length > 1 && (
              <span className="ml-2">· {identity.visitor_ids.length} {bi('пристроїв', 'devices')}</span>
            )}
          </div>
          <button onClick={load} className="text-token-muted hover:text-token-primary transition" title="Refresh" data-testid="activity-timeline-refresh">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
      <ol className="relative border-l border-app ml-2">
        {events.map((e, i) => {
          const Icon = EVENT_ICON[e.event] || Activity;
          const dot = STAGE_DOT[e.stage] || 'bg-slate-400';
          const label = (e.label && (lang === 'en' ? e.label.en : e.label.uk)) || e.event;
          return (
            <li key={i} className="ml-4 pb-4" data-testid={`activity-event-${e.event}`}>
              <span className={`absolute -left-[7px] w-3.5 h-3.5 rounded-full ${dot} ring-2 ring-app-surface`} />
              <div className="flex items-center gap-2">
                <Icon className="w-3.5 h-3.5 text-token-muted shrink-0" />
                <span className="text-sm font-medium text-token-primary">{label}</span>
                <span className="text-[11px] text-token-muted ml-auto whitespace-nowrap">{fmtTime(e.at, lang)}</span>
              </div>
              <div className="text-[11px] text-token-muted mt-0.5 ml-5 truncate">
                {e.path || e.asset_id || e.surface || ''}
                {e.props && e.props.label ? ` · ${e.props.label}` : ''}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
