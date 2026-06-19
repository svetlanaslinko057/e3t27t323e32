import { useState, useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { lumen } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import {
  Bell, CheckCheck, UserPlus, Clock, AlarmClock, CalendarClock, AlertTriangle, X,
} from 'lucide-react';

const ICONS = {
  new_lead_assigned: UserPlus,
  task_due_today: Clock,
  task_overdue: AlarmClock,
  meeting_in_1_hour: CalendarClock,
  sla_breach: AlertTriangle,
};
const COLORS = {
  new_lead_assigned: 'text-sky-600 bg-sky-100',
  task_due_today: 'text-amber-600 bg-amber-100',
  task_overdue: 'text-rose-600 bg-rose-100',
  meeting_in_1_hour: 'text-violet-600 bg-violet-100',
  sla_breach: 'text-rose-700 bg-rose-100',
};

/**
 * StaffNotificationBell — Manager OS (M4) in-app staff notifications.
 * Reads /api/staff/notifications (scoped to the logged-in staff user).
 */
export default function StaffNotificationBell() {
  const { bi } = useLang();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [rect, setRect] = useState(null);
  const btnRef = useRef(null);
  const panelRef = useRef(null);

  const loadCount = useCallback(async () => {
    try {
      const r = await lumen.get('/staff/notifications/unread-count');
      setUnread(r.data?.count || 0);
    } catch (_e) { /* ignore */ }
  }, []);

  const loadList = useCallback(async () => {
    try {
      const r = await lumen.get('/staff/notifications?limit=30');
      setItems(r.data?.notifications || []);
    } catch (_e) { /* ignore */ }
  }, []);

  useEffect(() => {
    loadCount();
    const t = setInterval(loadCount, 30000);
    return () => clearInterval(t);
  }, [loadCount]);

  useEffect(() => {
    if (open) {
      loadList();
      if (btnRef.current) setRect(btnRef.current.getBoundingClientRect());
    }
  }, [open, loadList]);

  useEffect(() => {
    const onClick = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)
        && btnRef.current && !btnRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  const markAll = async () => {
    try {
      await lumen.post('/staff/notifications/read-all');
      setUnread(0);
      setItems((prev) => prev.map((n) => ({ ...n, read: true })));
    } catch (_e) { /* ignore */ }
  };

  const markOne = async (id) => {
    try {
      await lumen.post(`/staff/notifications/${id}/read`);
      setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
      setUnread((u) => Math.max(0, u - 1));
    } catch (_e) { /* ignore */ }
  };

  return (
    <>
      <button
        ref={btnRef}
        onClick={() => setOpen((o) => !o)}
        data-testid="staff-bell-btn"
        className="relative p-1.5 rounded-lg text-token-muted hover:text-token-primary transition"
        title={bi('Сповіщення', 'Notifications')}
      >
        <Bell className="w-4 h-4" />
        {unread > 0 && (
          <span
            data-testid="staff-bell-badge"
            className="absolute -top-1 -right-1 min-w-[16px] h-4 px-1 rounded-full text-[10px] font-bold text-white flex items-center justify-center"
            style={{ background: '#E11D48' }}
          >
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && rect && createPortal(
        <div
          ref={panelRef}
          data-testid="staff-bell-panel"
          className="fixed z-[9999] w-[340px] max-h-[460px] overflow-hidden rounded-2xl shadow-2xl bg-card border border-border flex flex-col"
          style={{ top: rect.bottom + 8, left: Math.max(12, rect.left - 150) }}
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <span className="font-semibold text-sm text-token-primary">{bi('Сповіщення', 'Notifications')}</span>
            <div className="flex items-center gap-2">
              <button onClick={markAll} data-testid="staff-bell-readall" className="text-[11px] inline-flex items-center gap-1 text-token-muted hover:text-token-primary">
                <CheckCheck className="w-3.5 h-3.5" /> {bi('Прочитати все', 'Read all')}
              </button>
              <button onClick={() => setOpen(false)} className="text-token-muted hover:text-token-primary"><X className="w-4 h-4" /></button>
            </div>
          </div>
          <div className="overflow-y-auto flex-1">
            {items.length === 0 ? (
              <p className="p-6 text-center text-sm text-token-muted">{bi('Немає сповіщень', 'No notifications')}</p>
            ) : items.map((n) => {
              const Icon = ICONS[n.kind] || Bell;
              return (
                <button
                  key={n.id}
                  onClick={() => markOne(n.id)}
                  data-testid="staff-notif-item"
                  className={`w-full text-left flex items-start gap-3 px-4 py-3 border-b border-border hover:bg-muted/50 transition ${n.read ? 'opacity-60' : ''}`}
                >
                  <span className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${COLORS[n.kind] || 'text-slate-600 bg-slate-100'}`}>
                    <Icon className="w-4 h-4" />
                  </span>
                  <span className="flex-1 min-w-0">
                    <span className="block text-sm font-medium text-token-primary truncate">{n.title}</span>
                    <span className="block text-xs text-token-muted line-clamp-2">{n.body}</span>
                  </span>
                  {!n.read && <span className="w-2 h-2 rounded-full mt-1.5 shrink-0" style={{ background: 'var(--token-primary)' }} />}
                </button>
              );
            })}
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
