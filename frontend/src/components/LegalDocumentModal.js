/**
 * LegalDocumentModal — fetches /api/public/legal-document/{kind} and renders
 * a clean readable modal. Adapts to dark/light tone of the caller.
 */
import { useEffect, useState } from 'react';
import { useLegalSettings } from '@/contexts/LegalSettingsContext';
import { useLang } from '@/contexts/LanguageContext';

export default function LegalDocumentModal({ kind, onClose, tone = 'dark' }) {
  const { tByEn } = useLang();
  const { fetchDocument } = useLegalSettings();
  const [doc, setDoc] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchDocument(kind).then((d) => { if (active) { setDoc(d); setLoading(false); }});
    return () => { active = false; };
  }, [kind, fetchDocument]);

  const isLight = tone === 'light';
  const bg = isLight ? '#ffffff' : '#0b0f17';
  const bd = isLight ? '#e2e8f0' : '#1e293b';
  const tx = isLight ? '#0f172a' : '#e2e8f0';
  const sub = isLight ? '#64748b' : '#94a3b8';

  return (
    <div
      role="dialog"
      aria-modal="true"
      data-testid={`legal-modal-${kind}`}
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(0,0,0,0.65)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          maxWidth: 720, width: '100%', maxHeight: '88vh', overflow: 'auto',
          background: bg, color: tx, border: `1px solid ${bd}`,
          borderRadius: 14, padding: '28px 28px 24px',
          boxShadow: '0 30px 60px rgba(0,0,0,0.5)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, marginBottom: 16 }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800 }}>{doc?.title || (loading ? 'Loading…' : 'Document')}</h2>
            {doc?.updated_at ? (
              <p style={{ color: sub, fontSize: 12, marginTop: 6 }}>
                Last updated · {new Date(doc.updated_at).toLocaleDateString()}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            data-testid="legal-modal-close"
            aria-label={tByEn('Close')}
            style={{
              background: 'transparent', border: `1px solid ${bd}`, color: tx,
              borderRadius: 8, padding: '6px 12px', cursor: 'pointer',
              fontSize: 14, fontWeight: 600,
            }}
          >
            ✕
          </button>
        </div>

        {loading ? (
          <p style={{ color: sub }}>Loading…</p>
        ) : !doc ? (
          <p style={{ color: sub }}>{tByEn('Failed to load this document. Please try again later.')}</p>
        ) : (
          <div
            style={{ fontSize: 14, lineHeight: 1.65, color: tx, whiteSpace: 'pre-wrap' }}
            data-testid="legal-modal-body"
          >
            {doc.body}
          </div>
        )}
      </div>
    </div>
  );
}
