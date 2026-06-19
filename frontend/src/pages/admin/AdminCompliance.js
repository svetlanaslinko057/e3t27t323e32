import { useEffect, useState } from 'react';
import { lumen } from '@/lib/lumenApi';
import { Loader2, Scale, Save } from 'lucide-react';

export default function AdminCompliance() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [savingSeg, setSavingSeg] = useState(null);

  const load = () => lumen.get('/institutional/compliance/matrix').then((r) => setRows(r.data.items || [])).catch(() => {}).finally(() => setLoading(false));
  useEffect(() => { load(); }, []);

  const update = (seg, field, value) => setRows((rs) => rs.map((r) => r.segment === seg ? { ...r, [field]: value } : r));
  const save = async (r) => {
    setSavingSeg(r.segment);
    try {
      await lumen.patch(`/admin/institutional/compliance/matrix/${r.segment}`, {
        max_ticket_uah: r.max_ticket_uah === '' || r.max_ticket_uah == null ? null : Number(r.max_ticket_uah),
        requires_accreditation: !!r.requires_accreditation,
        requires_ubo: !!r.requires_ubo,
      });
    } catch (_e) {} finally { setSavingSeg(null); }
  };

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6" data-testid="admin-compliance">
      <div><div className="text-[11px] uppercase tracking-widest text-muted-foreground">Institutional OS · G8</div><h1 className="text-2xl font-bold flex items-center gap-2"><Scale className="w-5 h-5 text-[#2E5D4F]" /> Матриця комплаєнсу</h1><p className="text-sm text-muted-foreground mt-1">Ліміти та вимоги за сегментами. Ці правила застосовуються при перевірці інвестиції.</p></div>
      <div className="space-y-3">
        {rows.map((r) => (
          <div key={r.segment} className="rounded-2xl border border-border bg-card p-4" data-testid={`matrix-${r.segment}`}>
            <div className="flex items-center justify-between mb-3"><div className="font-semibold">{r.segment_label}</div><button onClick={() => save(r)} disabled={savingSeg === r.segment} data-testid={`matrix-save-${r.segment}`} className="h-9 px-3 rounded-lg text-xs font-medium text-white inline-flex items-center gap-1.5" style={{ background: '#2E5D4F' }}>{savingSeg === r.segment ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />} Зберегти</button></div>
            <div className="grid md:grid-cols-3 gap-3 items-center">
              <div><label className="text-[11px] uppercase text-muted-foreground">Ліміт чека, ₾ (порожньо = без ліміту)</label><input type="number" value={r.max_ticket_uah ?? ''} onChange={(e) => update(r.segment, 'max_ticket_uah', e.target.value)} className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" /></div>
              <label className="flex items-center gap-2 text-sm mt-5"><input type="checkbox" checked={!!r.requires_accreditation} onChange={(e) => update(r.segment, 'requires_accreditation', e.target.checked)} /> Потрібна акредитація</label>
              <label className="flex items-center gap-2 text-sm mt-5"><input type="checkbox" checked={!!r.requires_ubo} onChange={(e) => update(r.segment, 'requires_ubo', e.target.checked)} /> Потрібен UBO</label>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
