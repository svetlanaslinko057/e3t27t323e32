/**
 * LUMEN — F2 Site Activity Tracker (client)
 * =========================================
 * Lightweight, dependency-free, fire-and-forget activity beacon.
 *
 * Responsibilities:
 *   • Persist a stable anonymous `visitor_id` (localStorage).
 *   • Maintain a `session_id` (sessionStorage) with 30-min idle reset.
 *   • Auto events: session_start, session_end, page_view, cta_click.
 *   • Business events: track(event, props) from any surface.
 *   • Identity stitching: identify({user_id, lead_id, manager_id}).
 *   • Batched delivery (queue → flush every 3s / 10 events), with
 *     navigator.sendBeacon on pagehide so we never lose session_end.
 *
 * The backend (`/api/activity/track`) is auth-free; cookies ride along
 * (credentials: include) so a logged-in user is attached server-side too.
 */

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

const VID_KEY = 'lumen_vid';
const SID_KEY = 'lumen_sid';
const SID_TS_KEY = 'lumen_sid_ts';
const SESSION_IDLE_MS = 30 * 60 * 1000; // 30 min
const FLUSH_INTERVAL_MS = 3000;
const FLUSH_AT = 10;

const KNOWN_EVENTS = new Set([
  'page_view', 'session_start', 'session_end', 'cta_click',
  'asset_view', 'fund_view', 'lead_created', 'meeting_scheduled',
  'kyc_started', 'kyc_completed', 'contract_opened', 'contract_signed',
  'funding_started', 'funding_confirmed', 'certificate_viewed', 'certificate_downloaded',
]);

function uuid() {
  try {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID().replace(/-/g, '').slice(0, 24);
  } catch (_) { /* noop */ }
  return 'x' + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function safeGet(storage, key) {
  try { return storage.getItem(key); } catch (_) { return null; }
}
function safeSet(storage, key, val) {
  try { storage.setItem(key, val); } catch (_) { /* noop */ }
}

function getVisitorId() {
  let vid = safeGet(localStorage, VID_KEY);
  if (!vid) {
    vid = 'vid_' + uuid();
    safeSet(localStorage, VID_KEY, vid);
  }
  return vid;
}

function getSessionId() {
  const now = Date.now();
  const last = parseInt(safeGet(sessionStorage, SID_TS_KEY) || '0', 10);
  let sid = safeGet(sessionStorage, SID_KEY);
  if (!sid || (last && now - last > SESSION_IDLE_MS)) {
    sid = 'sess_' + uuid();
    safeSet(sessionStorage, SID_KEY, sid);
  }
  safeSet(sessionStorage, SID_TS_KEY, String(now));
  return sid;
}

class ActivityTracker {
  constructor() {
    this.queue = [];
    this.timer = null;
    this.started = false;
    this.identity = { user_id: null, lead_id: null, manager_id: null };
    this.lastPath = null;
  }

  _device() {
    try { return window.innerWidth < 768 ? 'mobile' : 'desktop'; } catch (_) { return 'desktop'; }
  }

  init() {
    if (this.started) return;
    this.started = true;
    // restore identity hint (so events before checkAuth resolves still carry it)
    try {
      const cached = JSON.parse(localStorage.getItem('lumen_identity') || 'null');
      if (cached) this.identity = { ...this.identity, ...cached };
    } catch (_) { /* noop */ }

    this.track('session_start', { path: this._path() });

    // delivery on tab hide / unload (most reliable place for session_end)
    const onHide = () => {
      if (document.visibilityState === 'hidden') {
        this.track('session_end', { path: this._path() });
        this.flush(true);
      }
    };
    document.addEventListener('visibilitychange', onHide);
    window.addEventListener('pagehide', () => { this.track('session_end', {}); this.flush(true); });

    // delegated CTA capture: any element with [data-activity]
    document.addEventListener('click', (e) => {
      try {
        const el = e.target && e.target.closest ? e.target.closest('[data-activity]') : null;
        if (!el) return;
        const evName = el.getAttribute('data-activity') || 'cta_click';
        let props = {};
        const raw = el.getAttribute('data-activity-props');
        if (raw) { try { props = JSON.parse(raw); } catch (_) { props = { label: raw }; } }
        if (!props.label) props.label = (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 80);
        this.track(evName, { ...props, path: this._path() });
      } catch (_) { /* noop */ }
    }, true);

    this.timer = setInterval(() => this.flush(), FLUSH_INTERVAL_MS);
  }

  _path() {
    try { return window.location.pathname + window.location.search; } catch (_) { return '/'; }
  }

  setIdentity(partial) {
    if (!partial) return;
    const next = {
      user_id: partial.user_id || this.identity.user_id,
      lead_id: partial.lead_id || this.identity.lead_id,
      manager_id: partial.manager_id || this.identity.manager_id,
    };
    const changed = JSON.stringify(next) !== JSON.stringify(this.identity);
    this.identity = next;
    try { localStorage.setItem('lumen_identity', JSON.stringify(next)); } catch (_) { /* noop */ }
    if (changed && (next.user_id || next.lead_id)) this.identify();
  }

  /** Stitch the anonymous visitor to a real identity + back-fill prior events. */
  async identify(extra = {}) {
    const visitor_id = getVisitorId();
    const body = {
      visitor_id,
      user_id: extra.user_id || this.identity.user_id || null,
      lead_id: extra.lead_id || this.identity.lead_id || null,
      manager_id: extra.manager_id || this.identity.manager_id || null,
      investor_profile_id: extra.investor_profile_id || null,
    };
    if (!body.user_id && !body.lead_id) return;
    try {
      await fetch(`${API}/activity/identify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        keepalive: true,
        body: JSON.stringify(body),
      });
    } catch (_) { /* noop */ }
  }

  /** Record a page view (called on route change). De-dupes consecutive same-path. */
  page(path) {
    const p = path || this._path();
    if (p === this.lastPath) return;
    this.lastPath = p;
    getSessionId(); // refresh idle timer
    this.track('page_view', { path: p, referrer: document.referrer || null });
  }

  track(event, props = {}) {
    if (!event) return;
    const visitor_id = getVisitorId();
    const session_id = getSessionId();
    const ev = {
      event,
      surface: props.surface || 'web',
      visitor_id,
      session_id,
      user_id: this.identity.user_id || null,
      lead_id: this.identity.lead_id || null,
      manager_id: this.identity.manager_id || null,
      path: props.path || this._path(),
      referrer: props.referrer || null,
      device: this._device(),
      occurred_at: new Date().toISOString(),
      props: props || {},
    };
    this.queue.push(ev);
    if (this.queue.length >= FLUSH_AT) this.flush();
  }

  flush(useBeacon = false) {
    if (!this.queue.length) return;
    const events = this.queue.splice(0, this.queue.length);
    const payload = JSON.stringify({ events });
    const url = `${API}/activity/track`;
    try {
      if (useBeacon && navigator.sendBeacon) {
        const blob = new Blob([payload], { type: 'application/json' });
        navigator.sendBeacon(url, blob);
        return;
      }
    } catch (_) { /* fall through to fetch */ }
    try {
      fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        keepalive: true,
        body: payload,
      }).catch(() => { /* swallow */ });
    } catch (_) { /* noop */ }
  }
}

const tracker = new ActivityTracker();

// Convenience named exports
export const trackEvent = (event, props) => tracker.track(event, props);
export const trackPage = (path) => tracker.page(path);
export const identifyUser = (id) => tracker.setIdentity(id);
export const KNOWN_ACTIVITY_EVENTS = KNOWN_EVENTS;

export default tracker;
