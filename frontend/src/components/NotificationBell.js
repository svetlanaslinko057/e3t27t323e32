import { useState, useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useAuth, API } from '@/App';
import axios from 'axios';
import { useLang } from '@/contexts/LanguageContext';
import {
  Bell, Check, CheckCheck, DollarSign, TrendingUp, UserPlus,
  Target, Award, Zap, Star, Crown, Shield, X
} from 'lucide-react';

const ICON_MAP = {
  referral_earned: DollarSign,
  tier_up: TrendingUp,
  dev_joined: UserPlus,
  task_assigned: Target,
  achievement_unlocked: Award,
  payment_received: DollarSign,
  deliverable_ready: Zap,
};

const COLOR_MAP = {
  referral_earned: 'text-emerald-400 bg-emerald-500/10',
  tier_up: 'text-amber-400 bg-amber-500/10',
  dev_joined: 'text-signal bg-signal/10',
  task_assigned: 'text-signal bg-signal/10',
  achievement_unlocked: 'text-signal bg-signal/10',
  payment_received: 'text-emerald-400 bg-emerald-500/10',
  deliverable_ready: 'text-orange-400 bg-orange-500/10',
};

const NotificationBell = () => {
  const { tByEn } = useLang();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [anchorRect, setAnchorRect] = useState(null);
  const panelRef = useRef(null);
  const btnRef = useRef(null);

  const fetchUnreadCount = useCallback(async () => {
    if (!user) return;
    try {
      const res = await axios.get(`${API}/notifications/unread-count`, { withCredentials: true });
      setUnreadCount(res.data.count || 0);
    } catch (err) { /* ignore */ }
  }, [user]);

  const fetchNotifications = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      const res = await axios.get(`${API}/notifications`, { withCredentials: true });
      setNotifications(res.data || []);
    } catch (err) { /* ignore */ }
    setLoading(false);
  }, [user]);

  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 15000);
    return () => clearInterval(interval);
  }, [fetchUnreadCount]);

  useEffect(() => {
    if (open) fetchNotifications();
  }, [open, fetchNotifications]);

  // Click outside to close — checks both the bell button and the portaled panel.
  useEffect(() => {
    const handleClick = (e) => {
      const inPanel = panelRef.current && panelRef.current.contains(e.target);
      const inBtn = btnRef.current && btnRef.current.contains(e.target);
      if (!inPanel && !inBtn) setOpen(false);
    };
    if (open) document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  // Recompute panel position when opening, on scroll, and on resize.
  // Panel is rendered via Portal into `document.body` with `position: fixed`,
  // anchored to the bell's bounding rect, so it escapes any sidebar
  // stacking-context / overflow that was clipping it. Always on the top layer.
  useEffect(() => {
    if (!open) return;
    const update = () => {
      if (btnRef.current) setAnchorRect(btnRef.current.getBoundingClientRect());
    };
    update();
    window.addEventListener('scroll', update, true);
    window.addEventListener('resize', update);
    return () => {
      window.removeEventListener('scroll', update, true);
      window.removeEventListener('resize', update);
    };
  }, [open]);

  const markRead = async (id) => {
    await axios.post(`${API}/notifications/${id}/read`, {}, { withCredentials: true });
    setNotifications(prev => prev.map(n => n.notification_id === id ? { ...n, is_read: true } : n));
    setUnreadCount(prev => Math.max(0, prev - 1));
  };

  const markAllRead = async () => {
    await axios.post(`${API}/notifications/read-all`, {}, { withCredentials: true });
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
    setUnreadCount(0);
  };

  const timeAgo = (dateStr) => {
    if (!dateStr) return '';
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'now';
    if (mins < 60) return `${mins}m`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h`;
    return `${Math.floor(hrs / 24)}d`;
  };

  // Panel position: fixed-positioned in portal, anchored to bell's left edge
  // and top edge below the bell. Width clamps to viewport. If the bell sits
  // near the right edge (shouldn't, but safe), the panel shifts left to fit.
  const PANEL_WIDTH = 380;
  const GAP = 8;
  let panelLeft = 0;
  let panelTop = 0;
  if (anchorRect) {
    panelLeft = Math.max(16, anchorRect.left);
    // If panel would overflow right edge, push it back inside viewport
    if (panelLeft + PANEL_WIDTH > window.innerWidth - 16) {
      panelLeft = Math.max(16, window.innerWidth - PANEL_WIDTH - 16);
    }
    panelTop = anchorRect.bottom + GAP;
  }

  return (
    <>
      <div className="relative" data-testid="notification-bell-wrapper">
        <button
          ref={btnRef}
          onClick={() => setOpen(!open)}
          className="relative p-2 rounded-xl hover:bg-muted transition-colors text-muted-foreground hover:text-white"
          data-testid="notification-bell-btn"
        >
          <Bell className="w-5 h-5" />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-red-500 text-white text-[10px] font-bold px-1 animate-pulse" data-testid="notification-badge">
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </button>
      </div>

      {open && anchorRect && typeof document !== 'undefined' && createPortal(
        <div
          ref={panelRef}
          style={{
            position: 'fixed',
            top: panelTop,
            left: panelLeft,
            width: PANEL_WIDTH,
            maxWidth: 'calc(100vw - 32px)',
            maxHeight: 'min(480px, calc(100vh - 100px))',
            zIndex: 9999,
            background: 'var(--token-surface-elevated)',
            border: '1px solid var(--token-border)',
            boxShadow: '0 24px 48px -12px rgba(0,0,0,0.55), 0 0 0 1px var(--token-border)',
          }}
          className="rounded-2xl overflow-hidden flex flex-col"
          data-testid="notification-panel"
        >
          {/* Header */}
          <div
            className="flex items-center justify-between px-4 py-3"
            style={{ borderBottom: '1px solid var(--token-border)' }}
          >
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-token-primary">{tByEn('Notifications')}</span>
              {unreadCount > 0 && (
                <span
                  className="px-1.5 py-0.5 text-[10px] font-bold rounded-full"
                  style={{ background: 'var(--token-success-tint)', color: 'var(--token-primary)' }}
                >
                  {unreadCount}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1">
              {unreadCount > 0 && (
                <button
                  onClick={markAllRead}
                  className="flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] text-token-muted hover:text-token-primary transition-colors"
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--token-border)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
                  data-testid="mark-all-read-btn"
                >
                  <CheckCheck className="w-3.5 h-3.5" /> Read all
                </button>
              )}
              <button
                onClick={() => setOpen(false)}
                className="p-1 rounded-lg text-token-muted hover:text-token-primary"
                onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--token-border)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
                aria-label={tByEn('Close notifications')}
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* List */}
          <div className="overflow-y-auto" style={{ maxHeight: 400 }} data-testid="notification-list">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <div
                  className="w-5 h-5 rounded-full animate-spin"
                  style={{ border: '2px solid var(--token-border)', borderTopColor: 'var(--token-primary)' }}
                />
              </div>
            ) : notifications.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-token-muted">
                <Bell className="w-8 h-8 mb-2 opacity-40" />
                <span className="text-sm">{tByEn('No notifications yet')}</span>
                <span className="text-[11px] mt-1 opacity-70">{tByEn('We\'ll ping you when something happens.')}</span>
              </div>
            ) : (
              notifications.map((n) => {
                const Icon = ICON_MAP[n.type] || Bell;
                const colors = COLOR_MAP[n.type] || 'text-token-muted';
                return (
                  <div
                    key={n.notification_id}
                    onClick={() => !n.is_read && markRead(n.notification_id)}
                    className="flex items-start gap-3 px-4 py-3 cursor-pointer transition-colors"
                    style={{
                      borderBottom: '1px solid var(--token-border)',
                      background: !n.is_read ? 'var(--token-surface)' : 'transparent',
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--token-border)'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = !n.is_read ? 'var(--token-surface)' : 'transparent'; }}
                    data-testid={`notification-item-${n.notification_id}`}
                  >
                    <div
                      className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5 ${colors}`}
                      style={{ background: 'var(--token-surface)', border: '1px solid var(--token-border)' }}
                    >
                      <Icon className="w-4 h-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={`text-sm font-medium truncate ${!n.is_read ? 'text-token-primary' : 'text-token-secondary'}`}>{n.title}</span>
                        {!n.is_read && (
                          <span
                            className="w-1.5 h-1.5 rounded-full shrink-0"
                            style={{ background: 'var(--token-primary)' }}
                          />
                        )}
                      </div>
                      <p className="text-xs text-token-muted mt-0.5 line-clamp-2">{n.message}</p>
                    </div>
                    <span className="text-[10px] text-token-muted shrink-0 mt-1">{timeAgo(n.created_at)}</span>
                  </div>
                );
              })
            )}
          </div>
        </div>,
        document.body
      )}
    </>
  );
};

export default NotificationBell;
