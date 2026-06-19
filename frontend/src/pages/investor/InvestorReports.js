import { useEffect, useState } from 'react';
import { lumen, formatDateUk } from '@/lib/lumenApi';
import { FileText, Download, Loader2, BarChart3, Building2, Landmark } from 'lucide-react';

const KIND_META = {
  asset_factsheet: { icon: Building2, label: 'Факт-лист активу', color: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  quarterly: { icon: BarChart3, label: 'Квартальний звіт', color: 'bg-sky-50 text-sky-700 border-sky-200' },
  fund_report: { icon: Landmark, label: 'Звіт фонду', color: 'bg-violet-50 text-violet-700 border-violet-200' },
};

export default function InvestorReports() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    lumen.get('/reports').then((r) => setData(r.data)).finally(() => setLoading(false));
  }, []);

  const dl = (rid) => {
    const url = `${lumen.defaults.baseURL}/reports/${rid}/pdf`;
    window.open(url, '_blank');
  };

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;

  const items = data?.items || [];

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-5" data-testid="investor-reports">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Reporting OS · G12</div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><FileText className="w-5 h-5 text-[#2E5D4F]" /> Бібліотека звітів</h1>
        <p className="text-sm text-muted-foreground mt-1">PDF-звіти за вашими активами та фондами — завантажуйте для дю ділідженсу або архіву.</p>
      </div>

      <div className="flex gap-3 text-xs text-muted-foreground">
        <span>Моїх активів: <b className="text-foreground">{data?.my_assets ?? 0}</b></span>
        <span>Моїх фондів: <b className="text-foreground">{data?.my_funds ?? 0}</b></span>
        <span>Доступних звітів: <b className="text-foreground">{data?.count ?? 0}</b></span>
      </div>

      {items.length === 0 ? (
        <div className="rounded-2xl border border-border p-10 text-center text-sm text-muted-foreground">
          <FileText className="w-8 h-8 mx-auto mb-3 opacity-40" />Звітів для вас ще немає. Адміністратор згенерує їх за результатами кварталу.
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="reports-grid">
          {items.map((r) => {
            const meta = KIND_META[r.kind] || KIND_META.quarterly;
            const Icon = meta.icon;
            return (
              <div key={r.id} className="rounded-2xl border border-border bg-card overflow-hidden" data-testid={`report-${r.id}`}>
                <div className={`h-1.5 ${meta.color.split(' ')[0]}`} />
                <div className="p-5">
                  <span className={`inline-flex items-center gap-1.5 text-[11px] px-2 py-1 rounded-full border ${meta.color}`}>
                    <Icon className="w-3 h-3" /> {meta.label}
                  </span>
                  <h3 className="mt-3 font-semibold text-sm leading-snug">{r.title}</h3>
                  <p className="text-[11px] text-muted-foreground mt-1">{formatDateUk(r.created_at)}</p>
                  <button onClick={() => dl(r.id)} data-testid={`report-pdf-${r.id}`}
                    className="mt-4 w-full h-9 rounded-lg text-sm font-medium text-white inline-flex items-center justify-center gap-1.5"
                    style={{ background: '#2E5D4F' }}>
                    <Download className="w-4 h-4" /> PDF
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
