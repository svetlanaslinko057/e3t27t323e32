/**
 * AdminLegalSettings — comprehensive editor for footer socials, legal docs and
 * cookie-consent overview. Uses platform design tokens (bg-app, border-app,
 * text-token-*) → adapts automatically to light/dark themes.
 *
 * Layout:
 *   • Page header (sticky-feeling): title + subtitle + actions
 *   • Section 1 — Social links (6 platforms, toggle + URL + live preview)
 *   • Section 2 — Legal documents (tabs: terms/privacy/cookies; title + body
 *                 editor with word/char counter, last-updated, reset button)
 *   • Section 3 — Cookie consent stats (total + breakdown by choice + bars)
 *
 * Backed by:
 *   GET  /api/admin/legal-settings
 *   PUT  /api/admin/legal-settings
 *   GET  /api/admin/cookie-consents/stats
 *   GET  /api/public/legal-document/:kind  (for "Reset to current public copy")
 */
import { useEffect, useState, useMemo, useCallback } from 'react';
import { useLang } from '../contexts/LanguageContext';
import {
  Scale, Share2, FileText, Cookie, Save, RotateCcw, AlertCircle, CheckCircle2,
  Link as LinkIcon, ExternalLink, History,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/components/Toast';

const SOCIALS = [
  { key: 'telegram',  label: 'Telegram',  hint: 'Public channel or bot',     placeholder: 'https://t.me/yourchannel',         brand: '#229ED9' },
  { key: 'tiktok',    label: 'TikTok',    hint: 'Profile handle',            placeholder: 'https://tiktok.com/@you',          brand: '#FE2C55' },
  { key: 'instagram', label: 'Instagram', hint: 'Profile or business page',  placeholder: 'https://instagram.com/you',        brand: '#E1306C' },
  { key: 'youtube',   label: 'YouTube',   hint: 'Channel URL',               placeholder: 'https://youtube.com/@you',         brand: '#FF0000' },
  { key: 'facebook',  label: 'Facebook',  hint: 'Page or profile',           placeholder: 'https://facebook.com/you',         brand: '#1877F2' },
  { key: 'github',    label: 'GitHub',    hint: 'Org or user',               placeholder: 'https://github.com/you',           brand: '#7c8a99' },
];

const DOCS = [
  { key: 'terms',   label: 'Terms of Use',   icon: FileText, hint: 'Rules of the platform — what users agree to.' },
  { key: 'privacy', label: 'Privacy Policy', icon: Scale,    hint: 'How user data is collected, stored, and used.' },
  { key: 'cookies', label: 'Cookies Policy', icon: Cookie,   hint: 'Categories of cookies used and consent options.' },
];

const CHOICE_LABELS = { all: 'Accepted all', essential: 'Essential only', rejected: 'Rejected' };
// Static class strings so Tailwind JIT picks them up at build time.
const CHOICE_STYLES = {
  all:       { pct: 'text-emerald-400', bar: 'bg-emerald-500' },
  essential: { pct: 'text-amber-400',   bar: 'bg-amber-500'   },
  rejected:  { pct: 'text-rose-400',    bar: 'bg-rose-500'    },
};

function isValidUrl(s) {
  if (!s) return true; // empty allowed when disabled
  try { const u = new URL(s); return u.protocol === 'http:' || u.protocol === 'https:'; }
  catch { return false; }
}

export default function AdminLegalSettings() {
  const { tByEn } = useLang();
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeDoc, setActiveDoc] = useState('terms');
  const [dirty, setDirty] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, st] = await Promise.all([
        api.get('/admin/legal-settings'),
        api.get('/admin/cookie-consents/stats').catch(() => null),
      ]);
      setData(s);
      setStats(st);
      setDirty(false);
    } catch {
      toast.error('Failed to load legal settings');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  function patchSocial(key, field, value) {
    setDirty(true);
    setData((prev) => ({
      ...prev,
      socials: { ...prev.socials, [key]: { ...prev.socials[key], [field]: value } },
    }));
  }
  function patchDoc(kind, field, value) {
    setDirty(true);
    setData((prev) => ({
      ...prev,
      legal: { ...prev.legal, [kind]: { ...prev.legal[kind], [field]: value } },
    }));
  }

  async function save() {
    if (!data) return;
    // Pre-validate URLs
    const bad = SOCIALS.filter((s) => {
      const v = data.socials?.[s.key];
      return v?.enabled && v?.url && !isValidUrl(v.url);
    });
    if (bad.length) {
      toast.error(`Invalid URL: ${bad.map((b) => b.label).join(', ')}`);
      return;
    }
    setSaving(true);
    try {
      const next = await api.put('/admin/legal-settings', {
        socials: data.socials,
        legal: data.legal,
      });
      setData(next);
      setDirty(false);
      toast.success('Saved');
    } catch {
      toast.error('Save failed');
    } finally {
      setSaving(false);
    }
  }

  const completionByChoice = useMemo(() => {
    if (!stats || !stats.total) return null;
    return ['all', 'essential', 'rejected'].map((k) => ({
      key: k,
      count: stats.by_choice?.[k] || 0,
      pct: stats.total ? Math.round(((stats.by_choice?.[k] || 0) / stats.total) * 100) : 0,
    }));
  }, [stats]);

  if (loading || !data) {
    return (
      <div className="px-[50px] py-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 w-64 bg-app-elevated rounded" />
          <div className="h-4 w-96 bg-app-elevated rounded" />
          <div className="h-64 bg-app-elevated rounded-2xl mt-8" />
          <div className="h-64 bg-app-elevated rounded-2xl" />
        </div>
      </div>
    );
  }

  const enabledCount = SOCIALS.filter((s) => data.socials?.[s.key]?.enabled && data.socials?.[s.key]?.url).length;
  const activeDocBody = data.legal?.[activeDoc]?.body || '';
  const activeDocTitle = data.legal?.[activeDoc]?.title || '';
  const activeDocUpdated = data.legal?.[activeDoc]?.updated_at;
  const wordCount = activeDocBody.trim() ? activeDocBody.trim().split(/\s+/).length : 0;
  const charCount = activeDocBody.length;

  return (
    <div className="px-[50px] py-8 pb-20" data-testid="admin-legal-settings">
      {/* Header */}
      <div className="flex items-start justify-between gap-6 mb-6 flex-wrap">
        <div className="min-w-0">
          <h1 className="text-h1 mb-1">{tByEn('Legal &amp; social')}</h1>
          <p className="text-small-token max-w-2xl">
            Footer socials, legal documents and cookie consent. Changes take effect
            instantly across the public site and mobile app.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {dirty ? (
            <span className="inline-flex items-center gap-1.5 text-xs text-amber-500 font-medium">
              <AlertCircle className="w-3.5 h-3.5" />
              {tByEn('Unsaved changes')}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-xs text-token-muted font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" />
              {tByEn('All changes saved')}
            </span>
          )}
          <button
            type="button"
            onClick={() => load()}
            disabled={saving}
            className="px-4 py-2.5 rounded-xl border border-app text-sm font-semibold text-token-secondary hover:text-token-primary hover:border-app-strong transition-colors disabled:opacity-50"
            data-testid="legal-reload"
          >
            {tByEn('Reload')}
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving || !dirty}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white text-sm font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            data-testid="legal-save"
          >
            <Save className="w-4 h-4" />
            {saving ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </div>

      {/* === Section 1: Social links === */}
      <section className="rounded-2xl border border-app bg-app-surface mb-6 overflow-hidden">
        <header className="px-6 py-5 border-b border-app flex items-center gap-3">
          <Share2 className="w-5 h-5 text-emerald-400" />
          <div className="flex-1">
            <h2 className="text-h3">{tByEn('Footer social links')}</h2>
            <p className="text-small-token mt-0.5">
              Enabled platforms with a URL appear in the footer. {enabledCount} of {SOCIALS.length} active.
            </p>
          </div>
        </header>
        <div className="p-6 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {SOCIALS.map((s) => {
            const v = data.socials?.[s.key] || { url: '', enabled: false };
            const urlValid = isValidUrl(v.url);
            const showError = v.enabled && v.url && !urlValid;
            return (
              <div
                key={s.key}
                data-testid={`legal-social-${s.key}`}
                className={`rounded-xl border p-4 transition-colors ${
                  v.enabled ? 'border-emerald-500/40 bg-emerald-500/[0.04]' : 'border-app bg-app-elevated'
                }`}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2.5">
                    <span
                      className="w-2.5 h-2.5 rounded-full"
                      style={{ background: v.enabled ? s.brand : '#475569' }}
                      aria-hidden
                    />
                    <div>
                      <div className="text-sm font-semibold text-token-primary">{s.label}</div>
                      <div className="text-[11px] text-token-muted">{s.hint}</div>
                    </div>
                  </div>
                  <label className="relative inline-flex cursor-pointer items-center">
                    <input
                      type="checkbox"
                      className="sr-only peer"
                      checked={!!v.enabled}
                      onChange={(e) => patchSocial(s.key, 'enabled', e.target.checked)}
                      data-testid={`legal-social-${s.key}-toggle`}
                    />
                    <div className="w-9 h-5 bg-app-elevated border border-app peer-checked:border-emerald-500 peer-checked:bg-emerald-500 rounded-full transition-all
                                    after:content-[''] after:absolute after:top-[2px] after:left-[2px]
                                    after:bg-white after:rounded-full after:w-4 after:h-4 after:transition-all
                                    peer-checked:after:translate-x-4" />
                  </label>
                </div>
                <div className="relative">
                  <LinkIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-token-muted pointer-events-none" />
                  <input
                    type="url"
                    value={v.url || ''}
                    placeholder={s.placeholder}
                    onChange={(e) => patchSocial(s.key, 'url', e.target.value)}
                    data-testid={`legal-social-${s.key}-url`}
                    className={`w-full pl-9 pr-9 py-2 rounded-lg bg-app border text-sm text-token-primary placeholder:text-token-muted outline-none transition-colors ${
                      showError ? 'border-rose-500' : 'border-app focus:border-app-strong'
                    }`}
                  />
                  {v.url && urlValid ? (
                    <a
                      href={v.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={tByEn('Open in new tab')}
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-token-muted hover:text-emerald-400 transition-colors"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  ) : null}
                </div>
                {showError ? (
                  <p className="text-[11px] text-rose-500 mt-1.5 flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" />
                    URL must start with http:// or https://
                  </p>
                ) : null}
              </div>
            );
          })}
        </div>
      </section>

      {/* === Section 2: Legal documents === */}
      <section className="rounded-2xl border border-app bg-app-surface mb-6 overflow-hidden">
        <header className="px-6 py-5 border-b border-app flex items-center gap-3">
          <FileText className="w-5 h-5 text-emerald-400" />
          <div className="flex-1">
            <h2 className="text-h3">{tByEn('Legal documents')}</h2>
            <p className="text-small-token mt-0.5">
              Plain-text editor. Line breaks are preserved. Both the public web footer and the cookie banner pull these on every page load.
            </p>
          </div>
        </header>

        {/* Tabs */}
        <div className="px-6 pt-4 flex flex-wrap gap-2 border-b border-app">
          {DOCS.map((d) => {
            const Icon = d.icon;
            const active = activeDoc === d.key;
            return (
              <button
                key={d.key}
                type="button"
                onClick={() => setActiveDoc(d.key)}
                data-testid={`legal-doc-tab-${d.key}`}
                className={`inline-flex items-center gap-2 px-4 py-2.5 -mb-px text-sm font-semibold rounded-t-lg border-b-2 transition-colors ${
                  active
                    ? 'border-emerald-500 text-token-primary bg-app-elevated'
                    : 'border-transparent text-token-secondary hover:text-token-primary'
                }`}
              >
                <Icon className="w-4 h-4" />
                {d.label}
              </button>
            );
          })}
        </div>

        {/* Editor */}
        <div className="p-6">
          <p className="text-small-token mb-5">
            {DOCS.find((d) => d.key === activeDoc)?.hint}
          </p>

          <label className="block text-[11px] uppercase tracking-wider font-bold text-token-muted mb-1.5">{tByEn('Title')}</label>
          <input
            type="text"
            value={activeDocTitle}
            onChange={(e) => patchDoc(activeDoc, 'title', e.target.value)}
            data-testid={`legal-doc-${activeDoc}-title`}
            className="w-full px-3.5 py-2.5 rounded-xl bg-app-elevated border border-app text-sm text-token-primary outline-none focus:border-app-strong transition-colors mb-5"
            placeholder={DOCS.find((d) => d.key === activeDoc)?.label}
          />

          <div className="flex items-center justify-between mb-1.5">
            <label className="text-[11px] uppercase tracking-wider font-bold text-token-muted">{tByEn('Body')}</label>
            <div className="text-[11px] text-token-muted tabular-nums">
              {wordCount} words · {charCount} chars
            </div>
          </div>
          <textarea
            rows={16}
            value={activeDocBody}
            onChange={(e) => patchDoc(activeDoc, 'body', e.target.value)}
            data-testid={`legal-doc-${activeDoc}-body`}
            className="w-full px-4 py-3 rounded-xl bg-app-elevated border border-app text-sm text-token-primary leading-relaxed outline-none focus:border-app-strong transition-colors resize-y font-mono"
            placeholder={`Write the full ${DOCS.find((d) => d.key === activeDoc)?.label.toLowerCase()} here. Line breaks are preserved.`}
            style={{ minHeight: 320 }}
          />

          <div className="flex items-center justify-between mt-3 flex-wrap gap-2">
            <div className="text-[11px] text-token-muted flex items-center gap-1.5">
              <History className="w-3.5 h-3.5" />
              {activeDocUpdated
                ? <>Last updated · {new Date(activeDocUpdated).toLocaleString()}</>
                : 'Never updated'}
            </div>
            <button
              type="button"
              onClick={() => {
                if (!confirm(`Reset ${DOCS.find((d) => d.key === activeDoc)?.label} to last saved server copy?`)) return;
                load();
              }}
              className="inline-flex items-center gap-1.5 text-[11px] text-token-secondary hover:text-rose-400 transition-colors"
              data-testid={`legal-doc-${activeDoc}-reset`}
            >
              <RotateCcw className="w-3.5 h-3.5" />
              {tByEn('Reset to server copy')}
            </button>
          </div>
        </div>
      </section>

      {/* === Section 3: Cookie consent stats === */}
      <section className="rounded-2xl border border-app bg-app-surface overflow-hidden">
        <header className="px-6 py-5 border-b border-app flex items-center gap-3">
          <Cookie className="w-5 h-5 text-emerald-400" />
          <div className="flex-1">
            <h2 className="text-h3">{tByEn('Cookie consent overview')}</h2>
            <p className="text-small-token mt-0.5">
              Anonymous summary of choices users made in the cookie banner. Updates with every accept/reject.
            </p>
          </div>
        </header>
        <div className="p-6">
          {!stats || !stats.total ? (
            <div className="text-center py-10">
              <Cookie className="w-10 h-10 text-token-muted mx-auto mb-2 opacity-50" />
              <p className="text-small-token">{tByEn('No consent responses recorded yet.')}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Total */}
              <div className="rounded-xl border border-app bg-app-elevated p-5">
                <div className="text-[11px] uppercase tracking-wider font-bold text-token-muted">{tByEn('Total responses')}</div>
                <div className="text-3xl font-bold text-token-primary mt-2 tabular-nums">{stats.total}</div>
                <div className="text-[11px] text-token-muted mt-1">
                  Computed {stats.computed_at ? new Date(stats.computed_at).toLocaleTimeString() : '—'}
                </div>
              </div>
              {/* By choice */}
              {completionByChoice?.map((c) => (
                <div
                  key={c.key}
                  data-testid={`legal-stat-${c.key}`}
                  className="rounded-xl border border-app bg-app-elevated p-5"
                >
                  <div className="text-[11px] uppercase tracking-wider font-bold text-token-muted">
                    {CHOICE_LABELS[c.key]}
                  </div>
                  <div className="flex items-baseline gap-2 mt-2">
                    <span className="text-3xl font-bold text-token-primary tabular-nums">{c.count}</span>
                    <span className={`text-sm font-semibold tabular-nums ${CHOICE_STYLES[c.key].pct}`}>{c.pct}%</span>
                  </div>
                  <div className="h-1.5 bg-app rounded-full overflow-hidden mt-3">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${CHOICE_STYLES[c.key].bar}`}
                      style={{ width: `${c.pct}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
