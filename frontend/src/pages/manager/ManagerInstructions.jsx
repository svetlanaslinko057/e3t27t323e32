/**
 * ManagerInstructions — F4 manager-facing reading + acknowledgement.
 * Managers browse published instructions by category, read them, and
 * acknowledge the current version. A "pending" badge shows unread/un-acked.
 */
import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError, formatDateUk } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import MarkdownLite from '@/components/MarkdownLite';
import {
  BookOpen, Loader2, CheckCircle2, Circle, Pin, ArrowLeft, ShieldCheck,
} from 'lucide-react';

const CATEGORY_LABEL = {
  onboarding: { uk: 'Як вести інвестора', en: 'Leading an investor' },
  kyc: { uk: 'KYC та верифікація', en: 'KYC & verification' },
  objections: { uk: 'Робота з запереченнями', en: 'Handling objections' },
  documents: { uk: 'Оформлення документів', en: 'Document preparation' },
  handoff: { uk: 'Передача лідів', en: 'Lead handoff' },
  general: { uk: 'Загальне', en: 'General' },
};

export default function ManagerInstructions() {
  const { bi, lang } = useLang();
  const [list, setList] = useState([]);
  const [pending, setPending] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [catF, setCatF] = useState('');
  const [open, setOpen] = useState(null);   // open doc detail
  const [acking, setAcking] = useState(false);

  const cat = (k) => (CATEGORY_LABEL[k] ? (lang === 'en' ? CATEGORY_LABEL[k].en : CATEGORY_LABEL[k].uk) : k);

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const r = await lumen.get(`/manager/instructions${catF ? `?category=${catF}` : ''}`);
      setList(r.data?.instructions || []);
      setPending(r.data?.pending_acks || 0);
    } catch (e) { setErr(lumenError(e)); }
    finally { setLoading(false); }
  }, [catF]);
  useEffect(() => { load(); }, [load]);

  const openDoc = async (d) => {
    try { const r = await lumen.get(`/manager/instructions/${d.instruction_id}`); setOpen(r.data); }
    catch (e) { alert(lumenError(e)); }
  };
  const ack = async () => {
    if (!open) return;
    setAcking(true);
    try { await lumen.post(`/manager/instructions/${open.instruction_id}/ack`, {}); setOpen((o) => ({ ...o, acknowledged: true })); await load(); }
    catch (e) { alert(lumenError(e)); }
    finally { setAcking(false); }
  };

  if (open) {
    return (
      <div className="max-w-3xl mx-auto p-6" data-testid="manager-instruction-detail">
        <button onClick={() => setOpen(null)} className="inline-flex items-center gap-1.5 text-sm text-token-muted hover:text-token-primary mb-4"><ArrowLeft className="w-4 h-4" /> {bi('До списку', 'Back to list')}</button>
        <div className="rounded-2xl border border-border bg-card p-6">
          <div className="flex items-center gap-2 text-[11px] text-token-muted mb-2">
            <span className="px-2 py-0.5 rounded bg-muted">{cat(open.category)}</span>
            <span>v{open.version}</span>
            <span>· {open.updated_at ? formatDateUk(open.updated_at) : ''}</span>
          </div>
          <h1 className="text-2xl font-bold mb-4">{open.title}</h1>
          <div className="prose-sm max-w-none text-token-primary"><MarkdownLite text={open.body} /></div>
          <div className="mt-6 pt-4 border-t border-border flex items-center justify-between">
            {open.acknowledged ? (
              <span className="inline-flex items-center gap-2 text-emerald-700 text-sm font-medium" data-testid="mi-acked"><CheckCircle2 className="w-4 h-4" /> {bi('Ви підтвердили цю версію', 'You acknowledged this version')}</span>
            ) : (
              <button onClick={ack} disabled={acking} data-testid="mi-ack-btn" className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#2E5D4F] text-white text-sm font-semibold hover:bg-[#274f43] disabled:opacity-60">
                {acking ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />} {bi('Підтверджую, що ознайомився', 'I acknowledge I have read this')}
              </button>
            )}
            <span className="text-[11px] text-token-muted">{open.ack_count} {bi('підтверджень', 'acknowledgements')}</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-5" data-testid="manager-instructions">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-token-muted flex items-center gap-2"><BookOpen className="w-3.5 h-3.5" /> {bi('Інструкції', 'Instructions')}</div>
        <h1 className="mt-2 text-2xl font-bold">{bi('Інструкції та регламенти', 'Instructions & playbooks')}</h1>
        {pending > 0 && (
          <p className="mt-2 inline-flex items-center gap-2 text-sm text-amber-700 bg-amber-500/10 px-3 py-1.5 rounded-lg" data-testid="mi-pending-badge">
            <Circle className="w-3 h-3 fill-current" /> {pending} {bi('не підтверджено — ознайомтесь', 'unacknowledged — please read')}
          </p>
        )}
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <button onClick={() => setCatF('')} className={`px-3 py-1.5 rounded-lg text-sm border ${!catF ? 'border-[#2E5D4F] text-token-primary font-medium' : 'border-border text-token-muted'}`}>{bi('Усі', 'All')}</button>
        {Object.keys(CATEGORY_LABEL).map((c) => (
          <button key={c} onClick={() => setCatF(c)} className={`px-3 py-1.5 rounded-lg text-sm border ${catF === c ? 'border-[#2E5D4F] text-token-primary font-medium' : 'border-border text-token-muted'}`} data-testid={`mi-cat-${c}`}>{cat(c)}</button>
        ))}
      </div>

      {err && <p className="text-sm text-rose-600">{err}</p>}
      {loading && !list.length ? <Loading /> : list.length === 0 ? (
        <p className="py-10 text-sm text-token-muted text-center">{bi('Інструкцій ще немає.', 'No instructions yet.')}</p>
      ) : (
        <div className="grid sm:grid-cols-2 gap-3">
          {list.map((d) => (
            <button key={d.instruction_id} onClick={() => openDoc(d)} data-testid="mi-card"
              className="text-left rounded-2xl border border-border bg-card p-4 hover:border-[#2E5D4F]/40 transition">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 text-[11px] text-token-muted">
                  {d.pinned && <Pin className="w-3 h-3 text-[#2E5D4F]" />}
                  <span className="px-1.5 py-0.5 rounded bg-muted">{cat(d.category)}</span>
                </div>
                {d.acknowledged ? <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" /> : <Circle className="w-4 h-4 text-amber-500 shrink-0" />}
              </div>
              <div className="mt-2 font-semibold text-token-primary">{d.title}</div>
              <div className="mt-1 text-[11px] text-token-muted">v{d.version} · {d.updated_at ? formatDateUk(d.updated_at) : ''}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Loading() { return <div className="py-12 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto text-token-muted" /></div>; }
