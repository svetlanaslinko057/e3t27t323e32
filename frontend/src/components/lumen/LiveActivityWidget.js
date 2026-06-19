/**
 * LiveActivityWidget — F2.5
 * "Who is on the site right now." Polls /api/admin/activity/live every 30s.
 * Used in the admin Site-Activity page and the manager dashboard.
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import { lumen } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import { Radio, Users, Eye, Loader2, Circle } from 'lucide-react';

const STAGE_COLOR = {
  visitor: 'text-slate-500',
  lead: 'text-sky-600',
  meeting: 'text-indigo-600',
  kyc_started: 'text-amber-600',
  kyc_completed: 'text-amber-700',
  contract_opened: 'text-violet-600',
  contract_signed: 'text-violet-800',
  funding_started: 'text-emerald-600',
  funding_confirmed: 'text-emerald-800',
  certificate: 'text-[#2E5D4F]',
};

export default function LiveActivityWidget({ compact = false, pollMs = 30000 }) {
  const { bi, lang } = useLang();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const timer = useRef(null);

  const load = useCallback(async () => {
    try {
      const r = await lumen.get('/admin/activity/live');
      setData(r.data);
    } catch (_) { /* keep last */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    load();
    timer.current = setInterval(load, pollMs);
    return () => timer.current && clearInterval(timer.current);
  }, [load, pollMs]);

  const sessions = data?.sessions || [];

  return (
    <div className="rounded-2xl border border-app bg-app-surface overflow-hidden" data-testid="live-activity-widget">
      <div className="px-5 py-4 flex items-center justify-between border-b border-app">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
          </span>
          <h3 className="font-semibold text-token-primary flex items-center gap-2">
            <Radio className="w-4 h-4" /> {bi('Зараз на сайті', 'Live on site')}
          </h3>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="font-bold text-token-primary tabular-nums" data-testid="live-online-count">{data?.online_count ?? 0}</span>
          <span className="text-token-muted text-xs">{bi('онлайн', 'online')}</span>
        </div>
      </div>

      {loading && !data ? (
        <div className="py-8 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
      ) : sessions.length === 0 ? (
        <div className="py-8 text-center text-sm text-muted-foreground" data-testid="live-empty">
          {bi('Зараз нікого немає на сайті', 'Nobody on site right now')}
        </div>
      ) : (
        <ul className="divide-y divide-app max-h-[420px] overflow-y-auto">
          {sessions.slice(0, compact ? 6 : 100).map((s, i) => {
            const stageLabel = s.stage_label && (lang === 'en' ? s.stage_label.en : s.stage_label.uk);
            return (
              <li key={s.session_id || i} className="px-5 py-3 flex items-center gap-3" data-testid="live-session-row">
                <Circle className={`w-2.5 h-2.5 fill-current ${STAGE_COLOR[s.stage] || 'text-slate-400'}`} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-token-primary truncate flex items-center gap-2">
                    {s.identity}
                    {s.is_anonymous && (
                      <span className="text-[10px] uppercase tracking-wide text-token-muted bg-app-elevated px-1.5 py-0.5 rounded">anon</span>
                    )}
                  </div>
                  <div className="text-[11px] text-token-muted truncate flex items-center gap-1">
                    <Eye className="w-3 h-3" /> {s.last_path || s.last_event}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  {stageLabel && <div className={`text-[11px] font-medium ${STAGE_COLOR[s.stage] || 'text-token-muted'}`}>{stageLabel}</div>}
                  <div className="text-[10px] text-token-muted tabular-nums">{s.events} {bi('подій', 'events')}</div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
