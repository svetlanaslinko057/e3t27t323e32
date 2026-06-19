import { useEffect, useState } from 'react';
import { lumen, formatUAH } from '@/lib/lumenApi';
import { Loader2, Scale, Check, X } from 'lucide-react';

export default function InstitutionalCompliance() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { lumen.get('/institutional/compliance/matrix').then((r) => setRows(r.data.items || [])).catch(() => {}).finally(() => setLoading(false)); }, []);
  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6" data-testid="institutional-compliance">
      <div><div className="text-[11px] uppercase tracking-widest text-muted-foreground">Institutional OS · G8</div><h1 className="text-2xl font-bold flex items-center gap-2"><Scale className="w-5 h-5 text-[#2E5D4F]" /> Матриця комплаєнсу</h1><p className="text-sm text-muted-foreground mt-1">Ліміти та вимоги за сегментами інвесторів.</p></div>
      <div className="rounded-2xl border border-border bg-card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-muted-foreground"><tr><th className="text-left font-medium px-4 py-2.5">Сегмент</th><th className="text-right font-medium px-4 py-2.5">Ліміт чека</th><th className="text-center font-medium px-4 py-2.5">Акредитація</th><th className="text-center font-medium px-4 py-2.5">UBO</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.segment} className="border-t border-border">
                <td className="px-4 py-2.5 font-medium">{r.segment_label}</td>
                <td className="px-4 py-2.5 text-right">{r.max_ticket_uah == null ? 'Без ліміту' : formatUAH(r.max_ticket_uah)}</td>
                <td className="px-4 py-2.5 text-center">{r.requires_accreditation ? <Check className="w-4 h-4 text-emerald-600 inline" /> : <X className="w-4 h-4 text-muted-foreground inline" />}</td>
                <td className="px-4 py-2.5 text-center">{r.requires_ubo ? <Check className="w-4 h-4 text-emerald-600 inline" /> : <X className="w-4 h-4 text-muted-foreground inline" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
